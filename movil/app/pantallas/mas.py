"""Pestaña "Más": historial (h), ajustes, acerca de y la papelera.

La papelera está aquí a propósito, como una opción discreta al final de la
pantalla: se puede llegar a ella cuando hace falta recuperar una canción,
pero no está a la vista en el uso diario.
"""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout

from karaoke import __version__

from .. import tema as T
from ..componentes import Dialogo, FilaCancion, Texto, confirmar
from .base import Pantalla

Builder.load_string("""
#:import T app.tema

<FilaOpcion>:
    size_hint_y: None
    height: dp(60)
    padding: T.ESP["m"], 0
    spacing: T.ESP["m"]
    canvas.before:
        Color:
            rgba: T.SUPERFICIE_ALTA if self.state == "down" else (0, 0, 0, 0)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [T.RADIO_BOTON]
    AnchorLayout:
        size_hint: None, None
        size: dp(36), dp(36)
        pos_hint: {"center_y": .5}
        canvas.before:
            Color:
                rgba: T.ACENTO_SUAVE
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(10)]
        Icono:
            nombre: root.icono
            tamano: dp(20)
            tono: T.ACENTO_TEXTO
    Label:
        text: root.texto
        font_name: T.FUENTE_MEDIA
        font_size: sp(16)
        color: T.TEXTO
        text_size: self.size
        halign: "left"
        valign: "middle"
    Label:
        text: root.valor
        font_name: T.FUENTE_MEDIA
        font_size: sp(14)
        color: T.TEXTO_3
        size_hint_x: None
        width: self.texture_size[0]
    Icono:
        nombre: "chevron-right"
        tono: T.TEXTO_3
        tamano: dp(20)
        pos_hint: {"center_y": .5}

<FilaAjuste>:
    size_hint_y: None
    height: dp(72)
    padding: T.ESP["m"], 0
    spacing: T.ESP["s"]
    BoxLayout:
        orientation: "vertical"
        padding: 0, dp(12)
        Label:
            text: root.texto
            font_name: T.FUENTE_MEDIA
            font_size: sp(15)
            color: T.TEXTO
            text_size: self.size
            halign: "left"
            valign: "bottom"
        Label:
            text: root.ayuda
            font_name: T.FUENTE
            font_size: sp(12)
            color: T.TEXTO_3
            text_size: self.size
            halign: "left"
            valign: "top"
    BotonIcono:
        icono: "minus"
        lado: dp(36)
        pos_hint: {"center_y": .5}
        on_release: root.cambiar(-1)
    Label:
        text: root.mostrar
        font_name: T.FUENTE_SEMI
        font_size: sp(16)
        color: T.TEXTO
        size_hint_x: None
        width: dp(56)
    BotonIcono:
        icono: "plus"
        lado: dp(36)
        pos_hint: {"center_y": .5}
        on_release: root.cambiar(1)

<MasPantalla>:
    ScrollView:
        do_scroll_x: False
        BoxLayout:
            orientation: "vertical"
            padding: T.ESP["l"], T.ESP["xl"], T.ESP["l"], T.ESP["xl"]
            spacing: T.ESP["s"]
            size_hint_y: None
            height: self.minimum_height
            EncabezadoGrande:
                antetitulo: "Karaoke Inteligente"
                titulo: "Más"
            Tarjeta:
                padding: T.ESP["xs"]
                spacing: 0
                FilaOpcion:
                    icono: "history"
                    texto: "Historial y estadísticas"
                    on_release: app.abrir("historial")
                FilaOpcion:
                    icono: "cog-outline"
                    texto: "Ajustes"
                    on_release: app.abrir("ajustes")
                FilaOpcion:
                    icono: "information-outline"
                    texto: "Acerca de y derechos de autor"
                    on_release: app.abrir("acerca")
            Widget:
                size_hint_y: None
                height: T.ESP["xl"]
            Tarjeta:
                padding: T.ESP["xs"]
                fondo: 0, 0, 0, 0
                FilaOpcion:
                    icono: "delete-outline"
                    texto: "Papelera"
                    valor: root.en_papelera
                    on_release: app.abrir("papelera")

<SubPantalla@Pantalla>:
    con_pestanas: False

<ListaSimple>:
    con_pestanas: False
    BoxLayout:
        orientation: "vertical"
        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: T.ESP["s"], 0, T.ESP["l"], 0
            spacing: T.ESP["s"]
            BotonIcono:
                icono: "chevron-left"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: app.atras()
            Widget:
            Boton:
                id: accion
                size_hint: None, None
                width: dp(108)
                height: dp(40)
                estilo: "peligro"
                texto: root.texto_accion
                opacity: 1 if root.texto_accion else 0
                disabled: not root.texto_accion
                pos_hint: {"center_y": .5}
                on_release: root.accion()
        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                padding: T.ESP["l"], 0, T.ESP["l"], T.ESP["xl"]
                spacing: T.ESP["s"]
                size_hint_y: None
                height: self.minimum_height
                EncabezadoGrande:
                    antetitulo: root.antetitulo
                    titulo: root.titulo
                BoxLayout:
                    id: contenido
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: T.ESP["xs"]
""")


class FilaOpcion(ButtonBehavior, BoxLayout):
    icono = StringProperty("")
    texto = StringProperty("")
    valor = StringProperty("")


class FilaAjuste(BoxLayout):
    """Ajuste numérico con botones − y + (se guarda al momento en karaoke.ini)."""

    texto = StringProperty("")
    ayuda = StringProperty("")
    valor = NumericProperty(0)
    minimo = NumericProperty(0)
    maximo = NumericProperty(100)
    paso = NumericProperty(1)
    sufijo = StringProperty("")
    mostrar = StringProperty("")

    def __init__(self, al_cambiar=None, **kwargs):
        self.al_cambiar = al_cambiar
        super().__init__(**kwargs)
        self.on_valor()

    def on_valor(self, *_):
        self.mostrar = f"{int(self.valor)}{self.sufijo}"

    def cambiar(self, direccion: int):
        nuevo = max(self.minimo, min(self.maximo, self.valor + direccion * self.paso))
        if nuevo != self.valor:
            self.valor = nuevo
            if self.al_cambiar:
                self.al_cambiar(int(nuevo))


class MasPantalla(Pantalla):
    nombre_pantalla = "mas"
    en_papelera = StringProperty("")

    def al_entrar(self, **_):
        self.refrescar()

    def refrescar(self):
        cantidad = len(self.app.bd.listar_papelera())
        self.en_papelera = str(cantidad) if cantidad else ""


class ListaSimple(Pantalla):
    antetitulo = StringProperty("")
    texto_accion = StringProperty("")

    def contenido(self):
        caja = self.ids.contenido
        caja.clear_widgets()
        return caja

    def accion(self):
        pass

    def subtitulo(self, caja, texto):
        caja.add_widget(Texto(tipo="mini", tono=T.TEXTO_3, text=texto, padding=(0, T.ESP["m"])))

    def vacio(self, caja, texto):
        caja.add_widget(Texto(tipo="cuerpo", tono=T.TEXTO_2, text=texto, alineacion="center",
                              padding=(0, T.ESP["xxl"])))


class Historial(ListaSimple):
    nombre_pantalla = "historial"

    def al_entrar(self, **_):
        self.titulo, self.antetitulo = "Historial", "Estadísticas"
        bd = self.app.bd
        caja = self.contenido()
        populares = bd.mas_cantadas(5)
        recientes = bd.historial(30)
        if not populares and not recientes:
            self.vacio(caja, "Todavía no se ha cantado ninguna canción.")
            return
        if populares:
            self.subtitulo(caja, "MÁS CANTADAS")
            for codigo, nombre, veces in populares:
                caja.add_widget(FilaCancion(insignia=str(veces), titulo=nombre,
                                            subtitulo=f"{veces} {'vez' if veces == 1 else 'veces'} completa",
                                            icono_derecho="", dato=codigo))
        self.subtitulo(caja, "ÚLTIMAS INTERPRETACIONES")
        for fila in recientes:
            completa = bool(fila["completada"])
            caja.add_widget(FilaCancion(
                insignia="✓" if completa else "·", titulo=fila["nombre_cancion"],
                subtitulo=f"{fila['inicio']} · {fila['modo']} · {'completa' if completa else 'incompleta'}",
                icono_derecho="", color_insignia=T.EXITO_SUAVE if completa else T.SUPERFICIE_ALTA,
                color_texto_insignia=T.EXITO if completa else T.TEXTO_3))


class Papelera(ListaSimple):
    nombre_pantalla = "papelera"

    def al_entrar(self, **_):
        self.refrescar()

    def refrescar(self):
        if not self.ids:
            return
        self.titulo = "Papelera"
        dias = self.app.config_karaoke.entero("letras", "dias_papelera")
        self.antetitulo = f"Se vacía sola a los {dias} días" if dias else "No se vacía sola"
        borradas = self.app.bd.listar_papelera()
        self.texto_accion = "Vaciar" if borradas else ""
        caja = self.contenido()
        if not borradas:
            self.vacio(caja, "La papelera está vacía.\nLas canciones que borres aparecerán aquí.")
            return
        for codigo, nombre, lineas, fecha in borradas:
            fila = FilaCancion(insignia=str(codigo), titulo=nombre,
                               subtitulo=f"{lineas} líneas · borrada el {fecha[:10]}",
                               color_insignia=T.SUPERFICIE_ALTA, color_texto_insignia=T.TEXTO_2,
                               icono_derecho="dots-horizontal", dato=(codigo, nombre))
            fila.bind(on_release=self._opciones)
            caja.add_widget(fila)

    def _opciones(self, fila):
        codigo, nombre = fila.dato
        dialogo = Dialogo(titulo=nombre, icono="delete-outline",
                          mensaje="Puedes restaurarla con su mismo código o eliminarla para siempre.")
        dialogo.agregar_boton("Restaurar", "primario", lambda: self._restaurar(codigo, nombre))
        dialogo.agregar_boton("Eliminar definitivamente", "peligro", lambda: self._eliminar(codigo, nombre))
        dialogo.agregar_boton("Cancelar", "fantasma")
        dialogo.open()

    def _restaurar(self, codigo, nombre):
        self.app.bd.restaurar_cancion(codigo)
        self.app.datos_cambiaron()
        self.app.avisar(f"«{nombre}» restaurada")

    def _eliminar(self, codigo, nombre):
        def hacer():
            self.app.bd.eliminar_definitivamente(codigo)
            self.app.datos_cambiaron()
            self.app.avisar("Eliminada definitivamente")

        confirmar("¿Eliminar para siempre?", f"«{nombre}» y su letra se borrarán definitivamente.",
                  "Eliminar", hacer, peligro=True)

    def accion(self):
        def hacer():
            cantidad = self.app.bd.vaciar_papelera()
            self.app.datos_cambiaron()
            self.app.avisar(f"Se eliminaron {cantidad} canción(es)")

        confirmar("¿Vaciar la papelera?", "Todo lo que está en la papelera se borrará definitivamente.",
                  "Vaciar papelera", hacer, peligro=True)


class Ajustes(ListaSimple):
    nombre_pantalla = "ajustes"

    def al_entrar(self, **_):
        self.titulo, self.antetitulo = "Ajustes", "Se guardan en karaoke.ini"
        config = self.app.config_karaoke
        caja = self.contenido()
        ajustes = [
            ("letras", "caracteres_por_linea", "Caracteres por línea", "Las más largas se dividen",
             20, 200, 10, ""),
            ("automatico", "segundos_silencio_pausa", "Pausa automática", "Segundos sin voz",
             2, 30, 1, " s"),
            ("automatico", "avance_linea", "Adelantar la línea", "Al cantar este % de la actual",
             50, 95, 5, " %"),
            ("letras", "dias_papelera", "Días en la papelera", "0 = no se vacía sola", 0, 365, 5, ""),
        ]
        for seccion, clave, texto, ayuda, minimo, maximo, paso, sufijo in ajustes:
            if clave == "avance_linea":
                valor = int(round(config.decimal(seccion, clave) * 100))
            else:
                valor = config.entero(seccion, clave)

            def guardar(nuevo, seccion=seccion, clave=clave):
                config.establecer(seccion, clave, str(nuevo / 100 if clave == "avance_linea" else nuevo))
                config.guardar()

            caja.add_widget(FilaAjuste(texto=texto, ayuda=ayuda, valor=valor, minimo=minimo, maximo=maximo,
                                       paso=paso, sufijo=sufijo, al_cambiar=guardar))
        self.subtitulo(caja, "MODO AUTOMÁTICO")
        demostracion = FilaOpcion(icono="robot-outline", texto="Usar la demostración",
                                  valor="Sí" if getattr(self.app, "demostracion", False) else "No")

        def alternar(fila):
            self.app.demostracion = not getattr(self.app, "demostracion", False)
            fila.valor = "Sí" if self.app.demostracion else "No"

        demostracion.bind(on_release=alternar)
        caja.add_widget(demostracion)
        caja.add_widget(Texto(tipo="nota", tono=T.TEXTO_3, padding=(T.ESP["m"], T.ESP["s"]),
                              text="La demostración sigue Sound of You con un guion, sin usar el micrófono."))
        from kivy.utils import platform

        if platform != "android":
            self._fila_microfono(caja, config)

    def _fila_microfono(self, caja, config):
        """Computadora: lista completa de micrófonos y elección automática del
        que funciona (el mismo ajuste que la opción d de la consola)."""
        import threading

        from kivy.clock import Clock

        try:
            from karaoke.audio.fuentes import detectar_microfono, listar_microfonos_detalle

            microfonos = listar_microfonos_detalle()
        except Exception as ex:
            caja.add_widget(Texto(tipo="nota", tono=T.AVISO, padding=(T.ESP["m"], T.ESP["s"]),
                                  text=f"No se pueden leer los micrófonos: {ex}"))
            return
        nombres = {i: f"{n} · {sistema}" if sistema else n for i, n, sistema in microfonos}
        fila = FilaOpcion(icono="microphone", texto="Micrófono", valor="Buscando el que funciona…")
        nota = Texto(tipo="nota", tono=T.TEXTO_3, padding=(T.ESP["m"], T.ESP["s"]), text="")

        def detectar(*_):
            def trabajar():
                elegido = config.texto("audio", "dispositivo").strip()
                try:
                    indice, nombre = detectar_microfono(elegido or None)
                    modo = "elegido" if elegido and elegido == str(indice) else "automático"
                    texto, ayuda = nombre[:40], f"En uso ({modo}): {nombre}"
                    if elegido and elegido != str(indice):
                        ayuda += " · el elegido no funcionó, se usa este"
                except Exception as ex:
                    texto, ayuda = "Ninguno funciona", str(ex)
                Clock.schedule_once(lambda *_: (setattr(fila, "valor", texto), setattr(nota, "text", ayuda)), 0)

            threading.Thread(target=trabajar, daemon=True).start()

        def elegir(*_):
            dialogo = Dialogo(titulo="Elegir el micrófono", icono="microphone",
                              mensaje="«Automático» prueba los micrófonos y usa el primero que capta sonido. "
                                      "Canta cerca del micrófono y escucha la música con audífonos.")

            def guardar(valor):
                config.establecer("audio", "dispositivo", valor)
                config.guardar()
                fila.valor = "Comprobando…"
                detectar()
                self.app.avisar("Micrófono guardado")

            dialogo.agregar_boton("Automático (recomendado)", "primario", lambda: guardar(""))
            for indice, nombre in nombres.items():
                dialogo.agregar_boton(nombre[:46], "fantasma", lambda i=indice: guardar(str(i)))
            dialogo.open()

        fila.bind(on_release=elegir)
        caja.add_widget(fila)
        caja.add_widget(nota)
        if microfonos:
            detectar()
        else:
            fila.valor = "Ninguno"
            nota.text = "No se encontró ningún micrófono conectado."


class AcercaDe(ListaSimple):
    nombre_pantalla = "acerca"

    def al_entrar(self, **_):
        self.titulo, self.antetitulo = "Karaoke Inteligente", f"Versión {__version__}"
        caja = self.contenido()
        bloques = [
            ("AUTOR", "Edgar Alessandro Chocon Oliva · Carné 202212978"),
            ("DERECHOS DE AUTOR DE LAS CANCIONES",
             "Las letras de «Sound of You» y «Ghost of you», y sus grabaciones de ejemplo, son obra original "
             "de Edgar Alessandro Chocon Oliva. © 2026. Todos los derechos reservados. Se incluyen solo como "
             "ejemplo y prueba de esta aplicación; no se autoriza copiarlas, distribuirlas ni usarlas con otro "
             "fin sin permiso escrito del autor."),
            ("PRIVACIDAD",
             "La voz se reconoce en el teléfono. La app solo pide el permiso de micrófono y no envía tus "
             "canciones a ningún servidor."),
            ("TECNOLOGÍA",
             "Python y Kivy. Reconocimiento de voz del sistema Android. Mismo núcleo que la versión de "
             "Windows (SQLite, búsqueda tolerante a errores y seguimiento automático de la letra)."),
            ("LICENCIAS", "Tipografía Inter (SIL Open Font License 1.1). Íconos Material Design Icons "
                          "(Pictogrammers, Apache 2.0)."),
        ]
        for titulo, texto in bloques:
            self.subtitulo(caja, titulo)
            caja.add_widget(Texto(tipo="cuerpo", tono=T.TEXTO_2, text=texto))
