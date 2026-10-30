"""Ejecuta el modo automático SIN pantalla sobre un archivo de audio y muestra
cada decisión con su tiempo: qué canción identificó, cuándo cambió de línea,
cuándo se pausó y qué aprendió. Sirve para medir el modo automático con una
canción real (se usa en GitHub Actions) o con un guion de texto.

Uso:
    python herramientas/simular_automatico.py ejemplos/Sound_of_You.mp3
    python herramientas/simular_automatico.py ejemplos/Ghost_of_you_Remastered.mp3 --motor whisper
    python herramientas/simular_automatico.py --guion guion.txt
    KaraokeInteligente.exe --simular ejemplos\\Sound_of_You.mp3
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from .audio.fuentes import FuenteArchivo
from .audio.motores import MotorSimulado
from .audio.proceso import ProcesadorAudio, crear_limpiador, crear_motores
from .automatico import ControladorAutomatico
from .buscador import Buscador
from .config import carpeta_programa, cargar_config
from .db import BaseDatos
from .importador import importar_archivo
from .programa import cargar_programa
from .sesion import SesionKaraoke


def reloj(segundo: float) -> str:
    return f"{int(segundo // 60)}:{segundo % 60:04.1f}"


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simular", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", nargs="?")
    parser.add_argument("--guion", help="usa el motor simulado con este guion en vez de audio")
    parser.add_argument("--canciones", default=str(carpeta_programa() / "ejemplos" / "canciones.txt"))
    parser.add_argument("--programa", nargs="*", default=[], help="nombres de canciones del programa")
    parser.add_argument("--carpeta", default=str(carpeta_programa()))
    parser.add_argument("--motor", choices=["hibrido", "vosk", "whisper"])
    opciones = parser.parse_args(argumentos)
    if not opciones.audio and not opciones.guion:
        parser.error("indique un archivo de audio o --guion")

    config = cargar_config(Path(opciones.carpeta), crear=False)
    if opciones.motor:
        config.establecer("audio", "motor", opciones.motor)
    with tempfile.TemporaryDirectory() as temporal:
        bd = BaseDatos(Path(temporal) / "CANCIONES.db")
        importar_archivo(bd, opciones.canciones, config)
        if opciones.programa:
            cargar_programa(bd, opciones.programa)
        buscador = Buscador(bd, config)
        sesion = SesionKaraoke(bd, "automatico")

        if opciones.guion:
            motor = MotorSimulado(opciones.guion)
            motores = [motor]
            duracion = motor.duracion + 15
            fuente = None
        else:
            idiomas = sorted({c.idioma for c in bd.todas_las_letras().values()})
            motores, avisos = crear_motores(config, idiomas, sincrono=True)
            for aviso in avisos:
                print("Aviso:", aviso)
            fuente = FuenteArchivo(opciones.audio, tiempo_real=False,
                                   aislar_voz=config.booleano("audio", "aislar_voz_archivo"))
            fuente.iniciar()
            duracion = fuente.duracion
        nombres = " + ".join(m.nombre for m in motores)
        control = ControladorAutomatico(bd, buscador, config, sesion, nombres)
        print(f"Audio: {opciones.audio or opciones.guion} ({duracion:.0f} s) · motores: {nombres}")

        procesador = ProcesadorAudio(fuente, crear_limpiador(config, fuente) if fuente else None, motores) \
            if fuente else None
        inicio = time.monotonic()
        anterior = None
        avisos_vistos: set[str] = set()
        segundo = 0.0
        silencio = np.zeros(1600, dtype=np.float32)
        while True:
            if procesador is not None:
                resultado = procesador.paso()
                segundo, voz, transcripciones = resultado.segundo, resultado.voz, resultado.transcripciones
                terminado = resultado.terminado
            else:
                segundo += 0.1
                transcripciones = motores[0].procesar(silencio)
                voz = bool(transcripciones) or any(
                    f.inicio <= segundo <= f.inicio + len(f.palabras) * 0.35 + 0.5 for f in motores[0].frases)
                terminado = segundo >= duracion
            for t in transcripciones:
                control.recibir(t, retraso=max(0.0, segundo - t.segundo))
            control.tic(segundo, voz)
            if control.vocabulario_pedido is not None and procesador is not None:
                procesador.pedir_vocabulario(*control.vocabulario_pedido)
                control.vocabulario_pedido = None

            pantalla = control.pantalla()
            for aviso in pantalla.avisos:
                if aviso not in avisos_vistos:
                    avisos_vistos.add(aviso)
                    print(f"{reloj(segundo)}  ** {aviso}")
            actual = (pantalla.estado, pantalla.cancion.codigo if pantalla.cancion else None, pantalla.linea)
            if actual != anterior:
                anterior = actual
                texto = ""
                if pantalla.cancion and pantalla.linea < len(pantalla.cancion.lineas):
                    texto = pantalla.cancion.lineas[pantalla.linea]
                print(f"{reloj(segundo)}  [{pantalla.estado:<11}] "
                      f"{('línea ' + str(pantalla.linea + 1)) if pantalla.cancion else '':<9} {texto}")
            if terminado:
                break
        control.finalizar()
        print(f"\nProcesado en {time.monotonic() - inicio:.0f} s.")
        for numero, cantada in enumerate(sesion.cantadas, 1):
            print(f"  {numero}. {cantada.nombre} · {'completa' if cantada.completada else 'incompleta'} · "
                  f"{cantada.lineas_mostradas} cambios de línea")
        for temporal in bd.listar_temporales():
            print(f"  Aprendida: «{temporal.nombre_sugerido}» ({len(temporal.lineas)} líneas)")
        bd.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
