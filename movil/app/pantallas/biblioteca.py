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
            do_scroll_y: False
            size_hint_y: None
            height: dp(30)
            bar_width: 0
            BoxLayout:
                id: filtros
                size_hint_x: None
                width: self.minimum_width
                spacing: T.ESP["s"]
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
                icono: "heart" if root.favorita else "heart-outline"
                fondo: 0, 0, 0, 0
                tinta: T.ACENTO_TEXTO if root.favorita else T.TEXTO_2
                lado: dp(44)
                pos_hint: {"center_y": .5}
                on_release: root.alternar_favorita()
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
                AsyncImage:
                    source: root.portada
                    size_hint: None, None
                    size: (dp(150), dp(150)) if root.portada else (0, 0)
                    opacity: 1 if root.portada else 0
                    allow_stretch: True
                    keep_ratio: True
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
                BoxLayout:
                    size_hint_y: None
                    height: dp(26)
                    spacing: T.ESP["s"]
                    ChipBoton:
                        text: "Género: " + (root.genero or "ninguno")
                        on_release: root.cambiar_genero()
                    ChipBoton:
                        text: "Cambiar portada" if root.portada else "Agregar portada"
                        on_release: root.elegir_portada()
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
    """Con filtros arriba: Todas, Favoritas y cada género o carpeta."""

    resumen = StringProperty("")
    filtro = StringProperty("")  # "" todas · "★" favoritas · otro texto = género
    pagina = NumericProperty(0)
    paginas = NumericProperty(1)
    rango = StringProperty("")

    def al_entrar(self, **_):
        self.refrescar()

    def refrescar(self):
        self._dibujar_filtros()
        self.buscar(self.ids.busqueda.text)

    def _dibujar_filtros(self):
        from ..componentes import ChipBoton

        caja = self.ids.filtros
        caja.clear_widgets()
        generos = [g for g, _ in self.app.bd.generos()]
        if self.filtro not in ("", "★") and self.filtro not in generos:
            self.filtro = ""
        for valor, texto in [("", "Todas"), ("★", "Favoritas")] + [(g, g) for g in generos]:
            chip = ChipBoton(text=texto)
            chip.activo = valor == self.filtro
            chip.bind(on_release=lambda c, v=valor: self._elegir_filtro(v))
            caja.add_widget(chip)

    def _elegir_filtro(self, valor: str):
        self.filtro = valor
        self.refrescar()

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
        if self.filtro:
            permitidos = {c for c, _, _ in (bd.listar_filtradas(favoritas=True) if self.filtro == "★"
                                             else bd.listar_filtradas(genero=self.filtro))}
            self._resultados = [f for f in self._resultados if f[0] in permitidos]
            self._mensaje_vacio = ("Aún no hay favoritas: toca el corazón en una canción." if self.filtro == "★"
                                   else f"No hay canciones en «{self.filtro}».")
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
        detalles = self.app.bd.detalles_listado()
        for codigo, nombre, lineas in visibles:
            favorita, genero = detalles.get(codigo, (False, ""))
            partes = [f"{lineas} líneas", "Inglés" if idiomas.get(codigo) == "en" else "Español"]
            partes += [genero] if genero else []
            partes += ["Favorita"] if favorita else []
            fila = FilaCancion(insignia=str(codigo), titulo=nombre, subtitulo=" · ".join(partes), dato=codigo)
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
    favorita = BooleanProperty(False)
    genero = StringProperty("")
    portada = StringProperty("")

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
        self.favorita, self.genero = cancion.favorita, cancion.genero or ""
        imagen = self.app.carpeta / cancion.portada if cancion.portada else None
        self.portada = str(imagen) if imagen and imagen.exists() else ""
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

    # ------------------------------------------ favorita, género y portada
    def alternar_favorita(self):
        self.app.bd.marcar_favorita(self.codigo, not self.favorita)
        self.app.datos_cambiaron()
        self.app.avisar("Agregada a favoritas" if self.favorita else "Quitada de favoritas")

    def cambiar_genero(self):
        from ..componentes import Campo, Dialogo

        dialogo = Dialogo(titulo="Género o carpeta", icono="tag-outline",
                          mensaje="Por ejemplo: Pop, Baladas, Mis canciones. Vacío para quitarlo.")
        campo = Campo(text=self.genero, multiline=False, hint_text="Género o carpeta")
        dialogo.ids.botones.add_widget(campo)

        def guardar():
            self.app.bd.establecer_genero(self.codigo, campo.text.strip())
            self.app.datos_cambiaron()

        dialogo.agregar_boton("Guardar", "primario", guardar)
        dialogo.agregar_boton("Cancelar", "fantasma")
        dialogo.open()

    def elegir_portada(self):
        from kivy.utils import platform

        def usar(rutas):
            if not rutas:
                return
            from kivy.clock import Clock

            Clock.schedule_once(lambda *_: self._guardar_portada(rutas[0]), 0)

        if platform == "android":
            try:
                from plyer import filechooser

                filechooser.open_file(on_selection=usar, filters=["*.jpg", "*.jpeg", "*.png", "*.webp"])
            except Exception as ex:
                self.app.avisar(f"No se pudo abrir la galería: {ex}", "error")
            return
        self._selector_escritorio(usar)

    def _selector_escritorio(self, usar):
        from pathlib import Path

        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.modalview import ModalView

        from ..componentes import Boton

        ventana = ModalView(size_hint=(0.9, 0.85), background_color=(0, 0, 0, 0), overlay_color=T.VELO)
        caja = BoxLayout(orientation="vertical", spacing=T.ESP["s"], padding=T.ESP["m"])
        selector = FileChooserListView(path=str(Path.home()),
                                       filters=["*.jpg", "*.jpeg", "*.png", "*.webp", "*.JPG", "*.PNG"])
        botones = BoxLayout(size_hint_y=None, height=T.ALTO_BOTON, spacing=T.ESP["s"])
        elegir = Boton(texto="Usar esta imagen", icono="image-outline")
        cancelar = Boton(texto="Cancelar", estilo="fantasma")
        elegir.bind(on_release=lambda *_: (ventana.dismiss(), usar(selector.selection)))
        cancelar.bind(on_release=lambda *_: ventana.dismiss())
        botones.add_widget(cancelar)
        botones.add_widget(elegir)
        caja.add_widget(selector)
        caja.add_widget(botones)
        ventana.add_widget(caja)
        ventana.open()

    def _guardar_portada(self, ruta: str):
        from pathlib import Path

        from karaoke.portadas import guardar_portada

        try:
            relativa = guardar_portada(self.app.carpeta, self.codigo, Path(ruta))
        except (OSError, ValueError) as ex:
            self.app.avisar(f"No se pudo guardar: {ex}", "error")
            return
        self.app.bd.establecer_portada(self.codigo, relativa)
        self.portada = ""  # fuerza recargar la imagen nueva
        self.app.datos_cambiaron()
        self.app.avisar("Portada guardada")

    def borrar(self):
        def hacer():
            self.app.bd.borrar_cancion(self.codigo)
            self.app.datos_cambiaron()
            self.app.atras()
            self.app.avisar("Canción borrada")

        confirmar("¿Borrar esta canción?",
                  f"Se borrará «{self.nombre}» y toda su letra. Esta acción no se puede deshacer.",
                  "Borrar", hacer, peligro=True, icono="delete-outline")
