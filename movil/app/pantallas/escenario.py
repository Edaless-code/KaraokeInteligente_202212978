"""Buscar la canción (modo manual) y Escenario (la pantalla del karaoke).

El Escenario es la pantalla que ve el público: la línea que toca cantar
grande y centrada, la anterior tenue arriba y las dos siguientes debajo. Al
cambiar de línea la letra sube con una animación corta y suave (sin rebote).

Controles (equivalen a las teclas de la versión de Windows):

* tocar la letra o "Continuar" ..... c (deslizar a la izquierda también)
* Atrás ............................ a (deslizar a la derecha)
* Igual ............................ i
* Repetir .......................... r
* Pausa / Seguir ................... g / s
* cerrar (X) ....................... f, con resumen de la sesión

En modo automático los mismos controles corrigen lo que decide la IA.

Modo "pista" (Reproducir con letra): la canción suena y la letra cambia sola,
cada línea un poco antes de cantarse. Controles: −5 s, voz del artista
(100/75/50/25 %, en la computadora), +5 s, desde el inicio y pausa.

Los controles flotan en una "isla" semitransparente (como Apple Music) que
nunca pasa de cierto ancho; la letra crece con la pantalla (teléfono,
tableta o computadora).
"""

from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ColorProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout

import threading

from karaoke.alineacion import linea_en, tiempos_de_lineas
from karaoke.automatico import (APRENDIENDO, ESPERANDO, IGNORANDO, PAUSA, SIGUIENDO,
                                ControladorAutomatico)
from karaoke.sesion import SesionKaraoke

from .. import tema as T
from ..componentes import Dialogo, FilaCancion
from ..voz import VozAndroid, VozDemostracion, crear_fuente
from .base import Pantalla

Builder.load_string("""
#:import T app.tema

<BarraNavegacion@BoxLayout>:
    size_hint_y: None
    height: dp(56)
    padding: T.ESP["s"], 0
    spacing: T.ESP["s"]

<BuscarCancion>:
    con_pestanas: False
    BoxLayout:
        orientation: "vertical"
        BarraNavegacion:
            BotonIcono:
                icono: "chevron-left"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: app.atras()
            Texto:
                tipo: "encabezado"
                text: "Modo manual"
                pos_hint: {"center_y": .5}
        BoxLayout:
            orientation: "vertical"
            padding: T.ESP["l"], 0, T.ESP["l"], 0
            spacing: T.ESP["m"]
            Texto:
                tipo: "titulo"
                text: "¿Qué está cantando?"
            Texto:
                tipo: "nota"
                tono: T.TEXTO_2
                text: "Escribe 2 o 3 palabras que escuches. Toleramos errores de dedo."
            Campo:
                id: palabras
                hint_text: "Por ejemplo: follow me everywhere"
                multiline: False
                on_text: root.programar_busqueda()
            ScrollView:
                do_scroll_x: False
                BoxLayout:
                    id: resultados
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: T.ESP["xs"]

<Escenario>:
    con_pestanas: False
    BoxLayout:
        orientation: "vertical"

        # ---------------------------------------------------- barra superior
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            padding: T.ESP["s"], 0, T.ESP["l"], 0
            spacing: T.ESP["s"]
            BotonIcono:
                icono: "close"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: root.terminar_sesion()
            BoxLayout:
                orientation: "vertical"
                padding: 0, dp(10)
                Label:
                    text: root.titulo_cancion
                    font_name: T.FUENTE_SEMI
                    font_size: sp(16)
                    color: T.TEXTO
                    text_size: self.size
                    halign: "left"
                    valign: "bottom"
                    shorten: True
                Label:
                    text: root.subtitulo
                    font_name: T.FUENTE_MEDIA
                    font_size: sp(12)
                    color: T.TEXTO_2
                    text_size: self.size
                    halign: "left"
                    valign: "top"
            Chip:
                text: root.estado
                fondo: root.color_estado_suave
                tono: root.color_estado
                pos_hint: {"center_y": .5}

        # -------------------------------------------------- barra de progreso
        Widget:
            size_hint_y: None
            height: dp(3)
            canvas:
                Color:
                    rgba: T.SUPERFICIE_ALTA
                Rectangle:
                    pos: self.x + dp(16), self.y
                    size: self.width - dp(32), self.height
                Color:
                    rgba: T.ACENTO_TEXTO if root.modo == "manual" else T.SECUNDARIO_TEXTO
                Rectangle:
                    pos: self.x + dp(16), self.y
                    size: (self.width - dp(32)) * root.progreso, self.height

        # ----------------------------------------------------------- la letra
        FloatLayout:
            id: zona
            BoxLayout:
                id: letra
                orientation: "vertical"
                size_hint: 1, None
                height: self.minimum_height
                pos_hint: {"center_y": .52}
                padding: T.ESP["xl"], 0
                spacing: T.ESP["l"]
                opacity: .35 if root.pausado else 1
                Label:
                    text: root.linea_previa
                    font_name: T.FUENTE_SEMI
                    font_size: sp(17)
                    color: T.TEXTO_3
                    text_size: self.width, None
                    size_hint_y: None
                    height: self.texture_size[1]
                    halign: "center"
                Label:
                    text: root.linea_actual
                    font_name: T.FUENTE_EXTRA
                    font_size: root.tamano_actual
                    color: T.TEXTO
                    text_size: self.width, None
                    size_hint_y: None
                    height: self.texture_size[1]
                    halign: "center"
                    line_height: 1.08
                Label:
                    text: root.linea_siguiente
                    font_name: T.FUENTE_SEMI
                    font_size: sp(19)
                    color: T.TEXTO_2
                    text_size: self.width, None
                    size_hint_y: None
                    height: self.texture_size[1]
                    halign: "center"
                Label:
                    text: root.linea_despues
                    font_name: T.FUENTE_SEMI
                    font_size: sp(17)
                    color: T.TEXTO_3
                    text_size: self.width, None
                    size_hint_y: None
                    height: self.texture_size[1]
                    halign: "center"
            Label:
                text: root.mensaje
                font_name: T.FUENTE_MEDIA
                font_size: sp(13)
                color: T.TEXTO_2
                size_hint: 1, None
                height: dp(40)
                text_size: self.width - dp(48), None
                halign: "center"
                pos_hint: {"y": 0.02}

        # --------------------------------------------- escucha (automático)
        BoxLayout:
            size_hint_y: None
            height: dp(40) if root.modo == "automatico" else 0
            opacity: 1 if root.modo == "automatico" else 0
            padding: T.ESP["l"], 0
            spacing: T.ESP["s"]
            Widget:
                size_hint_x: None
                width: dp(14)
                canvas:
                    Color:
                        rgba: T.SECUNDARIO_TEXTO if root.hay_voz else T.TEXTO_3
                    Ellipse:
                        pos: self.center_x - dp(5) * root.pulso, self.center_y - dp(5) * root.pulso
                        size: dp(10) * root.pulso, dp(10) * root.pulso
            Label:
                text: root.escuchado
                font_name: T.FUENTE_MEDIA
                font_size: sp(13)
                color: T.TEXTO_2
                text_size: self.size
                halign: "left"
                valign: "middle"
                shorten: True
                shorten_from: "left"
            Chip:
                text: root.fuente
                pos_hint: {"center_y": .5}

        # ------------------------------------------- controles: la "isla"
        AnchorLayout:
            size_hint_y: None
            height: isla.height + dp(12) + (dp(12) if root.width < dp(600) else dp(20))
            anchor_y: "top"
            padding: dp(12), dp(4), dp(12), (dp(12) if root.width < dp(600) else dp(20))
            BoxLayout:
                id: isla
                orientation: "vertical"
                size_hint: None, None
                width: min(root.width - dp(24), dp(720))
                height: self.minimum_height
                padding: T.ESP["l"], T.ESP["m"], T.ESP["l"], T.ESP["l"]
                spacing: T.ESP["m"]
                canvas.before:
                    Color:
                        rgba: T.color("#1A2540", 0.86)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [dp(26)]
                    Color:
                        rgba: T.color("#8FAEE0", 0.14)
                    Line:
                        rounded_rectangle: self.x, self.y, self.width, self.height, dp(26)
                        width: 1
                BoxLayout:
                    size_hint_y: None
                    height: dp(64)
                    spacing: T.ESP["s"]
                    Control:
                        icono: root.icono1
                        texto: root.texto1
                        on_release: root.accion("a")
                    Control:
                        icono: root.icono2
                        texto: root.texto2
                        activo: root.activo2
                        on_release: root.accion("i")
                    Control:
                        icono: root.icono3
                        texto: root.texto3
                        on_release: root.accion("r")
                    Control:
                        icono: root.icono4
                        texto: root.texto4
                        activo: root.pausado and root.modo != "pista"
                        on_release: root.accion(root.tecla4)
                Boton:
                    texto: root.texto_principal
                    icono: root.icono_principal
                    estilo: "primario" if root.modo == "manual" else "automatico"
                    on_release: root.accion_principal()

<Control>:
    orientation: "vertical"
    padding: 0, dp(6)
    canvas.before:
        Color:
            rgba: (T.ACENTO_SUAVE if self.activo else (T.SUPERFICIE_ALTA if self.state == "down" else (0, 0, 0, 0)))
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [T.RADIO_BOTON]
    Icono:
        nombre: root.icono
        tamano: dp(24)
        tono: T.ACENTO_TEXTO if root.activo else T.TEXTO
        pos_hint: {"center_x": .5}
    Label:
        text: root.texto
        font_name: T.FUENTE_MEDIA
        font_size: sp(12)
        color: T.TEXTO_2
        size_hint_y: None
        height: dp(16)
""")


class Control(ButtonBehavior, BoxLayout):
    """Botón de control con ícono y rótulo (respuesta inmediata al tocar)."""

    icono = StringProperty("")
    texto = StringProperty("")
    activo = BooleanProperty(False)


class BuscarCancion(Pantalla):
    """Modo manual: identificar la canción con 2 o 3 palabras."""

    nombre_pantalla = "buscar"

    def al_entrar(self, **_):
        self.ids.palabras.text = ""
        self._mostrar_sugerencias()
        Clock.schedule_once(lambda *_: setattr(self.ids.palabras, "focus", True), 0.3)

    def programar_busqueda(self):
        Clock.unschedule(self._buscar)
        Clock.schedule_once(self._buscar, 0.2)

    def _mostrar_sugerencias(self):
        caja = self.ids.resultados
        caja.clear_widgets()
        from ..componentes import Texto

        siguiente = None
        for entrada in self.app.bd.obtener_programa():
            if entrada.estado == "pendiente" and entrada.codigo is not None:
                siguiente = entrada
                break
        if siguiente:
            caja.add_widget(Texto(tipo="mini", tono=T.TEXTO_3, text="SIGUIENTE EN EL PROGRAMA",
                                  padding=(0, T.ESP["s"])))
            fila = FilaCancion(insignia=str(siguiente.codigo), titulo=siguiente.nombre_solicitado,
                               subtitulo="Empieza desde la primera línea", icono_derecho="play",
                               dato=(siguiente.codigo, 0))
            fila.bind(on_release=self._elegir)
            caja.add_widget(fila)
        caja.add_widget(Texto(tipo="mini", tono=T.TEXTO_3, text="O ELIGE DE LA BIBLIOTECA",
                              padding=(0, T.ESP["s"])))
        for codigo, nombre, lineas in self.app.bd.listar_canciones(0, 30):
            fila = FilaCancion(insignia=str(codigo), titulo=nombre, subtitulo=f"{lineas} líneas",
                               icono_derecho="play", dato=(codigo, 0))
            fila.bind(on_release=self._elegir)
            caja.add_widget(fila)

    def _buscar(self, *_):
        texto = self.ids.palabras.text.strip()
        if len(texto) < 2:
            self._mostrar_sugerencias()
            return
        from ..componentes import Texto

        caja = self.ids.resultados
        caja.clear_widgets()
        resultados = self.app.buscador.buscar(texto, self._prioridad())
        resultados = [r for r in resultados if r.puntaje >= self.app.buscador.puntaje_minimo * 0.6]
        if not resultados:
            caja.add_widget(Texto(tipo="cuerpo", tono=T.TEXTO_2, alineacion="center",
                                  text="No encontramos esas palabras en ninguna letra.\n"
                                       "Prueba con otras o agrega la canción.",
                                  padding=(0, T.ESP["xl"])))
            return
        caja.add_widget(Texto(tipo="mini", tono=T.TEXTO_3, text="COINCIDENCIAS", padding=(0, T.ESP["s"])))
        for resultado in resultados:
            linea = self.app.buscador.canciones[resultado.codigo].lineas[resultado.linea_actual]
            fila = FilaCancion(insignia=f"{int(resultado.puntaje * 100)}%", titulo=resultado.nombre,
                               subtitulo=f"Línea {resultado.linea_actual + 1}: {linea}",
                               icono_derecho="play", dato=(resultado.codigo, resultado.linea_actual))
            fila.bind(on_release=self._elegir)
            caja.add_widget(fila)

    def _prioridad(self):
        for entrada in self.app.bd.obtener_programa():
            if entrada.estado == "pendiente" and entrada.codigo is not None:
                return {entrada.codigo: 0.12}
        return {}

    def _elegir(self, fila):
        codigo, linea = fila.dato
        self.ids.palabras.focus = False
        self.app.abrir("escenario", modo="manual", codigo=codigo, linea=linea)


class Escenario(Pantalla):
    nombre_pantalla = "escenario"

    modo = StringProperty("manual")
    titulo_cancion = StringProperty("")
    subtitulo = StringProperty("")
    estado = StringProperty("")
    color_estado = ColorProperty(T.EXITO)
    color_estado_suave = ColorProperty(T.EXITO_SUAVE)
    linea_previa = StringProperty("")
    linea_actual = StringProperty("")
    linea_siguiente = StringProperty("")
    linea_despues = StringProperty("")
    tamano_actual = NumericProperty(30)
    progreso = NumericProperty(0.0)
    pausado = BooleanProperty(False)
    mensaje = StringProperty("")
    escuchado = StringProperty("")
    fuente = StringProperty("")
    hay_voz = BooleanProperty(False)
    pulso = NumericProperty(1.0)
    texto_principal = StringProperty("Continuar")
    icono_principal = StringProperty("chevron-right")
    # Los cuatro controles de la isla cambian según el modo.
    icono1 = StringProperty("skip-previous")
    texto1 = StringProperty("Atrás")
    icono2 = StringProperty("repeat-once")
    texto2 = StringProperty("Igual")
    activo2 = BooleanProperty(False)
    icono3 = StringProperty("replay")
    texto3 = StringProperty("Repetir")
    icono4 = StringProperty("pause")
    texto4 = StringProperty("Pausa")
    tecla4 = StringProperty("g")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sesion: SesionKaraoke | None = None
        self.control: ControladorAutomatico | None = None
        self.voz = None
        self._reloj = None
        self._segundo = 0.0
        self._linea_mostrada = None
        self._toque_inicio = None
        self.reproduccion = None
        self._tiempos: list[float] = []
        self._cancion_pista = None
        self._afinando = ""

    # ------------------------------------------------------------ entrada
    def al_entrar(self, modo: str = "manual", codigo: int | None = None, linea: int = 0, **_):
        if self.sesion is None or self.sesion.finalizada or self.modo != modo or modo == "pista":
            self._cerrar_automatico()
            self._cerrar_pista()
            self.modo = modo
            self.sesion = SesionKaraoke(self.app.bd, modo)
        if modo == "pista" and codigo is not None:
            self._iniciar_pista(codigo)
        elif modo == "automatico":
            self._iniciar_automatico()
        elif codigo is not None:
            cancion = self.app.bd.obtener_cancion(codigo)
            if cancion:
                self.sesion.iniciar(cancion, linea)
        self._linea_mostrada = None
        self.actualizar()

    # ------------------------------------------------------------- manual
    def accion_principal(self):
        if self.modo == "pista":
            self.accion("g")
            return
        if self.modo == "manual" and self.sesion and self.sesion.en_curso is None:
            self._despues_de_terminar()
            return
        self.accion("s" if self.pausado else "c")

    def accion(self, tecla: str):
        if self.modo == "pista":
            self._accion_pista(tecla)
            return
        if self.modo == "automatico" and self.control is not None:
            self.control.comando(tecla)
            self.actualizar()
            return
        curso = self.sesion.en_curso if self.sesion else None
        if curso is None:
            return
        if tecla == "c":
            if curso.continuar():
                self.sesion.terminar(completada=True)
                self.app.datos_cambiaron()
        elif tecla == "a":
            curso.atras()
        elif tecla == "i":
            curso.igual()
        elif tecla == "r":
            curso.repetir()
        elif tecla == "g":
            curso.ignorar()
        elif tecla == "s":
            curso.seguir()
        self.actualizar()

    def _despues_de_terminar(self):
        """Al terminar una canción: siguiente del programa o volver a buscar."""
        siguiente = self.sesion.programa.siguiente()
        if siguiente is not None:
            cancion = self.app.bd.obtener_cancion(siguiente.codigo)
            if cancion:
                self.sesion.iniciar(cancion)
                self.actualizar()
                return
        self.app.atras()

    # --------------------------------------------------------- automático
    def _iniciar_automatico(self):
        if self.control is not None:
            return
        self.control = ControladorAutomatico(self.app.bd, self.app.buscador, self.app.config_karaoke,
                                             self.sesion, "Android")
        guion = self.app.carpeta / "ejemplos" / "guion_sound_of_you.txt"
        demostracion = getattr(self.app, "demostracion", False)
        idiomas = sorted({c.idioma for c in self.app.bd.todas_las_letras().values()})
        self.voz = crear_fuente(demostracion, guion, config=self.app.config_karaoke, idiomas=idiomas)
        self.fuente = "Micrófono" if not isinstance(self.voz, VozDemostracion) else "Demostración"
        # Si no se pudo usar el micrófono, el motivo queda a la vista.
        self._motivo_demo = self.voz.nombre if "sin micrófono" in self.voz.nombre else ""
        if self._motivo_demo:
            self.fuente = "Demostración · sin micrófono"
        self._segundo = 0.0
        if isinstance(self.voz, VozAndroid):
            VozAndroid.pedir_permiso(self._permiso)
        else:
            self._empezar_a_escuchar()

    def _permiso(self, concedido: bool):
        if concedido:
            Clock.schedule_once(lambda *_: self._empezar_a_escuchar(), 0)
        else:
            self.mensaje = "Sin permiso de micrófono no se puede usar el modo automático."

    def _empezar_a_escuchar(self):
        self.voz.iniciar()
        self._reloj = Clock.schedule_interval(self._tic, 0.1)
        self._animar_pulso()

    def _tic(self, dt):
        self._segundo += dt
        transcripciones, voz = self.voz.recoger(self._segundo)
        for t in transcripciones:
            self.control.recibir(t)
        self.control.tic(self._segundo, voz)
        if self.control.cancion is not None and hasattr(self.voz, "cambiar_idioma"):
            self.voz.cambiar_idioma(self.control.cancion.idioma)
        if self.control.vocabulario_pedido is not None and hasattr(self.voz, "pedir_vocabulario"):
            self.voz.pedir_vocabulario(*self.control.vocabulario_pedido)  # computadora (Vosk)
        self.control.vocabulario_pedido = None
        self.hay_voz = voz
        self.actualizar()

    def _animar_pulso(self):
        animacion = Animation(pulso=1.5, d=0.6, t="in_out_sine") + Animation(pulso=1.0, d=0.6, t="in_out_sine")
        animacion.repeat = True
        animacion.start(self)

    def _cerrar_automatico(self):
        if self._reloj is not None:
            self._reloj.cancel()
            self._reloj = None
        if self.voz is not None:
            self.voz.detener()
            self.voz = None
        Animation.cancel_all(self, "pulso")
        self.control = None

    # ------------------------------------------------- con pista (r)
    def _iniciar_pista(self, codigo: int):
        from ..reproduccion import Reproduccion

        bd = self.app.bd
        cancion = bd.obtener_cancion(codigo)
        archivo = bd.obtener_pista(codigo)
        ruta = self.app.carpeta / archivo if archivo else None
        self._cancion_pista = cancion
        self.titulo_cancion = cancion.nombre if cancion else "Sin canción"
        # No arrastrar nada del modo anterior (automático o manual).
        self.subtitulo, self.mensaje, self.progreso, self._afinando = "", "", 0.0, ""
        self._estado("PREPARANDO", T.SECUNDARIO_TEXTO, T.SECUNDARIO_SUAVE)
        if cancion is None or ruta is None or not ruta.exists():
            self._mensaje_pista("Esta canción no tiene pista de audio.")
            return
        try:
            self.reproduccion = Reproduccion(ruta)
        except Exception as ex:
            self._mensaje_pista(f"No se pudo reproducir: {ex}")
            return
        tiempos = bd.obtener_tiempos(codigo)
        if tiempos:
            self._arrancar_pista(tiempos)
            return
        try:
            from karaoke.audio.proceso import whisper_disponible

            con_whisper = whisper_disponible()
        except Exception:
            con_whisper = False
        if self.reproduccion.voz_disponible and con_whisper:
            # Computadora: la canción empieza YA con tiempos aproximados y la IA
            # afina la sincronía en segundo plano (solo la primera vez).
            self._arrancar_pista(tiempos_de_lineas(cancion.lineas, [], self.reproduccion.duracion))
            self._afinando = "Afinando la sincronía con IA… (solo la primera vez)"
            threading.Thread(target=self._sincronizar, args=(codigo, cancion.lineas, ruta), daemon=True).start()
        else:
            # Teléfono: tiempos aproximados (se afinan al abrirla en la computadora).
            # Teléfono, o computadora sin Whisper: tiempos aproximados.
            self._arrancar_pista(tiempos_de_lineas(cancion.lineas, [], self.reproduccion.duracion))
            self._afinando = ("Tiempos aproximados · para la sincronía exacta: pip install faster-whisper"
                            if self.reproduccion.voz_disponible else "Letra con tiempos aproximados")

    def _sincronizar(self, codigo, lineas, ruta):
        try:
            from karaoke.audio.desde_audio import sincronizar

            def progreso(fraccion):
                texto = f"Afinando la sincronía con IA… {int(fraccion * 100)} %"
                Clock.schedule_once(lambda *_: setattr(self, "_afinando", texto), 0)

            tiempos = sincronizar(ruta, self.app.config_karaoke, lineas, progreso)
        except Exception as ex:
            error = f"Tiempos aproximados (no se pudo afinar: {ex})"
            Clock.schedule_once(lambda *_: setattr(self, "_afinando", error), 0)
            return

        def listo(*_):
            self.app.bd.guardar_tiempos(codigo, tiempos)  # la próxima vez empieza exacta
            if self.reproduccion is None:  # se salió mientras sincronizaba
                return
            self._tiempos = tiempos  # se cambian sin detener la canción
            self._afinando = "Sincronía exacta lista"
            Clock.schedule_once(lambda *_: setattr(self, "_afinando", ""), 3)

        Clock.schedule_once(listo, 0)

    def _arrancar_pista(self, tiempos: list[float]):
        self._tiempos = tiempos
        try:
            self.reproduccion.iniciar()
        except Exception as ex:
            self._mensaje_pista(f"No se pudo reproducir: {ex}")
            return
        self.sesion.iniciar(self._cancion_pista, 0)
        self._reloj = Clock.schedule_interval(lambda dt: self.actualizar(), 1 / 30)

    def _mensaje_pista(self, texto: str, detalle: str = ""):
        self.linea_previa = self.linea_siguiente = self.linea_despues = ""
        self.linea_actual = texto
        self.mensaje = detalle
        self.tamano_actual = dp(22)
        self._controles_pista()

    def _accion_pista(self, tecla: str):
        r = self.reproduccion
        if r is None or not self._tiempos:
            return
        if tecla == "a":
            r.mover(-5)
        elif tecla in ("r", "c"):
            r.mover(5)
        elif tecla == "i":
            r.siguiente_nivel_voz()
        elif tecla == "inicio":
            r.mover(-r.segundo)
        elif tecla in ("g", "s"):
            r.alternar_pausa()
        self.actualizar()

    def _cerrar_pista(self):
        if self.reproduccion is not None:
            self.reproduccion.detener()
            self.reproduccion = None
            if self._reloj is not None:
                self._reloj.cancel()
                self._reloj = None
        self._tiempos = []

    def _controles_pista(self):
        r = self.reproduccion
        voz = int(round((r.voz if r else 1.0) * 100))
        self.icono1, self.texto1 = "rewind-5", "−5 s"
        self.icono2 = "account-voice"
        self.texto2 = f"Voz {voz} %" if r is not None and r.voz_disponible else "Voz"
        self.activo2 = voz < 100
        self.icono3, self.texto3 = "fast-forward-5", "+5 s"
        self.icono4, self.texto4, self.tecla4 = "restart", "Inicio", "inicio"
        pausado = bool(r and r.pausado)
        self.texto_principal, self.icono_principal = ("Reproducir", "play") if pausado else ("Pausa", "pause")

    def _pintar_pista(self):
        r = self.reproduccion
        self._controles_pista()
        if r is None or not self._tiempos or self._cancion_pista is None:
            return
        cancion = self._cancion_pista
        segundo = r.segundo
        adelanto = self.app.config_karaoke.decimal("automatico", "segundos_letra_adelantada")
        actual = linea_en(self._tiempos, segundo, adelanto)
        reloj = f"{int(segundo // 60)}:{int(segundo % 60):02d} / {int(r.duracion // 60)}:{int(r.duracion % 60):02d}"
        self.subtitulo = reloj
        self.progreso = min(1.0, segundo / max(1.0, r.duracion))
        self.pausado = r.pausado
        if r.terminada:
            self._estado("TERMINÓ", T.EXITO, T.EXITO_SUAVE)
            if self.sesion and self.sesion.en_curso is not None:
                self.sesion.terminar(completada=True)
                self.app.datos_cambiaron()
            self._pintar_lineas(cancion.lineas, len(cancion.lineas))
            return
        if r.pausado:
            self._estado("EN PAUSA", T.AVISO, T.AVISO_SUAVE)
        elif actual < 0:
            self._estado("INTRO", T.SECUNDARIO_TEXTO, T.SECUNDARIO_SUAVE)
        else:
            self._estado("SONANDO", T.EXITO, T.EXITO_SUAVE)
        if actual < 0:
            faltan = max(0, int(self._tiempos[0] - adelanto - segundo + 0.99))
            self.mensaje = " · ".join(t for t in (f"La letra empieza en {faltan} s", self._afinando) if t)
            self._pintar_lineas(cancion.lineas, 0)
            self.linea_previa = ""
            return
        self.mensaje = self._afinando
        self._pintar_lineas(cancion.lineas, actual)

    def _controles_normales(self):
        self.icono1, self.texto1 = "skip-previous", "Atrás"
        self.icono2, self.texto2, self.activo2 = "repeat-once", "Igual", False
        self.icono3, self.texto3 = "replay", "Repetir"
        self.icono4 = "play" if self.pausado else "pause"
        self.texto4 = "Seguir" if self.pausado else "Pausa"
        self.tecla4 = "s" if self.pausado else "g"

    # ----------------------------------------------------------- pantalla
    def actualizar(self):
        if self.modo == "pista":
            self._pintar_pista()
            return
        if self.modo == "automatico" and self.control is not None:
            self._pintar_automatico()
        else:
            self._pintar_manual()
        self._controles_normales()

    def _pintar_lineas(self, lineas: list[str], actual: int):
        def linea(i):
            return lineas[i] if 0 <= i < len(lineas) else ""

        self.linea_previa = linea(actual - 1)
        self.linea_actual = linea(actual) if actual < len(lineas) else "Fin de la canción"
        self.linea_siguiente = linea(actual + 1) if actual < len(lineas) else ""
        self.linea_despues = linea(actual + 2) if actual < len(lineas) else ""
        largo = len(self.linea_actual)
        # La letra crece con la pantalla: teléfono, tableta o computadora.
        escala = min(1.6, max(1.0, self.width / dp(430)))
        base = dp(30) if largo <= 40 else dp(26) if largo <= 70 else dp(22)
        self.tamano_actual = base * escala
        self.progreso = min(1.0, actual / max(1, len(lineas)))
        clave = (tuple(lineas[:1]), actual)
        if clave != self._linea_mostrada:
            # La letra sube suavemente al cambiar de línea.
            self._linea_mostrada = clave
            caja = self.ids.letra
            Animation.cancel_all(caja, "pos_hint")
            caja.pos_hint = {"center_y": 0.47}
            Animation(pos_hint={"center_y": 0.52}, d=T.DURACION, t=T.CURVA).start(caja)

    def _pintar_manual(self):
        curso = self.sesion.en_curso if self.sesion else None
        self.texto_principal, self.icono_principal = "Continuar", "chevron-right"
        if curso is None:
            ultima = self.sesion.cantadas[-1] if self.sesion and self.sesion.cantadas else None
            self.titulo_cancion = ultima.nombre if ultima else "Sin canción"
            self.subtitulo = f"{len(self.sesion.cantadas)} canción(es) en esta sesión" if self.sesion else ""
            self._estado("TERMINÓ", T.EXITO, T.EXITO_SUAVE)
            self.linea_previa = self.linea_siguiente = self.linea_despues = ""
            self.linea_actual = "¡Bien cantado!"
            self.progreso = 1.0
            self.pausado = False
            siguiente = self.sesion.programa.siguiente() if self.sesion else None
            self.mensaje = f"Sigue en el programa: {siguiente.nombre_solicitado}" if siguiente else \
                "Toca «Elegir otra» para seguir cantando."
            self.texto_principal = "Siguiente del programa" if siguiente else "Elegir otra"
            self.icono_principal = "skip-next" if siguiente else "magnify"
            return
        cancion = curso.cancion
        self.titulo_cancion = cancion.nombre
        self.subtitulo = f"Línea {min(curso.actual + 1, curso.total)} de {curso.total}"
        self.pausado = curso.pausada
        if curso.pausada:
            self._estado("EN PAUSA", T.AVISO, T.AVISO_SUAVE)
            self.mensaje = "En pausa mientras el cantante afina. Toca «Seguir» para continuar."
            self.texto_principal, self.icono_principal = "Seguir", "play"
        else:
            self._estado("CANTANDO", T.EXITO, T.EXITO_SUAVE)
            self.mensaje = curso.mensaje
        self._pintar_lineas(cancion.lineas, curso.actual)

    def _pintar_automatico(self):
        pantalla = self.control.pantalla()
        self.escuchado = pantalla.escuchado or "Esperando la voz del cantante…"
        self.texto_principal, self.icono_principal = "Siguiente línea", "chevron-right"
        textos = {
            ESPERANDO: ("ESCUCHANDO", T.SECUNDARIO_TEXTO, T.SECUNDARIO_SUAVE),
            SIGUIENDO: ("SIGUIENDO", T.EXITO, T.EXITO_SUAVE),
            PAUSA: ("EN PAUSA", T.AVISO, T.AVISO_SUAVE),
            IGNORANDO: ("IGNORANDO", T.AVISO, T.AVISO_SUAVE),
            APRENDIENDO: ("APRENDIENDO", T.ACENTO_TEXTO, T.ACENTO_SUAVE),
        }
        self._estado(*textos.get(pantalla.estado, ("FIN", T.TEXTO_2, T.SUPERFICIE_ALTA)))
        self.pausado = pantalla.estado in (PAUSA, IGNORANDO)
        self.mensaje = pantalla.avisos[-1] if pantalla.avisos else getattr(self, "_motivo_demo", "")
        if pantalla.cancion is not None:
            self.titulo_cancion = pantalla.cancion.nombre
            total = len(pantalla.cancion.lineas)
            self.subtitulo = f"Línea {min(pantalla.linea + 1, total)} de {total} · modo automático"
            self._pintar_lineas(pantalla.cancion.lineas, pantalla.linea)
            return
        self.titulo_cancion = "Modo automático"
        self.subtitulo = f"Siguiente en el programa: {pantalla.siguiente_programa}" \
            if pantalla.siguiente_programa else "Canta y la canción se reconocerá sola"
        self.progreso = 0
        self.linea_previa = self.linea_siguiente = self.linea_despues = ""
        if pantalla.estado == APRENDIENDO:
            self.linea_actual = "Aprendiendo una canción nueva"
            self.linea_siguiente = "\n".join(pantalla.aprendidas)
        else:
            self.linea_actual = "Cante y la letra aparecerá aquí"
            self.linea_siguiente = "Reconocemos la canción con unas cuantas palabras."
        self.tamano_actual = dp(24)

    def _estado(self, texto, color, suave):
        self.estado, self.color_estado, self.color_estado_suave = texto, color, suave

    # ------------------------------------------------------------- gestos
    def on_touch_down(self, toque):
        if self.ids.zona.collide_point(*toque.pos):
            self._toque_inicio = toque.pos
        return super().on_touch_down(toque)

    def on_touch_up(self, toque):
        inicio, self._toque_inicio = self._toque_inicio, None
        if inicio is not None and self.ids.zona.collide_point(*toque.pos):
            dx = toque.pos[0] - inicio[0]
            if dx < -dp(60):
                self.accion("c")       # deslizar a la izquierda: avanzar
            elif dx > dp(60):
                self.accion("a")       # deslizar a la derecha: regresar
            elif abs(dx) < dp(10) and abs(toque.pos[1] - inicio[1]) < dp(10):
                self.accion_principal()  # tocar la letra: continuar
        return super().on_touch_up(toque)

    # ---------------------------------------------------------- terminar
    def terminar_sesion(self):
        if self.modo == "pista":
            self._cerrar_pista()
            if self.sesion is not None and not self.sesion.finalizada:
                self.sesion.finalizar()
            self.app.datos_cambiaron()
            self._salir()
            return
        sesion = self.sesion
        if sesion is None or (not sesion.cantadas and sesion.en_curso is None and self.control is None):
            self._salir()
            return
        if self.control is not None:
            self.control.finalizar()
        elif not sesion.finalizada:
            sesion.finalizar()
        self._cerrar_automatico()
        cantadas = sesion.cantadas
        completas = sum(1 for c in cantadas if c.completada)
        lista = "\n".join(f"{'✓' if c.completada else '·'}  {c.nombre}" for c in cantadas[-6:])
        dialogo = Dialogo(titulo="Fin de la sesión", icono="flag-checkered",
                          mensaje=f"Se cantaron {len(cantadas)} canción(es), {completas} completa(s).\n\n{lista}"
                          if cantadas else "No se cantó ninguna canción.")
        dialogo.agregar_boton("Listo", "primario", self._salir)
        dialogo.open()
        self.app.datos_cambiaron()

    def _salir(self):
        self._cerrar_automatico()
        self.sesion = None
        self.app.atras()

    def on_size(self, *_):
        # Al cambiar el tamaño de la ventana la letra se vuelve a medir.
        if self.sesion is not None or self.control is not None:
            self._linea_mostrada = None
            self.actualizar()

    def on_leave(self, *_):
        if self.modo == "pista":
            self._cerrar_pista()
        if self.sesion is not None and self.sesion.finalizada:
            self.sesion = None
