"""Pestaña "Cantar": punto de partida de una sesión de karaoke."""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import BooleanProperty, ColorProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout

from .. import tema as T
from .base import Pantalla


class TarjetaModo(ButtonBehavior, BoxLayout):
    icono = StringProperty("")
    titulo = StringProperty("")
    descripcion = StringProperty("")
    acento = ColorProperty(T.ACENTO)
    acento_suave = ColorProperty(T.ACENTO_SUAVE)

Builder.load_string("""
#:import T app.tema

<TarjetaModo>:
    size_hint_y: None
    height: dp(96)
    padding: T.ESP["l"]
    spacing: T.ESP["l"]
    canvas.before:
        Color:
            rgba: T.SUPERFICIE_ALTA if self.state == "down" else T.SUPERFICIE
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [T.RADIO_TARJETA]
        Color:
            rgba: T.TRAZO
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, T.RADIO_TARJETA)
    AnchorLayout:
        size_hint: None, None
        size: dp(56), dp(56)
        pos_hint: {"center_y": .5}
        canvas.before:
            Color:
                rgba: root.acento_suave
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(16)]
        Icono:
            nombre: root.icono
            tamano: dp(26)
            tono: root.acento
    BoxLayout:
        orientation: "vertical"
        spacing: dp(2)
        Widget:
        Texto:
            tipo: "encabezado"
            text: root.titulo
        Texto:
            tipo: "nota"
            tono: T.TEXTO_2
            text: root.descripcion
        Widget:
    Icono:
        nombre: "chevron-right"
        tono: T.TEXTO_3
        tamano: dp(22)
        pos_hint: {"center_y": .5}

<Inicio>:
    ScrollView:
        do_scroll_x: False
        BoxLayout:
            orientation: "vertical"
            padding: T.ESP["l"], T.ESP["xl"], T.ESP["l"], T.ESP["xl"]
            spacing: T.ESP["l"]
            size_hint_y: None
            height: self.minimum_height

            EncabezadoGrande:
                antetitulo: "Karaoke Inteligente"
                titulo: "¿Qué cantamos hoy?"

            BoxLayout:
                size_hint_y: None
                height: dp(26)
                spacing: T.ESP["s"]
                Chip:
                    text: root.resumen_canciones
                Chip:
                    text: root.resumen_programa
                    opacity: 1 if root.resumen_programa else 0
                Chip:
                    text: root.resumen_temporales
                    fondo: T.AVISO_SUAVE
                    tono: T.AVISO
                    opacity: 1 if root.resumen_temporales else 0
                Widget:

            Tarjeta:
                opacity: 1 if root.hay_siguiente else 0
                disabled: not root.hay_siguiente
                height: self.minimum_height if root.hay_siguiente else 0
                padding: T.ESP["l"] if root.hay_siguiente else 0
                fondo: T.ACENTO_SUAVE
                borde: False
                Texto:
                    tipo: "mini"
                    tono: T.ACENTO
                    text: "SIGUIENTE EN EL PROGRAMA"
                Texto:
                    tipo: "titulo"
                    text: root.siguiente
                Boton:
                    texto: "Cantar ahora"
                    icono: "play"
                    on_release: root.cantar_siguiente()

            Texto:
                tipo: "nota"
                tono: T.TEXTO_3
                text: "ELIGE CÓMO SEGUIR LA LETRA"

            TarjetaModo:
                icono: "gesture-tap"
                titulo: "Modo manual"
                descripcion: "Escribe 2 o 3 palabras que escuches y avanza con un toque."
                on_release: app.abrir("buscar")

            TarjetaModo:
                icono: "waveform"
                titulo: "Modo automático"
                descripcion: "La IA escucha al cantante, reconoce la canción y la sigue."
                acento: T.VIOLETA
                acento_suave: T.VIOLETA_SUAVE
                on_release: app.abrir("escenario", modo="automatico")

            Tarjeta:
                opacity: 1 if root.resumen_temporales else 0
                height: self.minimum_height if root.resumen_temporales else 0
                padding: T.ESP["l"] if root.resumen_temporales else 0
                fondo: T.AVISO_SUAVE
                borde: False
                Texto:
                    tipo: "encabezado"
                    tono: T.AVISO
                    text: "Canciones aprendidas por revisar"
                Texto:
                    tipo: "nota"
                    tono: T.TEXTO_2
                    text: "El modo automático guardó letras nuevas. Corrígelas y ponles nombre."
                Boton:
                    texto: "Revisar"
                    estilo: "secundario"
                    on_release: app.abrir("importar", seccion="aprendidas")
""")


class Inicio(Pantalla):
    resumen_canciones = StringProperty("")
    resumen_programa = StringProperty("")
    resumen_temporales = StringProperty("")
    siguiente = StringProperty("")
    hay_siguiente = BooleanProperty(False)

    def al_entrar(self, **_):
        self.refrescar()

    def refrescar(self):
        bd = self.app.bd
        total = bd.contar_canciones()
        self.resumen_canciones = f"{total} canción" if total == 1 else f"{total} canciones"
        entradas = bd.obtener_programa()
        pendientes = [e for e in entradas if e.estado == "pendiente" and e.codigo is not None]
        self.resumen_programa = f"{len(pendientes)} en el programa" if entradas else ""
        temporales = len(bd.listar_temporales())
        self.resumen_temporales = f"{temporales} por revisar" if temporales else ""
        self.hay_siguiente = bool(pendientes)
        self.siguiente = pendientes[0].nombre_solicitado if pendientes else ""
        self._codigo_siguiente = pendientes[0].codigo if pendientes else None

    def cantar_siguiente(self):
        if self._codigo_siguiente is not None:
            self.app.abrir("escenario", modo="manual", codigo=self._codigo_siguiente, linea=0)
