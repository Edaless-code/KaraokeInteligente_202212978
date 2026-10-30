"""Toma capturas de pantalla de la app móvil (para revisar el diseño).

Uso (en Linux sin pantalla):  xvfb-run -s "-screen 0 1200x2000x24" python herramientas/capturas_movil.py SALIDA
"""

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = Path(sys.argv[1] if len(sys.argv) > 1 else "capturas").resolve()
SALIDA.mkdir(parents=True, exist_ok=True)
os.environ["KARAOKE_HOME"] = tempfile.mkdtemp()
os.environ.setdefault("KIVY_LOG_MODE", "PYTHON")
sys.path[:0] = [str(RAIZ / "movil"), str(RAIZ)]

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

from app.aplicacion import KaraokeApp  # noqa: E402

PASOS = [l for l in (sys.argv[2] if len(sys.argv) > 2 else "inicio").split(";") if l]


class Capturador(KaraokeApp):
    def on_start(self):
        from karaoke.importador import importar_archivo
        from karaoke.programa import cargar_programa

        importar_archivo(self.bd, RAIZ / "ejemplos" / "canciones.txt", self.config_karaoke)
        cargar_programa(self.bd, ["Ghost of you", "Sound of You"])
        self.datos_cambiaron()
        Clock.schedule_once(lambda *_: self.siguiente(0), 0.8)

    def siguiente(self, indice):
        if indice >= len(PASOS):
            self.stop()
            return
        paso = PASOS[indice]
        nombre, _, codigo = paso.partition(":")
        nombre, _, espera = nombre.partition("@")  # "nombre@25" espera 25 s antes de capturar
        if codigo:
            exec(codigo, {"app": self})
        Clock.schedule_once(lambda *_: self.capturar(nombre, indice), float(espera or 1.0))

    def capturar(self, nombre, indice):
        Window.screenshot(name=str(SALIDA / f"{indice:02d}_{nombre}.png"))
        Clock.schedule_once(lambda *_: self.siguiente(indice + 1), 0.2)


Capturador().run()
