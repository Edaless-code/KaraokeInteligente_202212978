"""Aplicación Kivy: datos, navegación y pestañas."""

from __future__ import annotations

import os
import shutil
import sys
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
from .componentes import Aviso, BarraLateral, BarraPestanas  # noqa: E402

ANCHO_LATERAL = 760  # dp: desde este ancho la navegación pasa a la barra lateral
ANCHO_CONTENIDO = 1180  # dp: en pantallas muy anchas el contenido no se estira más

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
        if os.environ.get("KARAOKE_HOME"):
            carpeta = Path(os.environ["KARAOKE_HOME"])
        elif getattr(sys, "frozen", False):
            # .exe de escritorio: la misma carpeta que la versión de consola
            # (comparten CANCIONES.db, karaoke.ini, modelos y pistas).
            carpeta = Path(sys.executable).resolve().parent
        else:
            carpeta = Path(self.user_data_dir)
        carpeta.mkdir(parents=True, exist_ok=True)
        os.environ["KARAOKE_HOME"] = str(carpeta)
        app_dir = Path(__file__).resolve().parent.parent
        # En desarrollo las pistas de ejemplo están en la carpeta del proyecto.
        ejemplos = next((c for c in (app_dir / "ejemplos", app_dir.parent / "ejemplos")
                         if c.is_dir() and any(c.glob("*.mp3"))), app_dir / "ejemplos")
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
        try:  # las canciones de ejemplo traen su pista: se reproducen con su letra
            from karaoke.pistas import vincular_ejemplos

            vincular_ejemplos(self.bd, self.config_karaoke)
        except Exception as ex:
            Logger.warning(f"Karaoke: no se asociaron las pistas de ejemplo: {ex}")

    # ------------------------------------------------------------ interfaz
    def build(self):
        Window.clearcolor = T.FONDO
        if platform not in ("android", "ios"):
            # Escritorio: ventana amplia (se adapta si se cambia de tamaño).
            ancho, alto = (os.environ.get("KARAOKE_VENTANA") or "1180x760").split("x")
            Window.size = (int(dp(int(ancho))), int(dp(int(alto))))
            Window.minimum_width, Window.minimum_height = dp(360), dp(600)
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
        self.lateral = BarraLateral()
        self.lateral.construir(PESTANAS)
        self.lateral.al_elegir = self.ir_pestana

        # Diseño adaptable: en el teléfono, pestañas abajo; en pantallas
        # anchas, barra lateral (como Apple Music) y contenido con ancho máximo.
        from kivy.uix.anchorlayout import AnchorLayout

        self.marco = AnchorLayout(anchor_x="center")
        self.marco.add_widget(self.gestor)
        columna = BoxLayout(orientation="vertical")
        columna.add_widget(self.marco)
        columna.add_widget(self.pestanas)
        self.cuerpo = BoxLayout(orientation="horizontal")
        self.cuerpo.add_widget(self.lateral)
        self.cuerpo.add_widget(columna)
        raiz = FloatLayout()
        raiz.add_widget(self.cuerpo)
        # Los avisos aparecen arriba: nunca tapan la isla de controles ni las pestañas.
        self.aviso = Aviso(pos_hint={"center_x": 0.5, "top": 0.975})
        raiz.add_widget(self.aviso)

        self.historial: list[str] = []
        self.ancho = False
        Window.bind(on_keyboard=self._tecla, size=lambda *_: self._adaptar())
        self._adaptar()
        self.ir_pestana("inicio")
        if self.bd_nueva:
            self._cargar_ejemplos()
        if os.environ.get("KARAOKE_PRUEBA_SEGUNDOS"):  # prueba automática del .exe
            from kivy.clock import Clock

            def terminar(*_):
                (self.carpeta / "prueba_escritorio.txt").write_text(
                    f"Interfaz mostrada: {Window.width}x{Window.height}, "
                    f"{self.bd.contar_canciones()} canciones\n", encoding="utf-8")
                self.stop()

            Clock.schedule_once(terminar, float(os.environ["KARAOKE_PRUEBA_SEGUNDOS"]))
        return raiz

    def _cargar_ejemplos(self) -> None:
        """Primer uso: base nueva con las canciones de ejemplo (y sus pistas)
        para poder probar todo de inmediato."""
        texto = self.carpeta / "canciones.txt"
        if not texto.exists():
            self.avisar("Base de datos CANCIONES creada", "info")
            return
        from karaoke.importador import importar_archivo

        resultado = importar_archivo(self.bd, texto, self.config_karaoke)
        self.datos_cambiaron()
        self.avisar(f"Base de datos creada con {len(resultado.agregadas)} canciones de ejemplo", "info")

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

    def _adaptar(self) -> None:
        """Acomoda la navegación al ancho de la ventana o del dispositivo."""
        self.ancho = Window.width >= dp(ANCHO_LATERAL)
        self.lateral.width = dp(236) if self.ancho else 0
        self.lateral.opacity = 1 if self.ancho else 0
        self.lateral.disabled = not self.ancho
        disponible = Window.width - self.lateral.width
        self.gestor.size_hint_x = None
        self.gestor.width = min(disponible, dp(ANCHO_CONTENIDO))
        if self.gestor.current:
            self._mostrar_navegacion(self.gestor.current_screen)

    def _mostrar_navegacion(self, pantalla) -> None:
        abajo = pantalla.con_pestanas and not self.ancho
        self.pestanas.opacity = 1 if abajo else 0
        self.pestanas.disabled = not abajo
        self.pestanas.height = dp(64) if abajo else 0
        # El escenario usa toda la pantalla (sin barra lateral) para la letra;
        # las demás pantallas conservan la barra lateral, como Apple Music.
        lateral = self.ancho and pantalla.name != "escenario"
        self.lateral.width = dp(236) if lateral else 0
        self.lateral.opacity = 1 if lateral else 0
        self.lateral.disabled = not lateral
        self.gestor.width = min(Window.width - self.lateral.width, dp(ANCHO_CONTENIDO) if lateral else Window.width)

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
        self._mostrar_navegacion(pantalla)
        if pantalla.con_pestanas and not self.historial:
            self.pestanas.marcar(nombre)
            self.lateral.marcar(nombre)

    def _tecla(self, _ventana, tecla, *_):
        if tecla == 27:  # botón "atrás" de Android / Escape
            return self.atras()
        return False

    # -------------------------------------------------------------- avisos
    def avisar(self, texto: str, tipo: str = "exito") -> None:
        self.aviso.mostrar(texto, tipo)

    def datos_cambiaron(self) -> None:
        try:  # canciones recién importadas: se les asocia su pista de ejemplo
            from karaoke.pistas import vincular_ejemplos

            vincular_ejemplos(self.bd, self.config_karaoke)
        except Exception:
            pass
        for pantalla in self.gestor.screens:
            pantalla.refrescar()

    def on_stop(self):
        try:
            self.bd.cerrar()
        except Exception:
            pass
