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
from typing import TYPE_CHECKING

from ..audio.fuentes import ErrorAudio, FuenteArchivo, FuenteAudio, FuenteMicrofono
from ..audio.modelos import MODELOS, NOMBRES_IDIOMA, descargar_modelo, modelo_valido, ruta_modelo
from ..audio.motores import ErrorMotor
from ..audio.proceso import ProcesadorAudio, crear_limpiador, crear_motores, ruta_relativa
from ..automatico import APRENDIENDO, ESPERANDO, FIN, IGNORANDO, PAUSA, ControladorAutomatico
from ..sesion import SesionKaraoke
from . import consola
from .consola import color
from .diagnostico import barra
from .pantalla import VistaKaraoke, dibujar

if TYPE_CHECKING:
    from .menus import Aplicacion

AYUDA = ("[c] continuar  [a] atrás  [i] igual  [r] repetir  [g] ignorar  [s] seguir  "
         "[n] siguiente del programa  [x] abandonar canción  [t] terminar de aprender  [f] finalizar")

ESTADOS = {
    ESPERANDO: "ESCUCHANDO · cante para identificar la canción",
    "siguiendo": "CANTANDO · siguiendo al cantante",
    PAUSA: "EN PAUSA · sin voz (se reanuda solo)",
    IGNORANDO: "IGNORANDO · presione (s) para seguir",
    APRENDIENDO: "APRENDIENDO una canción nueva",
    FIN: "FIN",
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
            ejemplo = self.config.carpeta / "ejemplos" / "Sound_of_You.mp3"
            texto = self.app.preguntar(f"Ruta del archivo [{ejemplo}]: ")
            ruta = ruta_relativa(self.config, texto) if texto else ejemplo
            if not ruta.exists():
                consola.error(f"No existe el archivo {ruta}")
                self.teclado.pausa()
                return None
            desde = self.app.preguntar("¿Desde qué segundo? [0]: ")
            reproducir = self.teclado.confirmar("¿Reproducir el audio por las bocinas?")
            return FuenteArchivo(ruta, frecuencia, tiempo_real=True, reproducir=reproducir,
                                 desde_segundo=float(desde) if desde.replace(".", "", 1).isdigit() else 0.0,
                                 aislar_voz=self.config.booleano("audio", "aislar_voz_archivo"))
        return None

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
            consola.aviso("No hay canciones en la base de datos. Agréguelas con (f).")
        fuente = self.elegir_fuente()
        if fuente is None:
            return
        idiomas = sorted({c.idioma for c in self.bd.todas_las_letras().values()}) or ["es"]
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
                                        procesador.nombres_motores)
        try:
            procesador.iniciar()
        except ErrorAudio as ex:
            consola.error(str(ex))
            sesion.finalizar()
            self.teclado.pausa()
            return
        try:
            self.bucle(procesador, control)
        finally:
            procesador.detener()
            control.finalizar()
        if procesador.error:
            consola.error(f"Error de audio: {procesador.error}")
        self.resumen(sesion)

    def bucle(self, procesador: ProcesadorAudio, control: ControladorAutomatico) -> None:
        nivel, voz = -120.0, False
        ultimo_dibujo = 0.0
        cambio = True
        fin_audio = None
        while control.estado != FIN:
            # 1. Resultados del audio.
            while not procesador.cola.empty():
                resultado = procesador.cola.get_nowait()
                nivel, voz = resultado.nivel_db, resultado.voz
                for t in resultado.transcripciones:
                    control.recibir(t, retraso=max(0.0, resultado.segundo - t.segundo))
                    cambio = True
                control.tic(resultado.segundo, resultado.voz)
                if resultado.terminado and fin_audio is None:
                    fin_audio = time.monotonic()
            if control.vocabulario_pedido is not None:
                procesador.pedir_vocabulario(*control.vocabulario_pedido)
                control.vocabulario_pedido = None
            # 2. Teclas del operador.
            tecla = self.teclado.tecla(0.05)
            if tecla:
                cambio = True
                if not control.comando(tecla):
                    break
            # 3. Pantalla (como mucho 5 veces por segundo).
            ahora = time.monotonic()
            if cambio or ahora - ultimo_dibujo > 0.5:
                self.dibujar(control, procesador, nivel, voz)
                ultimo_dibujo, cambio = ahora, False
            if fin_audio is not None and ahora - fin_audio > 2:
                control.avisar("Terminó el archivo de audio.")
                break

    def dibujar(self, control: ControladorAutomatico, procesador: ProcesadorAudio,
                nivel: float, voz: bool) -> None:
        pantalla = control.pantalla()
        estado = ESTADOS.get(pantalla.estado, pantalla.estado.upper())
        detalles = [f"Escuchado: {pantalla.escuchado[-70:]}" if pantalla.escuchado else "Escuchado: …",
                    f"Sonido {barra(nivel, 20)} {'VOZ' if voz else '   '} · {procesador.fuente.nombre} · "
                    f"{procesador.nombres_motores}"]
        if pantalla.segundos_por_palabra:
            detalles.append(f"Tempo del cantante: {pantalla.segundos_por_palabra:.2f} s por palabra")
        if pantalla.siguiente_programa:
            detalles.append(f"Siguiente en el programa: {pantalla.siguiente_programa}")
        if pantalla.cancion is not None:
            vista = VistaKaraoke(
                nombre=pantalla.cancion.nombre, codigo=pantalla.cancion.codigo,
                lineas=pantalla.cancion.lineas, actual=pantalla.linea, modo="automático",
                estado=estado, mensaje=" · ".join(pantalla.avisos[-2:]), ayuda=AYUDA, detalles=detalles,
                previas=self.config.entero("pantalla", "lineas_previas"),
                siguientes=self.config.entero("pantalla", "lineas_siguientes"),
            )
            dibujar(vista)
            return
        consola.limpiar()
        consola.titulo("KARAOKE INTELIGENTE · modo automático")
        print()
        print(color(f"  {estado}", "negrita", "amarillo" if pantalla.estado != APRENDIENDO else "magenta"))
        print()
        if pantalla.estado == APRENDIENDO:
            print(color("  Letra aprendida hasta ahora:", "tenue"))
            for linea in pantalla.aprendidas:
                print(f"    {linea}")
            print()
        for aviso in pantalla.avisos[-3:]:
            consola.aviso(f"  {aviso}")
        for detalle in detalles:
            print(color(f"  {detalle}", "tenue"))
        print(color("─" * min(consola.ancho(), 100), "cian"))
        print(color(f"  {AYUDA}", "cian"))

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
