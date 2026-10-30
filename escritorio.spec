# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: versión de escritorio con interfaz gráfica (Kivy) para Windows.
# Se construye con:  pyinstaller --noconfirm escritorio.spec
# Su carpeta interna se llama "_escritorio" para poder vivir junto a la versión
# de consola (KaraokeInteligente.exe + _internal) y compartir sus datos.

from kivy_deps import angle, glew, sdl2
from kivy.tools.packaging.pyinstaller_hooks import hookspath, runtime_hooks
from PyInstaller.utils.hooks import (collect_all, collect_data_files, collect_dynamic_libs,
                                     collect_submodules)

datas = [("movil/recursos", "recursos")]
binaries = collect_dynamic_libs("sounddevice")
datas += collect_data_files("_sounddevice_data")
ocultos = collect_submodules("karaoke") + collect_submodules("app")
for paquete in ("faster_whisper", "ctranslate2"):
    d, b, h = collect_all(paquete)
    datas += d
    binaries += b
    ocultos += h
# Proveedores de Kivy que usa la app en Windows. Se listan a mano: la ayuda
# get_deps_all() importa kivy.core.window al empaquetar y en un servidor sin
# pantalla eso abre (o intenta abrir) una ventana y el empaquetado se queda colgado.
kivy_ocultos = [
    "kivy.core.window.window_sdl2",
    "kivy.core.text.text_sdl2",
    "kivy.core.image.img_sdl2",
    "kivy.core.image.img_tex",
    "kivy.core.clipboard.clipboard_winctypes",
    "kivy.core.clipboard.clipboard_sdl2",
    "kivy.core.audio.audio_sdl2",
    "kivy.uix.anchorlayout",
    "kivy.uix.modalview",
    "kivy.uix.screenmanager",
]
kivy_excluir = ["kivy.core.video", "kivy.core.camera", "cv2", "gi", "ffpyplayer", "gst", "enchant"]

a = Analysis(
    ["movil/main.py"],
    pathex=[".", "movil"],
    binaries=binaries,
    datas=datas,
    hiddenimports=ocultos + kivy_ocultos,
    excludes=kivy_excluir,
    hookspath=hookspath(),
    runtime_hooks=runtime_hooks(),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KaraokeEscritorio",
    console=False,
    icon="movil/recursos/icono.png",
    contents_directory="_escritorio",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *[Tree(p) for p in (sdl2.dep_bins + glew.dep_bins + angle.dep_bins)],
    name="KaraokeEscritorio",
)
