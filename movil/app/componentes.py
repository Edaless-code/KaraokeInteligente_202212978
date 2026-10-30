"""Componentes visuales reutilizables de la app móvil.

Todos toman sus valores de ``tema``. Reglas que se siguen:

* La respuesta al toque es inmediata: el botón se encoge y oscurece al
  PRESIONAR (no al soltar), en 80 ms.
* Jerarquía por peso + tamaño + color, no solo por tamaño.
* Un solo color de acento para la acción principal de cada pantalla.
"""

from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import (BooleanProperty, ColorProperty, ListProperty, NumericProperty,
                             ObjectProperty, OptionProperty, StringProperty)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput

from . import tema as T

KV = """
#:import T app.tema

<Texto>:
    font_name: T.TIPOS[self.tipo][1]
    font_size: T.TIPOS[self.tipo][0]
    color: self.tono
    halign: self.alineacion
    valign: "middle"
    text_size: (self.width, None) if self.envolver else (None, None)
    size_hint_y: None
    height: self.texture_size[1]
    markup: True

<Icono>:
    font_name: T.ICONOS
    text: T.ICONO.get(self.nombre, "")
    font_size: self.tamano
    color: self.tono
    size_hint: None, None
    size: self.tamano * 1.25, self.tamano * 1.25
    halign: "center"
    valign: "middle"
    text_size: self.size

<Tarjeta>:
    orientation: "vertical"
    padding: T.ESP["l"]
    spacing: T.ESP["m"]
    size_hint_y: None
    height: self.minimum_height
    canvas.before:
        Color:
            rgba: self.fondo
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radio]
        Color:
            rgba: T.TRAZO if self.borde else (0, 0, 0, 0)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, self.radio)
            width: 1

<Boton>:
    size_hint_y: None
    height: T.ALTO_BOTON
    padding: T.ESP["l"], 0
    spacing: T.ESP["s"]
    canvas.before:
        PushMatrix
        Scale:
            origin: self.center
            x: self._escala
            y: self._escala
        Color:
            rgba: self._fondo_actual
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.radio]
    canvas.after:
        PopMatrix
    Widget:
    Icono:
        nombre: root.icono
        tono: root._tinta
        tamano: dp(20)
        opacity: 1 if root.icono else 0
        width: (dp(20) * 1.25) if root.icono else 0
        pos_hint: {"center_y": .5}
    Label:
        text: root.texto
        font_name: T.FUENTE_SEMI
        font_size: sp(16)
        color: root._tinta
        size_hint_x: None
        width: self.texture_size[0]
        opacity: 1 if root.texto else 0
    Widget:

<BotonIcono>:
    size_hint: None, None
    size: self.lado, self.lado
    canvas.before:
        PushMatrix
        Scale:
            origin: self.center
            x: self._escala
            y: self._escala
        Color:
            rgba: self._fondo_actual
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.lado / 2]
    canvas.after:
        PopMatrix
    Icono:
        nombre: root.icono
        tono: root.tinta
        tamano: root.lado * 0.44
        center: root.center

<Campo>:
    font_name: T.FUENTE
    font_size: sp(16)
    foreground_color: T.TEXTO
    hint_text_color: T.TEXTO_3
    cursor_color: T.ACENTO
    selection_color: T.ACENTO_SUAVE
    background_normal: ""
    background_active: ""
    background_color: 0, 0, 0, 0
    padding: dp(14), (self.height - self.line_height) / 2 if not self.multiline else dp(12)
    size_hint_y: None
    height: dp(50) if not self.multiline else dp(160)
    write_tab: False
    canvas.before:
        Color:
            rgba: T.SUPERFICIE_ALTA
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [T.RADIO_CAMPO]
        Color:
            rgba: T.ACENTO if self.focus else T.TRAZO
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, T.RADIO_CAMPO)
            width: 1.3 if self.focus else 1

<Chip>:
    size_hint: None, None
    height: dp(26)
    width: self.texture_size[0] + dp(20)
    font_name: T.FUENTE_SEMI
    font_size: sp(12)
    color: self.tono
    canvas.before:
        Color:
            rgba: self.fondo
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height / 2]

<FilaCancion>:
    size_hint_y: None
    height: T.ALTO_FILA
    padding: T.ESP["m"], T.ESP["s"]
    spacing: T.ESP["m"]
    canvas.before:
        Color:
            rgba: T.SUPERFICIE_ALTA if self.state == "down" else (0, 0, 0, 0)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [T.RADIO_BOTON]
    BoxLayout:
        size_hint: None, None
        size: dp(44), dp(44)
        pos_hint: {"center_y": .5}
        canvas.before:
            Color:
                rgba: root.color_insignia
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(12)]
        Label:
            text: root.insignia
            font_name: T.FUENTE_NEGRITA
            font_size: sp(15)
            color: root.color_texto_insignia
    BoxLayout:
        orientation: "vertical"
        padding: 0, dp(6)
        Label:
            text: root.titulo
            font_name: T.FUENTE_SEMI
            font_size: sp(16)
            color: T.TEXTO
            text_size: self.size
            halign: "left"
            valign: "bottom"
            shorten: True
            shorten_from: "right"
        Label:
            text: root.subtitulo
            font_name: T.FUENTE_MEDIA
            font_size: sp(13)
            color: T.TEXTO_2
            text_size: self.size
            halign: "left"
            valign: "top"
            shorten: True
            shorten_from: "right"
    Icono:
        nombre: root.icono_derecho
        tono: T.TEXTO_3
        tamano: dp(20)
        pos_hint: {"center_y": .5}

<FilaLetra>:
    size_hint_y: None
    height: max(numero.height, texto.height)
    spacing: T.ESP["m"]
    Label:
        id: numero
        text: root.numero
        font_name: T.FUENTE_MEDIA
        font_size: sp(14)
        color: T.TEXTO_3
        size_hint: None, None
        width: dp(22)
        height: self.texture_size[1]
        text_size: self.width, None
        halign: "right"
        pos_hint: {"top": 1}
    Texto:
        id: texto
        text: root.texto
        tipo: "cuerpo"
        pos_hint: {"top": 1}

<Separador@Widget>:
    size_hint_y: None
    height: 1
    canvas:
        Color:
            rgba: T.TRAZO
        Rectangle:
            pos: self.x + dp(68), self.y
            size: self.width - dp(68), 1

<Pestana>:
    orientation: "vertical"
    padding: 0, dp(8), 0, dp(6)
    spacing: dp(2)
    Icono:
        nombre: root.icono
        tamano: dp(24)
        tono: T.ACENTO if root.activa else T.TEXTO_3
        pos_hint: {"center_x": .5}
    Label:
        text: root.texto
        font_name: T.FUENTE_SEMI
        font_size: sp(11)
        color: T.ACENTO if root.activa else T.TEXTO_3
        size_hint_y: None
        height: dp(16)

<BarraPestanas>:
    size_hint_y: None
    height: dp(64)
    canvas.before:
        Color:
            rgba: T.color("#0E0E15", 0.97)
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: T.TRAZO
        Rectangle:
            pos: self.x, self.top - 1
            size: self.width, 1

<Dialogo>:
    background: ""
    background_color: T.VELO
    overlay_color: 0, 0, 0, 0
    size_hint: None, None
    width: min(dp(360), root.parent.width - dp(40)) if root.parent else dp(320)
    height: caja.minimum_height
    auto_dismiss: True
    BoxLayout:
        id: caja
        orientation: "vertical"
        padding: T.ESP["xl"], T.ESP["xl"], T.ESP["xl"], T.ESP["l"]
        spacing: T.ESP["m"]
        size_hint_y: None
        height: self.minimum_height
        canvas.before:
            Color:
                rgba: T.SUPERFICIE_ALTA
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [T.RADIO_TARJETA]
        Icono:
            nombre: root.icono
            tamano: dp(30)
            tono: root.tono
            pos_hint: {"center_x": .5}
            opacity: 1 if root.icono else 0
        Texto:
            tipo: "encabezado"
            text: root.titulo
            alineacion: "center"
        Texto:
            tipo: "cuerpo"
            tono: T.TEXTO_2
            text: root.mensaje
            alineacion: "center"
        BoxLayout:
            id: botones
            orientation: "vertical"
            spacing: T.ESP["s"]
            size_hint_y: None
            height: self.minimum_height
            padding: 0, T.ESP["s"], 0, 0

<Aviso>:
    size_hint: None, None
    height: dp(46)
    width: min(etiqueta.texture_size[0] + dp(56), self.parent.width - dp(32)) if self.parent else dp(300)
    opacity: 0
    canvas.before:
        Color:
            rgba: T.color("#2A2A38", 0.98)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height / 2]
    Icono:
        nombre: root.icono
        tono: root.tono
        tamano: dp(18)
        pos: root.x + dp(14), root.center_y - self.height / 2
    Label:
        id: etiqueta
        text: root.texto
        font_name: T.FUENTE_MEDIA
        font_size: sp(14)
        color: T.TEXTO
        size_hint: None, None
        size: root.width - dp(52), root.height
        pos: root.x + dp(40), root.y
        text_size: self.size
        valign: "middle"
        shorten: True
"""


class Texto(Label):
    tipo = StringProperty("cuerpo")
    tono = ColorProperty(T.TEXTO)
    alineacion = StringProperty("left")
    envolver = BooleanProperty(True)


class Icono(Label):
    nombre = StringProperty("")
    tamano = NumericProperty(24)
    tono = ColorProperty(T.TEXTO)


class Tarjeta(BoxLayout):
    fondo = ColorProperty(T.SUPERFICIE)
    radio = NumericProperty(T.RADIO_TARJETA)
    borde = BooleanProperty(True)


class _Presionable(ButtonBehavior):
    """Respuesta inmediata al presionar: escala 0.97 y oscurece."""

    _escala = NumericProperty(1.0)
    _fondo_actual = ColorProperty((0, 0, 0, 0))

    def _fondo_base(self):
        return (0, 0, 0, 0)

    def on_kv_post(self, *_):
        self._fondo_actual = self._fondo_base()

    def on_state(self, _instancia, estado):
        Animation.cancel_all(self, "_escala")
        base = list(self._fondo_base())
        if estado == "down":
            self._escala = 0.97
            if base[3] == 0:
                base = list(T.color("#FFFFFF", 0.06))
            else:
                base = [c * 0.85 for c in base[:3]] + [base[3]]
            self._fondo_actual = base
        else:
            Animation(_escala=1.0, d=T.DURACION, t=T.CURVA).start(self)
            self._fondo_actual = base


class Boton(_Presionable, BoxLayout):
    texto = StringProperty("")
    icono = StringProperty("")
    estilo = OptionProperty("primario", options=["primario", "secundario", "fantasma", "peligro", "violeta"])
    radio = NumericProperty(T.RADIO_BOTON)
    _tinta = ColorProperty(T.TEXTO)

    _FONDOS = {
        "primario": T.ACENTO, "secundario": T.SUPERFICIE_ALTA, "fantasma": (0, 0, 0, 0),
        "peligro": T.PELIGRO_SUAVE, "violeta": T.VIOLETA,
    }
    _TINTAS = {
        "primario": T.color("#FFFFFF"), "secundario": T.TEXTO, "fantasma": T.ACENTO,
        "peligro": T.PELIGRO, "violeta": T.color("#FFFFFF"),
    }

    def _fondo_base(self):
        return self._FONDOS[self.estilo]

    def on_estilo(self, *_):
        self._fondo_actual = self._fondo_base()
        self._tinta = self._TINTAS[self.estilo]

    def on_kv_post(self, *_):
        super().on_kv_post()
        self.on_estilo()


class BotonIcono(_Presionable, FloatLayout):
    icono = StringProperty("")
    lado = NumericProperty(48)
    fondo = ColorProperty(T.SUPERFICIE_ALTA)
    tinta = ColorProperty(T.TEXTO)

    def _fondo_base(self):
        return self.fondo

    def on_fondo(self, *_):
        self._fondo_actual = self.fondo


class Campo(TextInput):
    pass


class Chip(Label):
    fondo = ColorProperty(T.SUPERFICIE_ALTA)
    tono = ColorProperty(T.TEXTO_2)


class FilaCancion(ButtonBehavior, BoxLayout):
    insignia = StringProperty("")
    titulo = StringProperty("")
    subtitulo = StringProperty("")
    icono_derecho = StringProperty("chevron-right")
    color_insignia = ColorProperty(T.ACENTO_SUAVE)
    color_texto_insignia = ColorProperty(T.ACENTO)
    dato = ObjectProperty(None, allownone=True)


class FilaLetra(BoxLayout):
    """Línea de la letra con su número en una columna aparte (si la línea
    ocupa dos renglones, el segundo no se mete debajo del número)."""

    numero = StringProperty("")
    texto = StringProperty("")


class Pestana(ButtonBehavior, BoxLayout):
    icono = StringProperty("")
    texto = StringProperty("")
    activa = BooleanProperty(False)
    nombre = StringProperty("")


class BarraPestanas(BoxLayout):
    al_elegir = ObjectProperty(None, allownone=True)
    pestanas = ListProperty([])

    def construir(self, pestanas: list[tuple[str, str, str]]) -> None:
        self.clear_widgets()
        for nombre, icono, texto in pestanas:
            pestana = Pestana(nombre=nombre, icono=icono, texto=texto)
            pestana.bind(on_press=lambda p: self.al_elegir and self.al_elegir(p.nombre))
            self.add_widget(pestana)

    def marcar(self, nombre: str) -> None:
        for pestana in self.children:
            pestana.activa = pestana.nombre == nombre


class Dialogo(ModalView):
    titulo = StringProperty("")
    mensaje = StringProperty("")
    icono = StringProperty("")
    tono = ColorProperty(T.ACENTO)

    def agregar_boton(self, texto: str, estilo: str = "secundario", accion=None) -> Boton:
        boton = Boton(texto=texto, estilo=estilo)

        def pulsar(*_):
            self.dismiss()
            if accion:
                accion()

        boton.bind(on_release=pulsar)
        self.ids.botones.add_widget(boton)
        return boton


def confirmar(titulo: str, mensaje: str, texto_si: str, accion, peligro: bool = False,
              icono: str = "alert-circle-outline") -> Dialogo:
    """Diálogo de confirmación: la acción destructiva en rojo y "Cancelar"
    siempre disponible (se puede cerrar tocando fuera)."""
    dialogo = Dialogo(titulo=titulo, mensaje=mensaje, icono=icono,
                      tono=T.PELIGRO if peligro else T.ACENTO)
    dialogo.agregar_boton(texto_si, "peligro" if peligro else "primario", accion)
    dialogo.agregar_boton("Cancelar", "fantasma")
    dialogo.open()
    return dialogo


class Aviso(FloatLayout):
    """Mensaje breve flotante (estado, confirmación o error) que aparece y se
    desvanece solo."""

    texto = StringProperty("")
    icono = StringProperty("check-circle")
    tono = ColorProperty(T.EXITO)

    def mostrar(self, texto: str, tipo: str = "exito", segundos: float = 2.4) -> None:
        estilos = {"exito": ("check-circle", T.EXITO), "error": ("alert-circle-outline", T.PELIGRO),
                   "info": ("information-outline", T.VIOLETA)}
        self.icono, self.tono = estilos.get(tipo, estilos["info"])
        self.texto = texto
        Animation.cancel_all(self)
        Animation(opacity=1, d=0.18, t=T.CURVA).start(self)
        Clock.unschedule(self._ocultar)
        Clock.schedule_once(self._ocultar, segundos)

    def _ocultar(self, *_):
        Animation(opacity=0, d=0.25, t=T.CURVA).start(self)


Builder.load_string(KV)
