"""Diagnóstico de audio (opción "d" del menú principal).

Permite ver los micrófonos disponibles, elegir cuál usar (se guarda en
karaoke.ini) y medir el nivel de entrada, el nivel después de la limpieza y si
el detector reconoce voz. Así se ajusta el micrófono antes de usar el modo
automático.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..audio.fuentes import (
    ErrorAudio,
    FuenteArchivo,
    FuenteAudio,
    FuenteHilo,
    FuenteMicrofono,
    microfono_predeterminado,
)
from ..audio.limpieza import LimpiadorAudio
from . import consola
from .consola import color

if TYPE_CHECKING:
    from .menus import Aplicacion


def barra(nivel: float, ancho: int = 30, minimo: float = -60.0) -> str:
    llenos = int(max(0.0, min(1.0, (nivel - minimo) / -minimo)) * ancho)
    return "█" * llenos + "·" * (ancho - llenos)


class Diagnostico:
    def __init__(self, app: Aplicacion):
        self.app = app
        self.config = app.config
        self.teclado = app.teclado

    def ejecutar(self) -> None:
        while True:
            consola.limpiar()
            consola.titulo("Diagnóstico de audio")
            actual = self.config.texto("audio", "dispositivo") or "predeterminado"
            print(color(f"  Micrófono configurado: {actual}", "tenue"))
            print("  (l) Listar micrófonos")
            print("  (e) Elegir el micrófono")
            print("  (n) Medir el nivel del micrófono y probar la limpieza")
            print("  (o) Probar la limpieza con un archivo de audio (MP3/WAV)")
            print("  (r) Regresar")
            opcion = self.app.preguntar("Opción: ").lower()[:1]
            try:
                if opcion == "l":
                    self.listar()
                    self.teclado.pausa()
                elif opcion == "e":
                    self.elegir()
                elif opcion == "n":
                    self.medir(FuenteMicrofono(self.config.entero("audio", "frecuencia_muestreo"),
                                               self.config.texto("audio", "dispositivo")))
                elif opcion == "o":
                    ruta = self.app.preguntar("Ruta del archivo de audio: ").strip('"')
                    if ruta:
                        self.medir(FuenteArchivo(Path(ruta), reproducir=True))
                elif opcion in ("r", "q", ""):
                    return
            except ErrorAudio as ex:
                consola.error(str(ex))
                self.teclado.pausa()

    def listar(self) -> list[tuple[int, str, str]]:
        """Lista completa: en Windows un micrófono aparece una vez por sistema
        de audio (MME, DirectSound, WASAPI…); cualquiera de ellos sirve."""
        from ..audio.fuentes import listar_microfonos_detalle

        microfonos = listar_microfonos_detalle()
        predeterminado = microfono_predeterminado()
        elegido = self.config.texto("audio", "dispositivo").strip()
        if not microfonos:
            consola.error("No se encontró ningún micrófono.")
        for indice, nombre, sistema in microfonos:
            marcas = []
            if indice == predeterminado:
                marcas.append("predeterminado")
            if elegido == str(indice):
                marcas.append("elegido")
            extra = color(f" ({', '.join(marcas)})", "cian") if marcas else ""
            print(f"  {indice:>3}. {nombre} " + color(f"· {sistema}", "tenue") + extra)
        return microfonos

    def detectar(self) -> None:
        from ..audio.fuentes import detectar_microfono

        print(color("  Probando los micrófonos…", "tenue"))
        try:
            indice, nombre = detectar_microfono(self.config.texto("audio", "dispositivo").strip() or None)
            consola.exito(f"  En uso: [{indice}] {nombre}")
        except ErrorAudio as ex:
            consola.error(f"  {ex}")

    def elegir(self) -> None:
        microfonos = self.listar()
        if not microfonos:
            self.teclado.pausa()
            return
        eleccion = self.app.preguntar("Número del micrófono (Enter = automático, el primero que funcione): ")
        if eleccion and not (eleccion.isdigit() and int(eleccion) in [m[0] for m in microfonos]):
            consola.error("Número inválido.")
            self.teclado.pausa()
            return
        self.config.establecer("audio", "dispositivo", eleccion)
        ruta = self.config.guardar()
        consola.exito(f"Guardado en {ruta}")
        self.detectar()
        self.teclado.pausa()

    def medir(self, fuente: FuenteAudio) -> None:
        limpiador = LimpiadorAudio.desde_config(self.config)
        candado = threading.Lock()
        datos = {"entrada": -120.0, "salida": -120.0, "voz": False, "snr": 0.0}

        def al_bloque(muestras):
            limpiador.procesar(muestras)
            with candado:
                datos.update(entrada=limpiador.nivel_entrada_db, salida=limpiador.nivel_db,
                             voz=limpiador.voz_activa, snr=limpiador.relacion_senal_ruido_db)

        hilo = FuenteHilo(fuente, al_bloque)
        hilo.iniciar()
        print(color(f"\n  Fuente: {fuente.nombre}", "negrita"))
        print(color("  Guarde silencio 2 segundos para medir el ruido; luego cante o hable.", "amarillo"))
        print(color("  Presione cualquier tecla para terminar.\n", "tenue"))
        try:
            while hilo.activo:
                with candado:
                    actual = dict(datos)
                estado = "calibrando" if not limpiador.calibrado else (
                    color("VOZ", "verde", "negrita") if actual["voz"] else color("silencio", "tenue"))
                print(f"\r  entrada {actual['entrada']:6.1f} dB {barra(actual['entrada'])}  "
                      f"limpio {actual['salida']:6.1f} dB  SNR {actual['snr']:5.1f} dB  {estado}     ",
                      end="", flush=True)
                if self.teclado.tecla(0.2) is not None:
                    break
        finally:
            hilo.detener()
            print()
        if hilo.error:
            consola.error(f"Error de audio: {hilo.error}")
        time.sleep(0.1)
        self.teclado.pausa()
