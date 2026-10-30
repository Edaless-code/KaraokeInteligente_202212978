"""Biblioteca: lista de canciones (w), ver la letra (x), corregir (u) y
borrar (b)."""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty

from .. import tema as T
from ..componentes import FilaCancion, FilaLetra, Texto, confirmar
from .base import Pantalla

Builder.load_string("""
#:import T app.tema

<Biblioteca>:
    BoxLayout:
        orientation: "vertical"
        padding: T.ESP["l"], T.ESP["xl"], T.ESP["l"], 0
        spacing: T.ESP["m"]
        BoxLayout:
            size_hint_y: None
            height: titulo.height
            EncabezadoGrande:
                id: titulo
                antetitulo: root.resumen
                titulo: "Biblioteca"
            BotonIcono:
                icono: "plus"
                fondo: T.ACENTO
                tinta: T.color("#F3F6FC")
                lado: dp(44)
                pos_hint: {"center_y": .35}
                on_release: app.abrir("importar")
        Campo:
            id: busqueda
            hint_text: "Buscar por nombre o código"
            multiline: False
            on_text: root.buscar(self.text)
        ScrollView:
            do_scroll_x: False
            BoxLayout:
                id: lista
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                spacing: 0
        BoxLayout:
            size_hint_y: None
            height: dp(56) if root.paginas > 1 else 0
            opacity: 1 if root.paginas > 1 else 0
            spacing: T.ESP["m"]
            BotonIcono:
                icono: "chevron-left"
                lado: dp(40)
                disabled: root.pagina == 0
                opacity: .35 if self.disabled else 1
                pos_hint: {"center_y": .5}
                on_release: root.cambiar_pagina(-1)
            Texto:
                tipo: "nota"
                tono: T.TEXTO_2
                alineacion: "center"
                text: root.rango
                pos_hint: {"center_y": .5}
            BotonIcono:
                icono: "chevron-right"
                lado: dp(40)
                disabled: root.pagina >= root.paginas - 1
                opacity: .35 if self.disabled else 1
                pos_hint: {"center_y": .5}
                on_release: root.cambiar_pagina(1)

<DetalleCancion>:
    con_pestanas: False
    BoxLayout:
        orientation: "vertical"
        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: T.ESP["s"], 0
            spacing: T.ESP["s"]
            BotonIcono:
                icono: "chevron-left"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: app.atras()
            Widget:
            BotonIcono:
                icono: "pencil"
                fondo: 0, 0, 0, 0
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: app.abrir("editor", codigo=root.codigo)
            BotonIcono:
                icono: "delete-outline"
                fondo: 0, 0, 0, 0
                tinta: T.PELIGRO
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: root.borrar()
        ScrollView:
            do_scroll_x: False
            BoxLayout:
                orientation: "vertical"
                padding: T.ESP["l"], 0, T.ESP["l"], T.ESP["xl"]
                spacing: T.ESP["m"]
                size_hint_y: None
                height: self.minimum_height
                Texto:
                    tipo: "mini"
                    tono: T.ACENTO_TEXTO
                    text: root.antetitulo
                Texto:
                    tipo: "titulo_grande"
                    text: root.nombre
                BoxLayout:
                    size_hint_y: None
                    height: dp(26)
                    spacing: T.ESP["s"]
                    Chip:
                        text: root.chip_lineas
                    Chip:
                        text: root.chip_idioma
                    Chip:
                        text: root.chip_veces
                    Widget:
                Boton:
                    texto: "Reproducir con letra"
                    icono: "playlist-play"
                    size_hint_y: None
                    height: T.ALTO_BOTON if root.con_pista else 0
                    opacity: 1 if root.con_pista else 0
                    disabled: not root.con_pista
                    on_release: app.abrir("escenario", modo="pista", codigo=root.codigo)
                Boton:
                    texto: "Cantar sin pista (avanzar a mano)" if root.con_pista else "Cantar esta canción"
                    icono: "play"
                    estilo: "secundario" if root.con_pista else "primario"
                    on_release: app.abrir("escenario", modo="manual", codigo=root.codigo, linea=0)
                BoxLayout:
                    id: letra
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: T.ESP["m"]
                    padding: 0, T.ESP["s"], 0, 0
""")

POR_PAGINA = 10


class Biblioteca(Pantalla):
    resumen = StringProperty("")
    pagina = NumericProperty(0)
    paginas = NumericProperty(1)
    rango = StringProperty("")

    def al_entrar(self, **_):
        self.refrescar()

    def refrescar(self):
        self.buscar(self.ids.busqueda.text)

    def buscar(self, texto: str):
        bd = self.app.bd
        texto = texto.strip()
        if texto.isdigit():
            cancion = bd.obtener_cancion(int(texto))
            self._resultados = [(cancion.codigo, cancion.nombre, len(cancion.lineas))] if cancion else []
            self._mensaje_vacio = f"No existe ninguna canción con el código {texto}."
        elif texto:
            encontrados = {c for c, _ in bd.buscar_por_nombre(texto, limite=50)}
            self._resultados = [f for f in bd.listar_canciones() if f[0] in encontrados]
            self._mensaje_vacio = f"Ninguna canción se llama «{texto}»."
        else:
            self._resultados = bd.listar_canciones()
            self._mensaje_vacio = "Aún no hay canciones. Toca + para agregarlas."
        total = bd.contar_canciones()
        self.resumen = f"{total} canción" if total == 1 else f"{total} canciones"
        self.pagina = 0
        self._dibujar()

    def cambiar_pagina(self, paso: int):
        self.pagina = max(0, min(self.paginas - 1, self.pagina + paso))
        self._dibujar()

    def _dibujar(self):
        lista = self.ids.lista
        lista.clear_widgets()
        total = len(self._resultados)
        self.paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
        desde = self.pagina * POR_PAGINA
        visibles = self._resultados[desde: desde + POR_PAGINA]
        self.rango = f"{desde + 1}–{desde + len(visibles)} de {total}" if total else ""
        if not visibles:
            lista.add_widget(Texto(text=self._mensaje_vacio, tipo="cuerpo", tono=T.TEXTO_2,
                                   alineacion="center", padding=(0, T.ESP["xxl"])))
            return
        idiomas = {c: x.idioma for c, x in self.app.bd.todas_las_letras().items()}
        for codigo, nombre, lineas in visibles:
            fila = FilaCancion(insignia=str(codigo), titulo=nombre,
                               subtitulo=f"{lineas} líneas · {'Inglés' if idiomas.get(codigo) == 'en' else 'Español'}",
                               dato=codigo)
            fila.bind(on_release=lambda f: self.app.abrir("detalle", codigo=f.dato))
            lista.add_widget(fila)


class DetalleCancion(Pantalla):
    """Letra completa en grupos de 10 líneas (opción x)."""

    codigo = NumericProperty(0)
    nombre = StringProperty("")
    antetitulo = StringProperty("")
    chip_lineas = StringProperty("")
    chip_idioma = StringProperty("")
    chip_veces = StringProperty("")
    existe = BooleanProperty(True)
    con_pista = BooleanProperty(False)

    def al_entrar(self, codigo: int = 0, **_):
        if codigo:
            self.codigo = codigo
        self.refrescar()

    def refrescar(self):
        cancion = self.app.bd.obtener_cancion(self.codigo)
        caja = self.ids.letra
        caja.clear_widgets()
        if cancion is None:
            self.nombre = "No existe"
            self.antetitulo = f"CÓDIGO {self.codigo}"
            self.chip_lineas = self.chip_idioma = self.chip_veces = ""
            return
        self.nombre = cancion.nombre
        archivo = self.app.bd.obtener_pista(cancion.codigo)
        self.con_pista = bool(archivo) and (self.app.carpeta / archivo).exists()
        self.antetitulo = f"CÓDIGO {cancion.codigo}"
        self.chip_lineas = f"{len(cancion.lineas)} líneas"
        self.chip_idioma = "Inglés" if cancion.idioma == "en" else "Español"
        self.chip_veces = f"Cantada {cancion.veces_cantada} {'vez' if cancion.veces_cantada == 1 else 'veces'}"
        for inicio in range(0, len(cancion.lineas), POR_PAGINA):
            grupo = cancion.lineas[inicio: inicio + POR_PAGINA]
            caja.add_widget(Texto(tipo="mini", tono=T.TEXTO_3,
                                  text=f"LÍNEAS {inicio + 1}–{inicio + len(grupo)}"))
            for numero, linea in enumerate(grupo, inicio + 1):
                caja.add_widget(FilaLetra(numero=str(numero), texto=linea))

    def borrar(self):
        def hacer():
            self.app.bd.borrar_cancion(self.codigo)
            self.app.datos_cambiaron()
            self.app.atras()
            self.app.avisar("Canción borrada")

        confirmar("¿Borrar esta canción?",
                  f"Se borrará «{self.nombre}» y toda su letra. Esta acción no se puede deshacer.",
                  "Borrar", hacer, peligro=True, icono="delete-outline")
