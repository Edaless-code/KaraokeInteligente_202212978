"""Modo alimentación → (m): agregar canciones desde archivos de audio.

Se elige un archivo o una carpeta completa; cada pista se transcribe con la IA
y se muestra el borrador de la letra para revisarlo antes de guardarlo:

    g guardar · e editar la letra · l usar mi letra · n cambiar el nombre ·
    v dejar para revisar después (f → v) · d descartar

Si el autor tiene la letra escrita (un .txt con el mismo nombre junto al
audio, o con la opción l) se usa esa letra, exacta, y la IA solo calcula en
qué segundo empieza cada línea para mostrarla a tiempo.

Si la canción ya existe (por ejemplo, se cargó desde canciones.txt) se ofrece
solo asociarle la pista, sin tocar su letra.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..db import CancionDuplicada, CancionEnPapelera
from . import consola
from .consola import color

if TYPE_CHECKING:
    from ..audio.desde_audio import Borrador
    from .menus import Aplicacion

IDIOMAS = {"": None, "a": None, "es": "es", "e": "es", "en": "en", "i": "en"}


def _duracion(segundos: float) -> str:
    return f"{int(segundos // 60)}:{int(segundos % 60):02d}"


class AgregarDesdeAudio:
    def __init__(self, app: Aplicacion):
        self.app = app
        self.bd = app.bd
        self.config = app.config
        self.teclado = app.teclado

    def ejecutar(self) -> None:
        try:  # NumPy y el lector de audio solo se necesitan aquí
            from ..audio import desde_audio
        except ImportError as ex:
            consola.error(f"Falta un componente de audio: {ex}")
            self.teclado.pausa()
            return
        consola.limpiar()
        consola.titulo("Agregar canciones desde audio", "MP3 · WAV · FLAC · OGG")
        print("  Escriba la ruta de un archivo de audio o de una carpeta con varios.")
        print(color("  Consejo: en Windows puede arrastrar el archivo a esta ventana.", "tenue"))
        print()
        texto = self.app.preguntar("  Archivo o carpeta: ").strip().strip('"').strip("'")
        if not texto:
            return
        ruta = Path(texto).expanduser()
        if not ruta.is_absolute() and not ruta.exists():
            ruta = self.config.carpeta / ruta
        archivos = desde_audio.buscar_audios(ruta)
        if not archivos:
            consola.error(f"No se encontraron archivos de audio en {ruta}")
            self.teclado.pausa()
            return
        print()
        for archivo in archivos:
            print(color(f"    ♪ {archivo.name}", "blanco"))
        respuesta = self.app.preguntar("\n  Idioma de las canciones (es / en, Enter = detectarlo solo): ").lower()
        idioma = IDIOMAS.get(respuesta, None)
        guardadas = 0
        for numero, archivo in enumerate(archivos, 1):
            borrador = self._transcribir(desde_audio, archivo, idioma, numero, len(archivos))
            if borrador is not None and self._revisar(desde_audio, borrador):
                guardadas += 1
        consola.limpiar()
        consola.titulo("Agregar canciones desde audio")
        consola.exito(f"  Listo: {guardadas} de {len(archivos)} pista(s) guardada(s).")
        self.teclado.pausa()

    def _transcribir(self, modulo, archivo: Path, idioma: str | None, numero: int, total: int) -> Borrador | None:
        consola.limpiar()
        consola.titulo("Transcribiendo con inteligencia artificial", f"{numero} de {total}")
        print(f"  ♪ {archivo.name}")
        print(color("  Se escucha la canción completa; puede tardar alrededor de un minuto.", "tenue"))
        print()

        def progreso(fraccion: float) -> None:
            llenas = int(fraccion * 30)
            print(f"\r  {'━' * llenas}{'─' * (30 - llenas)} {int(fraccion * 100):>3} %", end="", flush=True)

        try:
            borrador = modulo.crear_borrador(archivo, self.config, idioma, progreso)
        except Exception as ex:  # audio dañado, sin modelos, etc.
            print()
            consola.error(f"  No se pudo transcribir {archivo.name}: {ex}")
            self.teclado.pausa()
            return None
        print()
        propia = modulo.letra_junto_al_audio(archivo)
        if propia:
            borrador.usar_letra(propia)
            consola.exito(f"  Se usó tu letra de {archivo.with_suffix('.txt').name}; la IA puso los tiempos.")
            self.teclado.pausa()
        if not borrador.lineas:
            consola.aviso("  La IA no reconoció letra en esta pista (¿es instrumental?).")
            self.teclado.pausa()
            return None
        return borrador

    def _mostrar(self, borrador: Borrador) -> None:
        consola.limpiar()
        consola.titulo(f"Borrador: {borrador.nombre}",
                       f"{_duracion(borrador.duracion)} · {borrador.idioma} · {borrador.motor}")
        print(color("  Revise la letra: la IA puede equivocarse en algunas palabras.", "tenue"))
        print()
        tiempos = borrador.tiempos if len(borrador.tiempos) == len(borrador.lineas) else []
        for i, linea in enumerate(borrador.lineas, 1):
            marca = ""
            if tiempos and tiempos[i - 1] is not None:
                marca = f"{int(tiempos[i - 1] // 60)}:{tiempos[i - 1] % 60:04.1f}  "
            print(f"  {color(f'{i:>3}', 'tenue')}  {color(marca, 'tenue')}{linea}")
        print()
        print(color("  g guardar · e editar la letra · l usar mi letra (exacta) · n cambiar el nombre · "
                    "v revisar después (f → v) · d descartar", "cian"))

    def _revisar(self, modulo, borrador: Borrador) -> bool:
        """Devuelve True si la canción (o su pista) quedó guardada."""
        while True:
            self._mostrar(borrador)
            orden = self.app.preguntar("  Opción: ").lower()[:1]
            if orden == "g":
                if self._guardar(modulo, borrador):
                    return True
            elif orden == "e":
                editado = self.app.editar_lineas(borrador.nombre, list(borrador.lineas), permitir_renombrar=True)
                if editado is not None:
                    borrador.nombre, lineas = editado
                    if lineas != borrador.lineas and borrador.palabras:
                        borrador.usar_letra(lineas)  # los tiempos se recalculan con la letra corregida
                    borrador.lineas = lineas
            elif orden == "l":
                self._usar_mi_letra(borrador)
            elif orden == "n":
                nuevo = self.app.preguntar(f"  Nombre de la canción [{borrador.nombre}]: ")
                borrador.nombre = nuevo or borrador.nombre
            elif orden == "v":
                temporal = self.bd.crear_temporal(borrador.nombre, f"audio ({borrador.motor})")
                for linea in borrador.lineas:
                    self.bd.agregar_linea_temporal(temporal, linea)
                consola.exito("  Quedó en las canciones por revisar (f → v).")
                self.teclado.pausa()
                return False
            elif orden == "d":
                if self.teclado.confirmar("  ¿Descartar este borrador?"):
                    return False

    def _usar_mi_letra(self, borrador: Borrador) -> None:
        print(color("  Escriba la ruta de un .txt con la letra, o Enter para escribirla aquí.", "tenue"))
        texto = self.app.preguntar("  Archivo de la letra: ").strip().strip('"')
        if texto:
            from ..texto import es_etiqueta, leer_texto

            try:
                lineas = [r.strip() for r in leer_texto(texto).splitlines()
                          if r.strip() and not es_etiqueta(r) and not r.lstrip().startswith(("//", "#"))]
            except (OSError, ValueError) as ex:
                consola.error(f"  No se pudo leer: {ex}")
                self.teclado.pausa()
                return
        else:
            lineas = self.app.leer_lineas()
        if lineas:
            borrador.usar_letra(lineas)

    def _guardar(self, modulo, borrador: Borrador) -> bool:
        existente = self.bd.existe_nombre(borrador.nombre)
        if existente is not None:
            consola.aviso(f"  Ya existe la canción [{existente}] «{borrador.nombre}».")
            if self.teclado.confirmar("  ¿Asociarle esta pista y sincronizar su letra (sin cambiarla)?"):
                cancion = self.bd.obtener_cancion(existente)
                if cancion and borrador.palabras:
                    self.bd.guardar_tiempos(existente, modulo.tiempos_para(
                        cancion.lineas, borrador.palabras, borrador.duracion))
                return self._asociar_pista(modulo, borrador, existente)
            consola.aviso("  Cambie el nombre con (n) para guardarla como otra canción.")
            self.teclado.pausa()
            return False
        try:
            codigo = self.bd.agregar_cancion(borrador.nombre, borrador.lineas, origen="audio",
                                             idioma=borrador.idioma)
        except CancionEnPapelera as ex:
            consola.error(f"  «{ex.nombre}» está en la papelera (b → P para restaurarla).")
            self.teclado.pausa()
            return False
        except (CancionDuplicada, ValueError) as ex:
            consola.error(f"  {ex}")
            self.teclado.pausa()
            return False
        if len(borrador.tiempos) == len(borrador.lineas) and None not in borrador.tiempos:
            self.bd.guardar_tiempos(codigo, borrador.tiempos)
        self._asociar_pista(modulo, borrador, codigo, avisar=False)
        consola.exito(f"  Guardada con el código {codigo} ({len(borrador.lineas)} líneas) y su pista de audio.")
        self.teclado.pausa()
        return True

    def _asociar_pista(self, modulo, borrador: Borrador, codigo: int, avisar: bool = True) -> bool:
        try:
            relativa = modulo.guardar_pista(borrador.archivo, self.config, codigo, borrador.nombre)
        except OSError as ex:
            consola.error(f"  No se pudo copiar la pista: {ex}")
            self.teclado.pausa()
            return False
        self.bd.guardar_pista(codigo, relativa)
        if avisar:
            consola.exito(f"  Pista asociada a la canción {codigo}: {relativa}")
            self.teclado.pausa()
        return True
