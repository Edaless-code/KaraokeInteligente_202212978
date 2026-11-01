"""Agregar y corregir canciones (opciones f → t, f → e, f → v y u).

Pensado para que agregar una canción nueva sea lo más fácil posible:

* **Pegar la letra**: nombre + toda la letra pegada de una vez. Cada renglón
  es una línea; se quitan solas las etiquetas como "[Chorus]" y las líneas de
  más de 80 caracteres se dividen.
* **Línea por línea**: el modo de la especificación. Se escribe una línea y
  se presiona Enter; una línea vacía termina la canción.
* **Importar archivo** de texto y **canciones de ejemplo**.
* **Aprendidas**: las que el modo automático guardó en las tablas temporales.
"""

from __future__ import annotations

from pathlib import Path

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform

from karaoke.db import CancionDuplicada
from karaoke.importador import importar_archivo
from karaoke.texto import ajustar_linea, es_etiqueta

from .. import tema as T
from ..componentes import Boton, Dialogo, FilaCancion, Texto
from .base import Pantalla

Builder.load_string("""
#:import T app.tema

<CabeceraVolver@BoxLayout>:
    size_hint_y: None
    height: dp(56)
    padding: T.ESP["s"], 0
    spacing: T.ESP["s"]

<OpcionAgregar@TarjetaModo>:
    height: dp(88)

<Importar>:
    con_pestanas: False
    BoxLayout:
        orientation: "vertical"
        CabeceraVolver:
            BotonIcono:
                icono: "chevron-left"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: app.atras()
        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                padding: T.ESP["l"], 0, T.ESP["l"], T.ESP["xl"]
                spacing: T.ESP["m"]
                size_hint_y: None
                height: self.minimum_height
                EncabezadoGrande:
                    antetitulo: "Biblioteca"
                    titulo: "Agregar canciones"
                OpcionAgregar:
                    icono: "content-paste"
                    titulo: "Pegar o escribir la letra"
                    descripcion: "La forma más rápida: nombre y letra completa."
                    on_release: app.abrir("nueva", modo="pegar")
                OpcionAgregar:
                    icono: "waveform"
                    titulo: "Desde un MP3: la IA escribe la letra"
                    descripcion: "Elige la canción y la IA escribe su letra con los tiempos de cada línea."
                    on_release: root.desde_audio()
                OpcionAgregar:
                    icono: "format-list-numbered"
                    titulo: "Línea por línea"
                    descripcion: "Escribe una línea y presiona Enter. Vacía = terminar."
                    on_release: app.abrir("nueva", modo="lineas")
                OpcionAgregar:
                    icono: "file-document-outline"
                    titulo: "Importar archivo de texto"
                    descripcion: "Un archivo .txt con el nombre y la letra de cada canción."
                    on_release: root.importar_archivo()
                OpcionAgregar:
                    icono: "music-note-plus"
                    titulo: "Canciones de ejemplo"
                    descripcion: "Sound of You y Ghost of you, de Edgar A. Chocon Oliva."
                    on_release: root.importar_ejemplos()
                Texto:
                    tipo: "mini"
                    tono: T.TEXTO_3
                    text: root.titulo_aprendidas
                    padding: 0, T.ESP["m"], 0, 0
                BoxLayout:
                    id: aprendidas
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height

<NuevaCancion>:
    con_pestanas: False
    BoxLayout:
        orientation: "vertical"
        CabeceraVolver:
            BotonIcono:
                icono: "chevron-left"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: app.atras()
            Texto:
                tipo: "encabezado"
                text: "Nueva canción"
                pos_hint: {"center_y": .5}
        BoxLayout:
            orientation: "vertical"
            padding: T.ESP["l"], 0, T.ESP["l"], T.ESP["l"]
            spacing: T.ESP["m"]
            SelectorModo:
                id: selector
            Campo:
                id: nombre
                hint_text: "Nombre de la canción"
                multiline: False
                on_text_validate: root.al_validar_nombre()
            # ----- modo pegar
            Campo:
                id: letra
                hint_text: "Pega o escribe aquí la letra. Cada renglón es una línea."
                multiline: True
                size_hint_y: 1 if root.modo == "pegar" else None
                height: 0 if root.modo != "pegar" else dp(160)
                opacity: 1 if root.modo == "pegar" else 0
                on_text: root.contar()
            # ----- modo línea por línea
            ScrollView:
                id: lista_scroll
                do_scroll_x: False
                size_hint_y: 1 if root.modo == "lineas" else None
                height: 0
                opacity: 1 if root.modo == "lineas" else 0
                BoxLayout:
                    id: lista
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: T.ESP["s"]
            Campo:
                id: linea
                hint_text: root.pista_linea
                multiline: False
                text_validate_unfocus: False
                size_hint_y: None
                height: dp(50) if root.modo == "lineas" else 0
                opacity: 1 if root.modo == "lineas" else 0
                on_text_validate: root.agregar_linea()
            Texto:
                tipo: "nota"
                tono: T.TEXTO_2
                text: root.resumen
            Boton:
                texto: "Guardar canción"
                icono: "check"
                on_release: root.guardar()

<SelectorModo>:
    size_hint_y: None
    height: dp(40)
    padding: dp(4)
    spacing: dp(4)
    canvas.before:
        Color:
            rgba: T.SUPERFICIE_ALTA
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]

<EditorCancion>:
    con_pestanas: False
    BoxLayout:
        orientation: "vertical"
        CabeceraVolver:
            BotonIcono:
                icono: "chevron-left"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: app.atras()
            Widget:
            BotonIcono:
                icono: "delete-outline"
                fondo: 0, 0, 0, 0
                tinta: T.PELIGRO
                lado: dp(44)
                opacity: 1 if root.es_temporal else 0
                disabled: not root.es_temporal
                pos_hint: {"center_y": .5}
                on_release: root.descartar()
        BoxLayout:
            orientation: "vertical"
            padding: T.ESP["l"], 0, T.ESP["l"], T.ESP["l"]
            spacing: T.ESP["m"]
            Texto:
                tipo: "mini"
                tono: T.ACENTO_TEXTO
                text: root.antetitulo
            Texto:
                tipo: "titulo"
                text: "Revisar canción aprendida" if root.es_temporal else "Corregir canción"
            Campo:
                id: nombre
                hint_text: "Nombre de la canción"
                multiline: False
            Campo:
                id: letra
                hint_text: "Letra: un renglón por línea"
                multiline: True
                size_hint_y: 1
                on_text: root.contar()
            Texto:
                tipo: "nota"
                tono: T.TEXTO_2
                text: root.resumen
            Boton:
                texto: "Guardar en la biblioteca" if root.es_temporal else "Guardar cambios"
                icono: "check"
                on_release: root.guardar()
""")


class SelectorModo(BoxLayout):
    """Control segmentado de dos opciones (Pegar | Línea por línea)."""

    seleccion = StringProperty("pegar")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.botones = {}
        for clave, texto in (("pegar", "Pegar letra"), ("lineas", "Línea por línea")):
            boton = Boton(texto=texto, estilo="secundario", radio=9)
            boton.height = 32
            boton.bind(on_release=lambda b, c=clave: self.elegir(c))
            self.botones[clave] = boton
            self.add_widget(boton)
        self.on_seleccion()

    def elegir(self, clave: str):
        self.seleccion = clave

    def on_seleccion(self, *_):
        for clave, boton in self.botones.items():
            boton.estilo = "primario" if clave == self.seleccion else "fantasma"


def limpiar_letra(texto: str, config) -> tuple[list[str], int]:
    """Convierte el texto pegado en líneas: quita vacías y etiquetas, ajusta
    las largas. Devuelve (líneas, cuántas se ajustaron)."""
    maximo = config.caracteres_por_linea
    accion = config.texto("letras", "accion_linea_larga")
    lineas, ajustadas = [], 0
    for renglon in texto.replace("\r", "\n").split("\n"):
        renglon = renglon.strip()
        if not renglon or es_etiqueta(renglon):
            continue
        partes = ajustar_linea(renglon, maximo, accion)
        if len(partes) != 1 or partes[0] != renglon:
            ajustadas += 1
        lineas.extend(partes)
    return lineas, ajustadas


def describir(lineas: list[str], ajustadas: int) -> str:
    if not lineas:
        return "Aún no hay líneas."
    texto = f"{len(lineas)} línea{'s' if len(lineas) != 1 else ''}"
    if ajustadas:
        texto += f" · {ajustadas} larga(s) se dividieron"
    return texto


class Importar(Pantalla):
    nombre_pantalla = "importar"
    titulo_aprendidas = StringProperty("")

    def al_entrar(self, **_):
        self.refrescar()

    def refrescar(self):
        caja = self.ids.aprendidas
        caja.clear_widgets()
        temporales = self.app.bd.listar_temporales()
        self.titulo_aprendidas = (f"APRENDIDAS POR EL MODO AUTOMÁTICO ({len(temporales)})"
                                  if temporales else "")
        for t in temporales:
            fila = FilaCancion(insignia="IA", titulo=t.nombre_sugerido or "Canción nueva",
                               subtitulo=f"{len(t.lineas)} líneas · {t.fecha}",
                               color_insignia=T.SECUNDARIO_SUAVE, color_texto_insignia=T.SECUNDARIO_TEXTO,
                               dato=t.id_temporal)
            fila.bind(on_release=lambda f: self.app.abrir("editor", id_temporal=f.dato))
            caja.add_widget(fila)

    def _informar(self, resultado):
        self.app.datos_cambiaron()
        agregadas, omitidas = len(resultado.agregadas), resultado.omitidas
        mensaje = f"Se agregaron {agregadas} canción(es)."
        if omitidas:
            mensaje += "\n\nNo se agregaron:\n" + "\n".join(f"· {n}: {m}" for n, m in omitidas[:6])
        dialogo = Dialogo(titulo="Importación terminada", mensaje=mensaje,
                          icono="check-circle" if agregadas else "information-outline")
        dialogo.agregar_boton("Ver biblioteca", "primario",
                              lambda: (self.app.ir_pestana("biblioteca")))
        dialogo.agregar_boton("Cerrar", "fantasma")
        dialogo.open()

    def importar_ruta(self, ruta: str | Path):
        try:
            self._informar(importar_archivo(self.app.bd, ruta, self.app.config_karaoke))
        except (OSError, ValueError) as ex:
            self.app.avisar(f"No se pudo leer el archivo: {ex}", "error")

    def importar_ejemplos(self):
        self.importar_ruta(self.app.carpeta / "ejemplos" / "canciones.txt")

    def importar_archivo(self):
        """Selector de archivos del sistema (Android) o ruta escrita."""
        try:
            from plyer import filechooser

            def elegido(rutas):
                if rutas:
                    Clock.schedule_once(lambda *_: self.importar_ruta(rutas[0]), 0)

            if platform == "android":
                filechooser.open_file(on_selection=elegido, filters=["*.txt", "text/plain"])
                return
        except Exception:
            pass
        self._pedir_ruta()

    # ------------------------------------------------ desde un MP3 con IA
    def desde_audio(self):
        """La IA (Whisper) escucha el audio y escribe la letra con el inicio de
        cada línea; se guarda con su pista (como f → m en la consola). Solo en
        la computadora: en el teléfono no está Whisper."""
        try:
            from karaoke.audio.proceso import whisper_disponible

            disponible = whisper_disponible()
        except Exception:
            disponible = False
        if not disponible:
            self.app.avisar("Escribir la letra con IA funciona en la computadora (necesita faster-whisper)", "error")
            return
        self._elegir_audio()

    def _elegir_audio(self):
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.modalview import ModalView

        filtros = [f"*.{e}" for e in ("mp3", "wav", "flac", "ogg", "m4a")]
        filtros += [f.upper() for f in filtros]
        ventana = ModalView(size_hint=(0.9, 0.85), background_color=(0, 0, 0, 0), overlay_color=T.VELO)
        caja = BoxLayout(orientation="vertical", spacing=T.ESP["s"], padding=T.ESP["m"])
        selector = FileChooserListView(path=str(Path.home()), filters=filtros)
        botones = BoxLayout(size_hint_y=None, height=T.ALTO_BOTON, spacing=T.ESP["s"])
        elegir = Boton(texto="Escribir la letra con IA", icono="waveform")
        cancelar = Boton(texto="Cancelar", estilo="fantasma")

        def usar(*_):
            ventana.dismiss()
            if selector.selection:
                self._transcribir(Path(selector.selection[0]))

        elegir.bind(on_release=usar)
        cancelar.bind(on_release=lambda *_: ventana.dismiss())
        botones.add_widget(cancelar)
        botones.add_widget(elegir)
        caja.add_widget(selector)
        caja.add_widget(botones)
        ventana.add_widget(caja)
        ventana.open()

    def _transcribir(self, ruta: Path):
        import threading

        dialogo = Dialogo(titulo="La IA está escuchando la canción", icono="waveform",
                          mensaje=f"{ruta.name}\nPreparando la pista… (tarda uno o dos minutos)")
        dialogo.auto_dismiss = False
        dialogo.open()

        def progreso(fraccion: float):
            texto = f"{ruta.name}\nEscribiendo la letra… {int(fraccion * 100)} %"
            Clock.schedule_once(lambda *_: setattr(dialogo, "mensaje", texto), 0)

        def trabajar():
            try:
                from karaoke.audio.desde_audio import crear_borrador

                borrador = crear_borrador(ruta, self.app.config_karaoke, None, progreso)
            except Exception as ex:
                error = f"No se pudo escribir la letra: {ex}"
                Clock.schedule_once(lambda *_: (dialogo.dismiss(), self.app.avisar(error, "error")), 0)
                return
            Clock.schedule_once(lambda *_: (dialogo.dismiss(), self._guardar_borrador(borrador)), 0)

        threading.Thread(target=trabajar, daemon=True).start()

    def _guardar_borrador(self, borrador):
        from karaoke.audio.desde_audio import guardar_pista, tiempos_para

        bd, config = self.app.bd, self.app.config_karaoke
        if not borrador.lineas:
            self.app.avisar("La IA no escuchó letra en la pista", "error")
            return
        try:
            existente = bd.existe_nombre(borrador.nombre)
            if existente is not None:
                # Como en la consola: ya estaba (por ejemplo, desde un .txt). Se le
                # asocia la pista y su letra se sincroniza sin cambiarla.
                cancion = bd.obtener_cancion(existente)
                bd.guardar_tiempos(existente, tiempos_para(cancion.lineas, borrador.palabras, borrador.duracion))
                codigo = existente
                mensaje = f"«{borrador.nombre}» ya existía: se le agregó la pista y su letra quedó sincronizada"
            else:
                codigo = bd.agregar_cancion(borrador.nombre, borrador.lineas, origen="audio", idioma=borrador.idioma)
                if len(borrador.tiempos) == len(borrador.lineas) and None not in borrador.tiempos:
                    bd.guardar_tiempos(codigo, borrador.tiempos)
                mensaje = f"La IA escribió {len(borrador.lineas)} líneas; revísalas con «Corregir»"
            bd.guardar_pista(codigo, guardar_pista(borrador.archivo, config, codigo, borrador.nombre))
        except Exception as ex:
            self.app.avisar(f"No se pudo guardar: {ex}", "error")
            return
        self.app.datos_cambiaron()
        self.app.avisar(mensaje)
        self.app.historial = ["biblioteca"]
        self.app.gestor.get_screen("detalle").codigo = codigo
        self.app.abrir("detalle", codigo=codigo)

    def _pedir_ruta(self):
        from ..componentes import Campo

        dialogo = Dialogo(titulo="Importar archivo", icono="file-document-outline",
                          mensaje="Escribe la ruta del archivo de texto.")
        campo = Campo(hint_text=str(self.app.carpeta / "canciones.txt"), multiline=False)
        dialogo.ids.botones.add_widget(campo)
        dialogo.agregar_boton("Importar", "primario",
                              lambda: self.importar_ruta(campo.text.strip() or campo.hint_text))
        dialogo.agregar_boton("Cancelar", "fantasma")
        dialogo.open()


class NuevaCancion(Pantalla):
    """Opción e (línea por línea) y "pegar letra"."""

    nombre_pantalla = "nueva"
    modo = StringProperty("pegar")
    resumen = StringProperty("")
    pista_linea = StringProperty("Línea 1")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lineas: list[str] = []
        Clock.schedule_once(self._enlazar, 0)

    def _enlazar(self, *_):
        self.ids.selector.bind(seleccion=lambda _s, v: setattr(self, "modo", v))

    def al_entrar(self, modo: str = "pegar", **_):
        self.ids.nombre.text = ""
        self.ids.letra.text = ""
        self.ids.linea.text = ""
        self.lineas = []
        self.ids.lista.clear_widgets()
        self.ids.selector.seleccion = modo
        self.modo = modo
        self.contar()
        Clock.schedule_once(lambda *_: setattr(self.ids.nombre, "focus", True), 0.35)

    def al_validar_nombre(self):
        destino = self.ids.linea if self.modo == "lineas" else self.ids.letra
        Clock.schedule_once(lambda *_: setattr(destino, "focus", True), 0.05)

    def on_modo(self, *_):
        self.contar()

    def contar(self):
        if self.modo == "pegar":
            lineas, ajustadas = limpiar_letra(self.ids.letra.text, self.app.config_karaoke)
            self.resumen = describir(lineas, ajustadas)
        else:
            self.resumen = describir(self.lineas, 0) + " · deja la línea vacía y presiona Enter para terminar"
            self.pista_linea = f"Línea {len(self.lineas) + 1}"

    def agregar_linea(self):
        texto = self.ids.linea.text.strip()
        if not texto:  # línea vacía: se terminó de ingresar la canción
            self.guardar()
            return
        nuevas, _ = limpiar_letra(texto, self.app.config_karaoke)
        for linea in nuevas:
            self.lineas.append(linea)
            self.ids.lista.add_widget(Texto(tipo="cuerpo",
                                            text=f"[color=6B7790]{len(self.lineas)}[/color]   {linea}"))
        self.ids.linea.text = ""
        self.contar()
        Clock.schedule_once(self._bajar_lista, 0.05)
        Clock.schedule_once(lambda *_: setattr(self.ids.linea, "focus", True), 0.05)

    def _bajar_lista(self, *_):
        vista = self.ids.lista_scroll
        if self.ids.lista.height > vista.height:
            vista.scroll_y = 0

    def guardar(self):
        nombre = self.ids.nombre.text.strip()
        if self.modo == "pegar":
            lineas, _ = limpiar_letra(self.ids.letra.text, self.app.config_karaoke)
        else:
            lineas = list(self.lineas)
        if not nombre:
            self.app.avisar("Escribe el nombre de la canción", "error")
            self.ids.nombre.focus = True
            return
        if not lineas:
            self.app.avisar("La canción necesita al menos una línea", "error")
            return
        try:
            codigo = self.app.bd.agregar_cancion(nombre, lineas, origen="manual")
        except (CancionDuplicada, ValueError) as ex:
            self.app.avisar(str(ex), "error")
            return
        self.app.datos_cambiaron()
        self.app.avisar(f"Guardada con el código {codigo}")
        self.app.historial = ["biblioteca"]
        self.app.gestor.get_screen("detalle").codigo = codigo
        self.app.abrir("detalle", codigo=codigo)


class EditorCancion(Pantalla):
    """Opción u (corregir) y revisión de canciones aprendidas."""

    nombre_pantalla = "editor"
    codigo = NumericProperty(0)
    id_temporal = NumericProperty(0)
    es_temporal = BooleanProperty(False)
    antetitulo = StringProperty("")
    resumen = StringProperty("")

    def al_entrar(self, codigo: int = 0, id_temporal: int = 0, **_):
        self.codigo, self.id_temporal = codigo, id_temporal
        self.es_temporal = bool(id_temporal)
        if self.es_temporal:
            temporal = self.app.bd.obtener_temporal(id_temporal)
            nombre, lineas = (temporal.nombre_sugerido, temporal.lineas) if temporal else ("", [])
            self.antetitulo = "NOMBRE SUGERIDO POR LA IA · CORRÍGELO SI HACE FALTA"
        else:
            cancion = self.app.bd.obtener_cancion(codigo)
            nombre, lineas = (cancion.nombre, cancion.lineas) if cancion else ("", [])
            self.antetitulo = f"CÓDIGO {codigo}"
        self.ids.nombre.text = nombre
        self.ids.letra.text = "\n".join(lineas)
        self.contar()

    def contar(self):
        lineas, ajustadas = limpiar_letra(self.ids.letra.text, self.app.config_karaoke)
        self.resumen = describir(lineas, ajustadas)

    def guardar(self):
        bd = self.app.bd
        nombre = self.ids.nombre.text.strip()
        lineas, _ = limpiar_letra(self.ids.letra.text, self.app.config_karaoke)
        try:
            if self.es_temporal:
                bd.actualizar_temporal(self.id_temporal, lineas)
                codigo = bd.promover_temporal(self.id_temporal, nombre)
                mensaje = f"Guardada en la biblioteca con el código {codigo}"
            else:
                bd.renombrar(self.codigo, nombre)
                bd.actualizar_letra(self.codigo, lineas)
                mensaje = "Cambios guardados"
        except (CancionDuplicada, ValueError) as ex:
            self.app.avisar(str(ex), "error")
            return
        self.app.datos_cambiaron()
        self.app.avisar(mensaje)
        self.app.atras()

    def descartar(self):
        from ..componentes import confirmar

        def hacer():
            self.app.bd.borrar_temporal(self.id_temporal)
            self.app.datos_cambiaron()
            self.app.atras()
            self.app.avisar("Canción aprendida descartada")

        confirmar("¿Descartar esta canción?", "Se borrará la letra que aprendió el modo automático.",
                  "Descartar", hacer, peligro=True, icono="delete-outline")
