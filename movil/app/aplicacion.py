"""Aplicación Kivy: datos, navegación y pestañas."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from kivy.app import App
from kivy.core.window import Window
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import NoTransition, ScreenManager, SlideTransition
from kivy.utils import platform

from . import tema as T

T.registrar_fuentes()

from . import componentes  # noqa: E402,F401 -- registra los estilos
from .componentes import Aviso, BarraPestanas  # noqa: E402

PESTANAS = [
    ("inicio", "microphone", "Cantar"),
    ("biblioteca", "bookshelf", "Biblioteca"),
    ("programa", "playlist-music", "Programa"),
    ("mas", "dots-horizontal", "Más"),
]


class KaraokeApp(App):
    title = "Karaoke Inteligente"

    # ------------------------------------------------------------ datos
    def preparar_datos(self) -> None:
        carpeta = Path(os.environ.get("KARAOKE_HOME") or self.user_data_dir)
        carpeta.mkdir(parents=True, exist_ok=True)
        os.environ["KARAOKE_HOME"] = str(carpeta)
        ejemplos = Path(__file__).resolve().parent.parent / "ejemplos"
        destino = carpeta / "ejemplos"
        if ejemplos.exists() and not destino.exists():
            shutil.copytree(ejemplos, destino)
        if not (carpeta / "canciones.txt").exists() and (destino / "canciones.txt").exists():
            shutil.copy(destino / "canciones.txt", carpeta / "canciones.txt")

        from karaoke.buscador import Buscador
        from karaoke.config import cargar_config
        from karaoke.db import BaseDatos

        self.config_karaoke = cargar_config(carpeta)
        self.bd = BaseDatos(self.config_karaoke.ruta_bd)
        self.bd_nueva = not self.bd.existia
        self.buscador = Buscador(self.bd, self.config_karaoke)
        self.carpeta = carpeta

    # ------------------------------------------------------------ interfaz
    def build(self):
        Window.clearcolor = T.FONDO
        if platform not in ("android", "ios"):
            ancho, alto = (os.environ.get("KARAOKE_VENTANA") or "392x848").split("x")
            Window.size = (int(dp(int(ancho))), int(dp(int(alto))))
        self.preparar_datos()

        from .pantallas.biblioteca import Biblioteca, DetalleCancion
        from .pantallas.inicio import Inicio

        self.gestor = ScreenManager(transition=NoTransition())
        for pantalla in (Inicio(name="inicio"), Biblioteca(name="biblioteca"),
                         DetalleCancion(name="detalle")):
            self.gestor.add_widget(pantalla)
        self._registrar_pantallas_extra()

        self.pestanas = BarraPestanas()
        self.pestanas.construir(PESTANAS)
        self.pestanas.al_elegir = self.ir_pestana

        columna = BoxLayout(orientation="vertical")
        columna.add_widget(self.gestor)
        columna.add_widget(self.pestanas)
        raiz = FloatLayout()
        raiz.add_widget(columna)
        self.aviso = Aviso(pos_hint={"center_x": 0.5, "y": 0.11})
        raiz.add_widget(self.aviso)

        self.historial: list[str] = []
        Window.bind(on_keyboard=self._tecla)
        self.ir_pestana("inicio")
        if self.bd_nueva:
            self.avisar("Base de datos CANCIONES creada", "info")
        return raiz

    def _registrar_pantallas_extra(self) -> None:
        """Pantallas que se agregan en los pasos siguientes."""
        import importlib

        for modulo, clases in (
            ("programa", ("ProgramaPantalla",)),
            ("mas", ("MasPantalla", "Historial", "Papelera", "Ajustes", "AcercaDe")),
            ("editor", ("EditorCancion", "NuevaCancion", "Importar")),
            ("escenario", ("BuscarCancion", "Escenario")),
        ):
            try:
                paquete = importlib.import_module(f"app.pantallas.{modulo}")
            except ImportError as ex:
                Logger.warning(f"Karaoke: no se cargó la pantalla {modulo}: {ex}")
                continue
            for nombre in clases:
                clase = getattr(paquete, nombre)
                self.gestor.add_widget(clase(name=clase.nombre_pantalla))

    # ---------------------------------------------------------- navegación
    def ir_pestana(self, nombre: str) -> None:
        if not self.gestor.has_screen(nombre):
            return
        self.historial = []
        self.gestor.transition = NoTransition()
        self._mostrar(nombre)

    def abrir(self, nombre: str, **datos) -> None:
        """Abre una pantalla encima de la actual (se regresa con atrás)."""
        self.historial.append(self.gestor.current)
        self.gestor.transition = SlideTransition(direction="left", duration=T.DURACION)
        self._mostrar(nombre, **datos)

    def atras(self) -> bool:
        if not self.historial:
            return False
        anterior = self.historial.pop()
        self.gestor.transition = SlideTransition(direction="right", duration=T.DURACION)
        self._mostrar(anterior)
        return True

    def _mostrar(self, nombre: str, **datos) -> None:
        pantalla = self.gestor.get_screen(nombre)
        pantalla.al_entrar(**datos)
        self.gestor.current = nombre
        self.pestanas.opacity = 1 if pantalla.con_pestanas else 0
        self.pestanas.disabled = not pantalla.con_pestanas
        self.pestanas.height = dp(64) if pantalla.con_pestanas else 0
        if pantalla.con_pestanas and not self.historial:
            self.pestanas.marcar(nombre)

    def _tecla(self, _ventana, tecla, *_):
        if tecla == 27:  # botón "atrás" de Android / Escape
            return self.atras()
        return False

    # -------------------------------------------------------------- avisos
    def avisar(self, texto: str, tipo: str = "exito") -> None:
        self.aviso.mostrar(texto, tipo)

    def datos_cambiaron(self) -> None:
        for pantalla in self.gestor.screens:
            pantalla.refrescar()

    def on_stop(self):
        try:
            self.bd.cerrar()
        except Exception:
            pass
