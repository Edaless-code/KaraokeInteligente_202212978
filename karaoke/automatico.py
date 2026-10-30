"""Controlador del modo automático.

Recibe las transcripciones del motor de voz (Vosk, Whisper o el simulado) y
el estado del detector de voz, y automatiza todo lo que en el modo manual
hace el operador:

=============  ==============================================================
Estado         Qué significa
=============  ==============================================================
esperando      No hay canción en curso: se juntan las palabras escuchadas y se
               busca a qué canción pertenecen (con bono para la siguiente del
               PROGRAMA). Al identificarla se empieza a seguir desde la línea
               que se está cantando.
siguiendo      Se sigue al cantante línea por línea con el ``Seguidor`` (c, i
               y r automáticos).
pausa          Ignorar automático: hace ``segundos_silencio_pausa`` que no hay
               voz (el cantante afina, habla con el público o hay una parte
               instrumental). Se conserva la línea y se reanuda (seguir) en
               cuanto vuelve a cantar la letra.
ignorando      Ignorar manual (tecla g): no se procesa nada hasta (s).
aprendiendo    Lo que se canta no está en la base de datos: es una canción
               nueva. Cada frase transcrita se guarda en TEMP_LETRAS; al
               terminar se sugiere un nombre (la frase más repetida, que
               suele ser el coro y el título).
fin            La sesión terminó (tecla f o silencio prolongado).
=============  ==============================================================

Las variaciones de cada canción se consideran así: el tempo se aprende del
cantante, los saltos y coros extra se resuelven con la búsqueda global del
Seguidor, las improvisaciones que no son de la letra se ignoran y en las
partes instrumentales solo se predice por tempo si además se reconocen
palabras (no basta con que suene música).
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field

from .transcripcion import Transcripcion
from .buscador import Buscador, Resultado
from .config import Config
from .db import BaseDatos, Cancion
from .seguimiento import Evento, Seguidor
from .sesion import SesionKaraoke
from .texto import ajustar_linea, censurar, normalizar, vocabulario

ESPERANDO = "esperando"
SIGUIENDO = "siguiendo"
PAUSA = "pausa"
IGNORANDO = "ignorando"
APRENDIENDO = "aprendiendo"
FIN = "fin"


@dataclass
class Aviso:
    segundo: float
    texto: str


@dataclass
class EstadoPantalla:
    estado: str
    cancion: Cancion | None
    linea: int
    escuchado: str
    avisos: list[str] = field(default_factory=list)
    aprendidas: list[str] = field(default_factory=list)
    siguiente_programa: str = ""
    segundos_por_palabra: float = 0.0


class ControladorAutomatico:
    def __init__(self, bd: BaseDatos, buscador: Buscador, config: Config, sesion: SesionKaraoke,
                 motor_nombre: str = "", con_whisper: bool = False):
        self.bd = bd
        self.buscador = buscador
        self.config = config
        self.sesion = sesion
        self.motor_nombre = motor_nombre
        self.estado = ESPERANDO
        self.estado_previo = ESPERANDO
        self.cancion: Cancion | None = None
        self.seguidor: Seguidor | None = None
        self.segundo = 0.0

        self.palabras_muestra = config.entero("automatico", "palabras_muestra")
        self.palabras_nueva = config.entero("automatico", "palabras_cancion_nueva")
        self.parecido_conocida = config.decimal("automatico", "parecido_cancion_conocida")
        self.censurar = config.booleano("automatico", "censurar_transcripcion")
        self.avance = config.decimal("automatico", "avance_linea")
        self.silencio_pausa = config.decimal("automatico", "segundos_silencio_pausa")
        self.silencio_aprendizaje = config.decimal("automatico", "segundos_silencio_fin_aprendizaje")
        self.silencio_sesion = config.decimal("automatico", "segundos_silencio_fin_sesion")
        self.prediccion = config.booleano("automatico", "prediccion_tempo")
        self.restringir_vocabulario = config.booleano("automatico", "vocabulario_restringido")

        # Palabras recientes de CADA motor por separado (Vosk libre y Whisper):
        # mezclarlas desordena las frases, porque Whisper llega con retraso.
        self._recientes: dict[str, deque[tuple[float, str]]] = {}
        # Si se usa Whisper se sabe desde el inicio: así nunca se decide con
        # el ruido de Vosk mientras llega la primera frase de Whisper.
        self._hay_whisper = con_whisper
        self._mejor_parecido = 0.0
        # Frases completas recientes del motor más confiable: si la canción
        # resulta nueva, son sus primeras líneas.
        self._frases: deque[str] = deque(maxlen=12)
        self._parcial_libre: list[str] = []
        self._palabras_sin_identificar = 0
        self._consumidas: dict[str, int] = {}
        self._hay_restringido = False
        self.ultima_voz = 0.0
        self.ultimo_texto = -100.0
        self.ultima_coincidencia = 0.0
        self.escuchado = ""
        self.avisos: deque[Aviso] = deque(maxlen=4)
        # Aprendizaje de canciones nuevas.
        self.id_temporal: int | None = None
        self.lineas_aprendidas: list[str] = []
        # Pedido de vocabulario para el motor: (vocabulario, idioma) o None.
        self.vocabulario_pedido: tuple[set[str] | None, str | None] | None = None

    # ---------------------------------------------------------------- avisos
    def avisar(self, texto: str) -> None:
        self.avisos.append(Aviso(self.segundo, texto))

    def _pedir_vocabulario(self, cancion: Cancion | None) -> None:
        if not self.restringir_vocabulario:
            return
        if cancion is None:
            self.vocabulario_pedido = (None, None)
        else:
            self.vocabulario_pedido = (vocabulario(cancion.lineas, cancion.idioma), cancion.idioma)

    # ----------------------------------------------------- iniciar canciones
    def iniciar_cancion(self, cancion: Cancion, linea: int = 0, palabra: int | None = None,
                        motivo: str = "") -> None:
        if self.estado == APRENDIENDO:
            self._terminar_aprendizaje(descartar_si_corta=True)
        self.cancion = cancion
        self.seguidor = Seguidor(
            cancion.lineas,
            linea_inicial=linea,
            palabra_inicial=palabra,
            umbral_palabra=self.buscador.umbral_palabra,
            avance=self.avance,
            prediccion=self.prediccion,
            segundo=self.segundo,
        )
        self.sesion.iniciar(cancion, self.seguidor.mostrada)
        self.estado = SIGUIENDO
        self.ultima_coincidencia = self.segundo
        self._olvidar_lo_escuchado()
        self._pedir_vocabulario(cancion)
        self.avisar(f"Canción identificada: {cancion.nombre}{' · ' + motivo if motivo else ''}")

    def _terminar_cancion(self, completada: bool) -> None:
        if self.cancion is None:
            return
        if self.sesion.en_curso is not None and self.seguidor is not None:
            self.sesion.en_curso.actual = self.seguidor.mostrada
        self.sesion.terminar(completada)
        self.avisar(f"Terminó «{self.cancion.nombre}». Esperando la siguiente canción…")
        self.cancion = None
        self.seguidor = None
        self.estado = ESPERANDO
        self._olvidar_lo_escuchado()
        self._pedir_vocabulario(None)

    def _prioridad(self) -> dict[int, float]:
        prioridad = self.sesion.programa.prioridad(0.12)
        if self.sesion.cantadas and self.sesion.cantadas[-1].codigo is not None:
            ultima = self.sesion.cantadas[-1].codigo
            prioridad.setdefault(ultima, 0.04)  # puede repetir la misma
        return prioridad

    def _olvidar_lo_escuchado(self) -> None:
        self._recientes.clear()
        self._parcial_libre = []
        self._palabras_sin_identificar = 0
        self._mejor_parecido = 0.0
        self._frases.clear()

    def _identificar(self, palabras: list[str]) -> Resultado | None:
        if len(palabras) < self.palabras_muestra:
            return None
        consulta = palabras[-20:]
        resultados = self.buscador.buscar(consulta, self._prioridad(), limite=1)
        if resultados:
            self._mejor_parecido = max(self._mejor_parecido, resultados[0].puntaje)
        return self.buscador.identificar(consulta, self._prioridad())

    def _identificar_por_canal(self) -> Resultado | None:
        """Intenta identificar con lo que escuchó cada motor (por separado) y
        se queda con el resultado más claro."""
        mejor = None
        for recientes in self._recientes.values():
            resultado = self._identificar([p for _, p in recientes])
            if resultado and (mejor is None or resultado.orden > mejor.orden):
                mejor = resultado
        return mejor

    # -------------------------------------------------------- transcripción
    def _nuevas(self, t: Transcripcion) -> list[str]:
        """Palabras que todavía no se habían entregado de la frase en curso
        (los resultados parciales de Vosk van creciendo)."""
        palabras = t.palabras
        consumidas = min(self._consumidas.get(t.canal, 0), len(palabras))
        nuevas = palabras[consumidas:]
        self._consumidas[t.canal] = 0 if t.tipo == "final" else len(palabras)
        return nuevas

    def recibir(self, t: Transcripcion, retraso: float = 0.0) -> None:
        """Procesa una transcripción (parcial o final) de cualquier canal."""
        if t.canal == "restringido":
            self._hay_restringido = True
        if t.canal == "whisper":
            self._hay_whisper = True
        if t.palabras:
            self.ultimo_texto = self.segundo
            self.escuchado = censurar(t.texto) if self.censurar else t.texto
        if self.estado in (IGNORANDO, FIN):
            self._nuevas(t)
            return
        if t.canal in ("libre", "whisper"):
            self._recibir_libre(t, retraso)
        else:
            nuevas = self._nuevas(t)
            if self.estado in (SIGUIENDO, PAUSA) and nuevas:
                self._seguir(nuevas, retraso)

    def _canal_confiable(self, t: Transcripcion) -> bool:
        """Para decidir que una canción es nueva (y para aprender su letra)
        se usa el motor más confiable disponible: Whisper si está, si no Vosk."""
        return t.canal == "whisper" or not self._hay_whisper

    def _recibir_libre(self, t: Transcripcion, retraso: float) -> None:
        nuevas = self._nuevas(t)
        recientes = self._recientes.setdefault(t.canal, deque(maxlen=40))
        for palabra in nuevas:
            recientes.append((self.segundo, palabra))
        if t.tipo == "final" and self._canal_confiable(t):
            self._palabras_sin_identificar += len(t.palabras)
            if self.estado == ESPERANDO:
                self._frases.append(t.texto)

        if self.estado in (SIGUIENDO, PAUSA):
            if t.canal == "whisper":
                # Frases de Whisper: anclas de posición (llegan con retraso).
                if t.palabras:
                    self._seguir(t.palabras, retraso)
            elif not self._hay_restringido and nuevas:
                self._seguir(nuevas, retraso)
            elif t.tipo == "final" and len(t.palabras) > 6:
                self._seguir(t.palabras, retraso)
            if t.tipo == "final":
                self._revisar_cambio_de_cancion(t)
            return

        if self.estado == APRENDIENDO:
            resultado = self._identificar_por_canal()
            if resultado and resultado.evidencia >= self.buscador.evidencia_minima * 1.4:
                self._iniciar_resultado(resultado, "estaba en la base de datos")
                return
            if t.tipo == "final" and self._canal_confiable(t):
                self._aprender(t.texto)
            return

        # ESPERANDO
        resultado = self._identificar_por_canal()
        if resultado:
            self._iniciar_resultado(resultado)
        elif (t.tipo == "final" and self._canal_confiable(t)
              and self._palabras_sin_identificar >= self.palabras_nueva
              and self._mejor_parecido < self.parecido_conocida):
            # Solo es "nueva" si NINGUNA canción de la base se parece a lo
            # escuchado; si alguna se parece, se sigue escuchando.
            self._empezar_aprendizaje()

    def _iniciar_resultado(self, resultado: Resultado, motivo: str = "") -> None:
        cancion = self.bd.obtener_cancion(resultado.codigo)
        if cancion is None:
            return
        self.iniciar_cancion(cancion, palabra=resultado.palabra_siguiente,
                             linea=resultado.linea_actual, motivo=motivo)

    def _seguir(self, palabras: list[str], retraso: float) -> None:
        evento = self.seguidor.escuchar(palabras, self.segundo, retraso)
        if evento is not None:
            self._aplicar(evento)

    def _aplicar(self, evento: Evento) -> None:
        curso = self.sesion.en_curso
        if evento.tipo != "prediccion":
            self.ultima_coincidencia = self.segundo
        if self.estado == PAUSA and evento.tipo != "prediccion":
            self.estado = SIGUIENDO
            if curso:
                curso.seguir()
            self.avisar("El cantante volvió: se sigue con la letra (s).")
        if curso is not None:
            if evento.tipo == "igual":
                curso.igual()
            elif evento.tipo == "repetir":
                curso.repetir()
                self.avisar("El cantante repite la canción (r).")
            curso.ir_a(min(self.seguidor.mostrada, curso.total))
        if evento.tipo == "salto":
            self.avisar(f"Salto a la línea {evento.linea + 1} (cambio de estructura).")
        if evento.tipo == "fin":
            self._terminar_cancion(completada=True)

    def _revisar_cambio_de_cancion(self, t: Transcripcion) -> None:
        """Si hace rato que la letra no coincide y lo que se canta pertenece
        con claridad a otra canción, se cambia a esa canción."""
        if self.segundo - self.ultima_coincidencia < 8 or len(t.palabras) < 5:
            return
        resultado = self.buscador.identificar(t.palabras, self._prioridad(),
                                              evidencia=self.buscador.evidencia_minima * 1.6)
        if resultado and self.cancion and resultado.codigo != self.cancion.codigo:
            self._terminar_cancion(completada=False)
            self._iniciar_resultado(resultado, "el cantante cambió de canción")

    # ------------------------------------------------------- aprendizaje
    def _empezar_aprendizaje(self) -> None:
        self.estado = APRENDIENDO
        self.id_temporal = self.bd.crear_temporal(motor=self.motor_nombre)
        self.lineas_aprendidas = []
        self._pedir_vocabulario(None)
        self.avisar("Canción NUEVA: se está aprendiendo la letra en las tablas temporales.")
        # Las frases que ya se escucharon también son parte de la canción.
        for frase in self._frases:
            self._aprender(frase)
        self._frases.clear()

    def _aprender(self, texto: str) -> None:
        if self.id_temporal is None or not texto.strip():
            return
        if self.censurar:
            texto = censurar(texto)
        for linea in ajustar_linea(texto.strip(), self.config.caracteres_por_linea, "dividir"):
            self.bd.agregar_linea_temporal(self.id_temporal, linea)
            self.lineas_aprendidas.append(linea)

    def _terminar_aprendizaje(self, descartar_si_corta: bool = False) -> None:
        if self.id_temporal is None:
            self.estado = ESPERANDO
            return
        if len(self.lineas_aprendidas) < 3 or (descartar_si_corta and len(self.lineas_aprendidas) <= 2):
            # Menos de 3 líneas no es una canción (un comentario, el murmullo
            # del final de una pista): se descarta.
            self.bd.borrar_temporal(self.id_temporal)
            self.avisar("Lo que se escuchó era muy corto para ser una canción nueva; se descartó.")
        else:
            nombre = sugerir_nombre(self.lineas_aprendidas)
            self.bd.sugerir_nombre_temporal(self.id_temporal, nombre)
            self.avisar(f"Canción aprendida ({len(self.lineas_aprendidas)} líneas). Nombre sugerido: "
                        f"«{nombre}». Revísela en (f) → (v).")
        self.id_temporal = None
        self.lineas_aprendidas = []
        self.estado = ESPERANDO
        self._olvidar_lo_escuchado()

    # ------------------------------------------------------------- tiempo
    def tic(self, segundo: float, voz_activa: bool) -> None:
        """Llamar varias veces por segundo con el estado del detector de voz."""
        self.segundo = segundo
        if voz_activa:
            self.ultima_voz = segundo
        # Hay voz de verdad si el detector la oye Y el motor reconoce palabras
        # (con música de fondo el detector solo no basta).
        hay_voz = voz_activa and segundo - self.ultimo_texto < 4.0
        silencio = segundo - max(self.ultimo_texto, self.ultima_voz)

        if self.estado == SIGUIENDO and self.seguidor is not None:
            evento = self.seguidor.tic(segundo, hay_voz)
            if evento is not None:
                self._aplicar(evento)
            if self.estado == SIGUIENDO and segundo - self.ultimo_texto >= self.silencio_pausa:
                if self.seguidor.mostrada >= self.seguidor.total - 1:
                    self._terminar_cancion(completada=True)  # silencio después de la última línea
                else:
                    self.estado = PAUSA
                    if self.sesion.en_curso:
                        self.sesion.en_curso.ignorar()
                    self.avisar("Sin voz: se ignora hasta que el cantante continúe (g automático).")
        elif self.estado == APRENDIENDO and segundo - self.ultimo_texto >= self.silencio_aprendizaje:
            self._terminar_aprendizaje()
        elif self.estado == ESPERANDO:
            antiguas = segundo - 20
            for recientes in self._recientes.values():
                while recientes and recientes[0][0] < antiguas:
                    recientes.popleft()
            if segundo - self.ultimo_texto > 10:
                self._palabras_sin_identificar = 0
                self._mejor_parecido = 0.0
        if (self.silencio_sesion > 0 and self.estado in (ESPERANDO, PAUSA)
                and silencio >= self.silencio_sesion):
            self.finalizar()

    # --------------------------------------------- órdenes del operador
    def comando(self, tecla: str) -> bool:
        """Aplica una tecla. Devuelve ``False`` si la sesión terminó."""
        seguidor, curso = self.seguidor, self.sesion.en_curso
        if tecla == "f":
            self.finalizar()
            return False
        if tecla == "g":
            if self.estado != IGNORANDO:
                self.estado_previo = self.estado
                self.estado = IGNORANDO
                if curso:
                    curso.ignorar()
        elif tecla == "s":
            if self.estado == IGNORANDO:
                self.estado = self.estado_previo if self.estado_previo != PAUSA else SIGUIENDO
            elif self.estado == PAUSA:
                self.estado = SIGUIENDO
            if curso:
                curso.seguir()
            self.ultimo_texto = self.segundo
        elif tecla == "t" and self.estado == APRENDIENDO:
            self._terminar_aprendizaje()
        elif tecla == "n":
            siguiente = self.sesion.programa.siguiente()
            if siguiente is not None:
                cancion = self.bd.obtener_cancion(siguiente.codigo)
                if cancion:
                    if self.cancion is not None:
                        self._terminar_cancion(completada=False)
                    self.iniciar_cancion(cancion, motivo="siguiente del programa")
        elif seguidor is not None and curso is not None:
            if tecla in ("c", "\n", "derecha"):
                seguidor.continuar(self.segundo)
            elif tecla in ("a", "izquierda"):
                seguidor.atras(self.segundo)
            elif tecla == "i":
                curso.igual()
            elif tecla == "r":
                seguidor.repetir(self.segundo)
                curso.repetir()
            elif tecla == "x":
                self._terminar_cancion(completada=False)
                return True
            curso.ir_a(min(seguidor.mostrada, curso.total))
            if seguidor.terminada:
                self._terminar_cancion(completada=True)
        return True

    def finalizar(self) -> None:
        if self.estado == APRENDIENDO:
            self._terminar_aprendizaje()
        if self.cancion is not None:
            self._terminar_cancion(completada=bool(self.seguidor and self.seguidor.terminada))
        self.estado = FIN
        if not self.sesion.finalizada:
            self.sesion.finalizar()

    # ----------------------------------------------------------- pantalla
    def pantalla(self) -> EstadoPantalla:
        siguiente = self.sesion.programa.siguiente()
        return EstadoPantalla(
            estado=self.estado,
            cancion=self.cancion,
            linea=self.seguidor.mostrada if self.seguidor else 0,
            escuchado=self.escuchado,
            avisos=[a.texto for a in self.avisos if self.segundo - a.segundo < 8],
            aprendidas=list(self.lineas_aprendidas[-3:]),
            siguiente_programa=siguiente.nombre_solicitado if siguiente else "",
            segundos_por_palabra=self.seguidor.segundos_por_palabra if self.seguidor else 0.0,
        )


def sugerir_nombre(lineas: list[str]) -> str:
    """Sugiere el nombre de una canción aprendida: la línea que más se repite
    (normalmente el coro, que suele contener el título); si ninguna se repite,
    las primeras palabras de la primera línea."""
    if not lineas:
        return "Canción nueva"
    conteo = Counter(normalizar(l) for l in lineas if normalizar(l))
    linea, veces = conteo.most_common(1)[0] if conteo else ("", 0)
    if veces < 2:
        linea = normalizar(lineas[0])
    palabras = linea.split()[:6]
    return " ".join(palabras).capitalize() if palabras else "Canción nueva"
