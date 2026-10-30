"""Pantalla base y encabezado con título grande."""

from __future__ import annotations

from kivy.app import App
from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen


class EncabezadoGrande(BoxLayout):
    antetitulo = StringProperty("")
    titulo = StringProperty("")
    # El antetítulo se muestra en mayúsculas (se calcula aquí: en el KV la
    # expresión "root.antetitulo.upper()" no se actualiza al cambiar el valor).
    antetitulo_mayusculas = StringProperty("")

    def on_antetitulo(self, *_):
        self.antetitulo_mayusculas = self.antetitulo.upper()


class Pantalla(Screen):
    """Cada pantalla indica si muestra la barra de pestañas."""

    con_pestanas = BooleanProperty(True)
    titulo = StringProperty("")

    @property
    def app(self):
        return App.get_running_app()

    def al_entrar(self, **datos) -> None:
        """Se llama cada vez que se navega a la pantalla."""

    def refrescar(self) -> None:
        """Se llama cuando cambian los datos."""


Builder.load_string("""
#:import T app.tema

<Pantalla>:
    canvas.before:
        Color:
            rgba: T.FONDO
        Rectangle:
            pos: self.pos
            size: self.size

<EncabezadoGrande>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: 0, T.ESP["l"], 0, T.ESP["s"]
    spacing: T.ESP["xs"]
    Texto:
        tipo: "mini"
        tono: T.ACENTO
        text: root.antetitulo_mayusculas
    Texto:
        tipo: "titulo_grande"
        text: root.titulo
""")
