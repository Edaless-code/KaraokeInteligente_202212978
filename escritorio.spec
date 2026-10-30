# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: versión de escritorio con interfaz gráfica (Kivy) para Windows.
# Se construye con:  pyinstaller --noconfirm escritorio.spec
# Su carpeta interna se llama "_escritorio" para poder vivir junto a la versión
# de consola (KaraokeInteligente.exe + _internal) y compartir sus datos.

from kivy_deps import angle, glew, sdl2
from kivy.tools.packaging.pyinstaller_hooks import get_deps_all, hookspath, runtime_hooks
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
kivy = get_deps_all()

a = Analysis(
    ["movil/main.py"],
    pathex=[".", "movil"],
    binaries=binaries,
    datas=datas,
    hiddenimports=ocultos + kivy["hiddenimports"],
    excludes=kivy["excludes"],
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
