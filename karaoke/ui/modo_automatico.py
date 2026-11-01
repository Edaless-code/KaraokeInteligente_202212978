"""Modo automático (opción "a").

1. Se elige de dónde llega el sonido: el micrófono (karaoke en vivo) o un
   archivo de audio (para probar o para acompañar una pista grabada).
2. Se preparan los motores de voz (Vosk para seguir en tiempo real y, si está
   instalado, Whisper para identificar). Si falta un modelo de Vosk se ofrece
   descargarlo.
3. Un hilo aparte captura, limpia y transcribe el audio; la pantalla lee los
   resultados, se los pasa al ``ControladorAutomatico`` y dibuja la letra.

Las mismas teclas del modo manual siguen disponibles para corregir:
c continuar · a atrás · i igual · r repetir · g ignorar · s seguir ·
n siguiente del programa · x abandonar la canción · t terminar de aprender ·
f finalizar.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..audio.fuentes import ErrorAudio, FuenteArchivo, FuenteAudio, FuenteMicrofono
from ..audio.modelos import MODELOS, NOMBRES_IDIOMA, descargar_modelo, modelo_valido, ruta_modelo
from ..audio.motores import ErrorMotor
from ..audio.proceso import ProcesadorAudio, crear_limpiador, crear_motores, idiomas_escucha, ruta_relativa
from ..automatico import (APRENDIENDO, ESPERANDO, FIN, IGNORANDO, PAUSA, ControladorAutomatico,
                          EstadoPantalla)
from ..sesion import SesionKaraoke
from ..sincronia import LineaDeTiempo, desfase_pantalla
from . import consola
from .consola import color
from .diagnostico import barra
from .pantalla import VistaKaraoke, componer, encabezado, pie

if TYPE_CHECKING:
    from .menus import Aplicacion

AYUDA = ("c continuar · a atrás · i igual · r repetir · g ignorar · s seguir · n siguiente del programa · "
         "x otra canción · t terminar de aprender · d detalles · f finalizar")

# Estado → (texto para el público, tono).
ESTADOS = {
    ESPERANDO: ("Escuchando · cante para identificar la canción", "cian"),
    "siguiendo": ("Cantando · la letra sigue al cantante", "verde"),
    PAUSA: ("En pausa · sin voz, se reanuda sola", "amarillo"),
    IGNORANDO: ("Ignorando · presione s para seguir", "amarillo"),
    APRENDIENDO: ("Aprendiendo una canción nueva", "magenta"),
    FIN: ("Fin", "tenue"),
}


class ModoAutomatico:
    def __init__(self, app: Aplicacion):
        self.app = app
        self.bd = app.bd
        self.config = app.config
        self.teclado = app.teclado

    # ------------------------------------------------------------ preparar
    def elegir_fuente(self) -> FuenteAudio | None:
        consola.limpiar()
        consola.titulo("Modo automático")
        print("  ¿De dónde llega el sonido?")
        print("  (m) Micrófono (karaoke en vivo)")
        print("  (a) Archivo de audio MP3/WAV (prueba o pista grabada)")
        print("  (r) Regresar")
        opcion = self.app.preguntar("Opción: ").lower()[:1]
        frecuencia = self.config.entero("audio", "frecuencia_muestreo")
        if opcion == "m":
            return FuenteMicrofono(frecuencia, self.config.texto("audio", "dispositivo"))
        if opcion == "a":
            ruta = self.elegir_pista()
            if ruta is None:
                return None
            if not ruta.exists():
                consola.error(f"No existe el archivo {ruta}")
                self.teclado.pausa()
                return None
            desde = self.app.preguntar("¿Desde qué segundo? [0]: ")
            reproducir = self.teclado.confirmar("¿Reproducir el audio por las bocinas?")
            return FuenteArchivo(ruta, frecuencia, tiempo_real=True, reproducir=reproducir,
                                 desde_segundo=float(desde) if desde.replace(".", "", 1).isdigit() else 0.0,
                                 aislar_voz=self.config.booleano("audio", "aislar_voz_archivo"),
                                 retardo_reproduccion=self.config.decimal("automatico",
                                                                          "segundos_analisis_adelantado"))
        return None

    def pistas_disponibles(self) -> list[tuple[str, Path]]:
        """Pistas de la biblioteca (f → m) y audios de la carpeta de ejemplos."""
        pistas = [(f"[{codigo}] {nombre}", self.config.carpeta / archivo)
                  for codigo, nombre, archivo in self.bd.listar_pistas()]
        vistas = {ruta.resolve() for _, ruta in pistas}
        ejemplos = self.config.carpeta / "ejemplos"
        if ejemplos.is_dir():
            for ruta in sorted(ejemplos.iterdir()):
                if ruta.suffix.lower() in (".mp3", ".wav", ".flac", ".ogg") and ruta.resolve() not in vistas:
                    pistas.append((f"{ruta.name} (ejemplo)", ruta))
        return [(texto, ruta) for texto, ruta in pistas if ruta.exists()]

    def elegir_pista(self) -> Path | None:
        pistas = self.pistas_disponibles()
        if pistas:
            print()
            for numero, (texto, _) in enumerate(pistas, 1):
                print(f"    {color(str(numero), 'negrita', 'cian'):>4}  {texto}")
            print(color("  Para agregar más pistas use f → m.", "tenue"))
        texto = self.app.preguntar("  Número de la pista o ruta de un archivo [1]: " if pistas
                                   else "  Ruta del archivo de audio: ").strip().strip('"')
        if not texto and pistas:
            return pistas[0][1]
        if texto.isdigit() and 1 <= int(texto) <= len(pistas):
            return pistas[int(texto) - 1][1]
        return ruta_relativa(self.config, texto) if texto else None

    def revisar_modelos(self, idiomas: list[str]) -> None:
        """Ofrece descargar los modelos de Vosk que falten."""
        if self.config.texto("audio", "motor").lower() in ("whisper", "simulado"):
            return
        for idioma in idiomas:
            ruta = ruta_modelo(self.config, idioma)
            if idioma not in MODELOS or modelo_valido(ruta):
                continue
            consola.aviso(f"Falta el modelo de voz en {NOMBRES_IDIOMA[idioma]} ({MODELOS[idioma]}, ~40 MB).")
            if not self.teclado.confirmar("¿Descargarlo ahora (necesita internet)?"):
                continue

            def progreso(leidos: int, total: int) -> None:
                porcentaje = leidos * 100 // total if total else 0
                print(f"\r  Descargando… {leidos // 1_000_000} MB ({porcentaje} %)", end="", flush=True)

            try:
                descargar_modelo(idioma, ruta, progreso)
                print()
                consola.exito(f"Modelo instalado en {ruta}")
            except Exception as ex:
                print()
                consola.error(f"No se pudo descargar: {ex}")

    # ------------------------------------------------------------ ejecutar
    def ejecutar(self) -> None:
        if self.bd.contar_canciones() == 0:
            consola.limpiar()
            consola.aviso("La base de datos no tiene canciones: el modo automático no podrá reconocer "
                          "ninguna y las tratará como canciones nuevas.")
            ejemplos = self.config.carpeta / "canciones.txt"
            if ejemplos.exists() and self.teclado.confirmar(f"¿Cargar ahora las canciones de {ejemplos.name}?"):
                from ..importador import importar_archivo

                resultado = importar_archivo(self.bd, ejemplos, self.config)
                consola.exito(f"Se cargaron {len(resultado.agregadas)} canción(es).")
        fuente = self.elegir_fuente()
        if fuente is None:
            return
        # Siempre en español (y en inglés), además de los idiomas de las canciones.
        idiomas = idiomas_escucha(self.config, sorted({c.idioma for c in self.bd.todas_las_letras().values()}))
        self.revisar_modelos(idiomas)
        print(color("  Cargando los modelos de voz…", "tenue"))
        try:
            motores, avisos = crear_motores(self.config, idiomas)
        except ErrorMotor as ex:
            consola.error(str(ex))
            self.teclado.pausa()
            return
        for aviso in avisos:
            consola.aviso(aviso)
        procesador = ProcesadorAudio(fuente, crear_limpiador(self.config, fuente), motores)
        sesion = SesionKaraoke(self.bd, "automatico")
        control = ControladorAutomatico(self.bd, self.app.buscador, self.config, sesion,
                                        procesador.nombres_motores,
                                        con_whisper=any(m.nombre.lower().startswith("whisper") for m in motores))
        try:
            procesador.iniciar()
        except ErrorAudio as ex:
            consola.error(str(ex))
            sesion.finalizar()
            self.teclado.pausa()
            return
        self.entrada_pista = None
        consola.entrar_pantalla_completa()
        try:
            self.bucle(procesador, control)
        finally:
            consola.salir_pantalla_completa()
            procesador.detener()
            control.finalizar()
        if procesador.error:
            consola.error(f"Error de audio: {procesador.error}")
        if self.entrada_pista is not None:
            codigo, archivo, desde, entrada = self.entrada_pista
            self.reproductor.reproducir(codigo, archivo, desde=desde, entrada=None if desde is not None else entrada,
                                        voz=self.config.decimal("automatico", "voz_pista_al_reconocer"),
                                        mensaje="Canción reconocida: la pista entra donde vas cantando")
        self.resumen(sesion)

    def revisar_entrada_pista(self, procesador: ProcesadorAudio, control: ControladorAutomatico) -> bool:
        """Con el micrófono, al reconocer una canción que tiene pista (con o sin tiempos),
        prepara la entrada de la pista justo donde va el cantante (con la voz
        del artista bajada). Devuelve True si hay que pasar a la pista."""
        if control.cancion is None or control.cancion.codigo == self._revisada:
            return False
        self._revisada = control.cancion.codigo
        if not self.config.booleano("automatico", "pista_al_reconocer"):
            return False
        if type(procesador.fuente).__name__ != "FuenteMicrofono":
            return False  # con una pista o un archivo de audio ya suena la música
        from .reproducir import ReproducirConLetra

        self.reproductor = ReproducirConLetra(self.app)
        archivo = self.reproductor.pista_de(control.cancion.codigo)
        if not archivo:
            return False
        from ..pistas import punto_de_entrada

        tiempos = self.bd.obtener_tiempos(control.cancion.codigo)
        linea, fraccion = control.posicion_cantada()
        latencia = self.config.decimal("automatico", "segundos_latencia_reconocimiento")
        entrada = (linea, fraccion, latencia)
        # Sin tiempos exactos también entra: con tiempos aproximados que la IA
        # afina mientras suena (el punto de entrada se calcula con ellos).
        desde = (punto_de_entrada(tiempos, *entrada)
                 if tiempos and len(tiempos) == len(control.cancion.lineas) else None)
        self.entrada_pista = (control.cancion.codigo, archivo, desde, entrada)
        return True

    def bucle(self, procesador: ProcesadorAudio, control: ControladorAutomatico) -> None:
        nivel, voz = -120.0, False
        ultimo_dibujo = 0.0
        cambio = True
        fin_audio = None
        self._ultima_pantalla = None
        self.ver_detalles = False
        self._revisada = None
        # Con una pista que suena por las bocinas el análisis va adelantado y la
        # pantalla muestra lo que corresponde a lo que se escucha (sincronía).
        retardo = getattr(procesador.fuente, "retardo", 0.0)
        linea_tiempo: LineaDeTiempo[EstadoPantalla] = LineaDeTiempo(desfase_pantalla(
            retardo,
            self.config.decimal("automatico", "segundos_letra_adelantada"),
            self.config.decimal("automatico", "segundos_latencia_reconocimiento")))
        segundo = 0.0
        while control.estado != FIN:
            # 1. Resultados del audio.
            while not procesador.cola.empty():
                resultado = procesador.cola.get_nowait()
                nivel, voz = resultado.nivel_db, resultado.voz
                for t in resultado.transcripciones:
                    control.recibir(t, retraso=max(0.0, resultado.segundo - t.segundo))
                    cambio = True
                control.tic(resultado.segundo, resultado.voz)
                segundo = resultado.segundo
                linea_tiempo.guardar(segundo, control.pantalla())
                if resultado.terminado and fin_audio is None:
                    fin_audio = time.monotonic()
            if self.revisar_entrada_pista(procesador, control):
                break
            if control.vocabulario_pedido is not None:
                procesador.pedir_vocabulario(*control.vocabulario_pedido)
                control.vocabulario_pedido = None
            # 2. Teclas del operador (se ven de inmediato, sin el desfase).
            tecla = self.teclado.tecla(0.05)
            if tecla == "d":
                self.ver_detalles = not self.ver_detalles
                cambio = True
            elif tecla:
                cambio = True
                if not control.comando(tecla):
                    break
                linea_tiempo.reiniciar(control.pantalla())
            # 3. Pantalla: se redibuja en su lugar y solo si algo cambió (como
            #    mucho 4 veces por segundo), para que la letra sea fácil de seguir.
            ahora = time.monotonic()
            if cambio or ahora - ultimo_dibujo > 0.1:
                # Terminado el análisis, el reloj sigue corriendo con la pista.
                reloj = segundo + (ahora - fin_audio if fin_audio is not None else 0.0)
                pantalla = linea_tiempo.foto(reloj) or control.pantalla()
                self.dibujar(pantalla, procesador, nivel, voz)
                ultimo_dibujo, cambio = ahora, False
            # Al terminar el análisis todavía suena el final de la pista.
            if fin_audio is not None and ahora - fin_audio > 2 + retardo:
                control.avisar("Terminó el archivo de audio.")
                break

    def dibujar(self, pantalla: EstadoPantalla, procesador: ProcesadorAudio,
                nivel: float, voz: bool) -> None:
        texto_estado, tono = ESTADOS.get(pantalla.estado, (pantalla.estado.capitalize(), "cian"))
        # Los detalles técnicos cambian a cada instante: solo se muestran si se
        # piden con (d); así la pantalla normal no se mueve mientras se canta.
        detalles: list[str] = []
        if self.ver_detalles:
            detalles = [f"Escuchado: {pantalla.escuchado[-70:]}" if pantalla.escuchado else "Escuchado: …",
                        f"Sonido {barra(nivel, 20)} {'voz' if voz else '   '} · {procesador.nombres_motores}",
                        f"Fuente: {procesador.fuente.nombre}"]
            if pantalla.segundos_por_palabra:
                detalles.append(f"Tempo del cantante: {pantalla.segundos_por_palabra:.2f} s por palabra")
        mensaje = pantalla.avisos[-1] if pantalla.avisos else ""
        if pantalla.cancion is not None:
            vista = VistaKaraoke(
                nombre=pantalla.cancion.nombre, codigo=pantalla.cancion.codigo,
                lineas=pantalla.cancion.lineas, actual=pantalla.linea, modo="automático",
                estado=texto_estado, tono_estado=tono, mensaje=mensaje, ayuda=AYUDA, detalles=detalles,
                previas=self.config.entero("pantalla", "lineas_previas"),
                siguientes=self.config.entero("pantalla", "lineas_siguientes"),
            )
            self._mostrar(componer(vista))
            return
        self._mostrar(self._pantalla_sin_cancion(pantalla, texto_estado, tono, mensaje, detalles))

    def _pantalla_sin_cancion(self, pantalla: EstadoPantalla, texto_estado: str, tono: str,
                              mensaje: str, detalles: list[str]) -> list[str]:
        """Mientras se identifica la canción (o se aprende una nueva)."""
        ancho = min(consola.ancho(), 100)
        alto = consola.alto()
        renglones = encabezado("KARAOKE INTELIGENTE", "modo automático", ancho)
        centro: list[str] = []
        if pantalla.estado == APRENDIENDO:
            centro.append(color("  Canción nueva: se escribe un borrador de la letra", "negrita", "magenta"))
            centro.append(color("  (se revisa y se guarda después en f → v)", "tenue"))
            centro.append("")
            centro += [f"     {linea}" for linea in pantalla.aprendidas]
        else:
            centro.append(color("  ♪  Escuchando…", "negrita", "texto"))
            centro.append("")
            centro.append(color("  Empiece a cantar (o reproduzca la pista): la canción se reconoce sola", "blanco"))
            centro.append(color(f"  entre las {self.bd.contar_canciones()} canciones de la base de datos.", "blanco"))
            if pantalla.siguiente_programa:
                centro.append("")
                centro.append(color(f"  Siguiente en el programa: {pantalla.siguiente_programa}", "cian"))
        abajo = ["", "  " + color("● ", tono) + color(texto_estado, "negrita", tono),
                 color(f"  {mensaje}", "amarillo") if mensaje else ""]
        abajo += [color(f"  {detalle}", "tenue") for detalle in detalles]
        abajo += pie(AYUDA, ancho)
        libre = alto - len(renglones) - len(abajo) - 1
        arriba = max(1, (libre - len(centro)) // 2)
        renglones += [""] * arriba + centro
        renglones += [""] * max(1, libre - arriba - len(centro))
        return renglones + abajo

    def _mostrar(self, renglones: list[str]) -> None:
        if renglones != self._ultima_pantalla:
            self._ultima_pantalla = renglones
            consola.redibujar(renglones)

    def resumen(self, sesion: SesionKaraoke) -> None:
        consola.limpiar()
        consola.titulo("Fin de la sesión automática")
        print(f"  Se cantaron {len(sesion.cantadas)} canción(es):")
        for numero, cantada in enumerate(sesion.cantadas, 1):
            estado = "completa" if cantada.completada else "incompleta"
            print(f"   {numero:>2}. [{cantada.codigo}] {cantada.nombre} ({estado})")
        temporales = self.bd.listar_temporales()
        if temporales:
            consola.aviso(f"  Hay {len(temporales)} canción(es) aprendida(s): revíselas en (f) → (v).")
        self.teclado.pausa()
