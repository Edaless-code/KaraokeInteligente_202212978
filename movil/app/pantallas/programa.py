"""Programa tentativo del cantante (opción p)."""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import BooleanProperty, StringProperty

from karaoke.programa import cargar_programa, leer_programa

from .. import tema as T
from ..componentes import Campo, Dialogo, FilaCancion, confirmar
from .base import Pantalla

Builder.load_string("""
#:import T app.tema

<ProgramaPantalla>:
    BoxLayout:
        orientation: "vertical"
        padding: T.ESP["l"], T.ESP["xl"], T.ESP["l"], T.ESP["m"]
        spacing: T.ESP["m"]
        EncabezadoGrande:
            antetitulo: root.resumen
            titulo: "Programa"
        Tarjeta:
            opacity: 1 if root.vacio else 0
            height: self.minimum_height if root.vacio else 0
            padding: T.ESP["xl"] if root.vacio else 0
            Icono:
                nombre: "playlist-music"
                tamano: dp(34)
                tono: T.ACENTO_TEXTO
                pos_hint: {"center_x": .5}
            Texto:
                tipo: "encabezado"
                alineacion: "center"
                text: "Planea tu sesión"
            Texto:
                tipo: "nota"
                tono: T.TEXTO_2
                alineacion: "center"
                text: "Escribe las canciones en el orden que piensas cantarlas. El orden es flexible: puedes adelantarte, repetir o saltarte canciones."
        ScrollView:
            do_scroll_x: False
            BoxLayout:
                id: lista
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
        BoxLayout:
            size_hint_y: None
            height: T.ALTO_BOTON
            spacing: T.ESP["s"]
            Boton:
                texto: "Escribir"
                icono: "pencil"
                on_release: root.escribir()
            Boton:
                texto: "Importar"
                icono: "import"
                estilo: "secundario"
                on_release: root.importar()
            BotonIcono:
                icono: "restart"
                lado: T.ALTO_BOTON
                opacity: 0 if root.vacio else 1
                disabled: root.vacio
                on_release: root.reiniciar()
""")

ESTADOS = {
    "pendiente": ("Pendiente", T.ACENTO_SUAVE, T.ACENTO_TEXTO),
    "cantada": ("Cantada", T.EXITO_SUAVE, T.EXITO),
    "saltada": ("Saltada", T.SUPERFICIE_ALTA, T.TEXTO_3),
}


class ProgramaPantalla(Pantalla):
    nombre_pantalla = "programa"
    resumen = StringProperty("")
    vacio = BooleanProperty(True)

    def al_entrar(self, **_):
        self.refrescar()

    def refrescar(self):
        bd = self.app.bd
        bd.vincular_programa()
        entradas = bd.obtener_programa()
        self.vacio = not entradas
        pendientes = sum(1 for e in entradas if e.estado == "pendiente")
        self.resumen = f"{pendientes} de {len(entradas)} pendientes" if entradas else "Sin programa"
        lista = self.ids.lista
        lista.clear_widgets()
        for entrada in entradas:
            estado, fondo, tinta = ESTADOS.get(entrada.estado, ESTADOS["pendiente"])
            if entrada.codigo is None:
                estado, fondo, tinta = "No está en la biblioteca", T.AVISO_SUAVE, T.AVISO
            fila = FilaCancion(insignia=str(entrada.orden), titulo=entrada.nombre_solicitado,
                               subtitulo=estado, color_insignia=fondo, color_texto_insignia=tinta,
                               icono_derecho="play" if entrada.codigo else "",
                               dato=entrada.codigo)
            fila.bind(on_release=self._cantar)
            lista.add_widget(fila)

    def _cantar(self, fila):
        if fila.dato is not None:
            self.app.abrir("escenario", modo="manual", codigo=fila.dato, linea=0)

    def _guardar(self, nombres: list[str]):
        if not nombres:
            return
        entradas = cargar_programa(self.app.bd, nombres)
        faltan = [n for n, c in entradas if c is None]
        self.app.datos_cambiaron()
        if faltan:
            self.app.avisar(f"{len(faltan)} canción(es) no están en la biblioteca", "info")
        else:
            self.app.avisar(f"Programa con {len(entradas)} canciones")
        try:  # también se guarda como archivo PROGRAMA.txt
            ruta = self.app.config_karaoke.ruta("programa", "archivo")
            ruta.write_text("\n".join(f"{i}. {n}" for i, n in enumerate(nombres, 1)) + "\n",
                            encoding="utf-8")
        except OSError:
            pass

    def escribir(self):
        actuales = "\n".join(e.nombre_solicitado for e in self.app.bd.obtener_programa())
        dialogo = Dialogo(titulo="Escribir el programa", icono="format-list-numbered",
                          mensaje="Una canción por renglón, en el orden que se piensa cantar.")
        campo = Campo(text=actuales, multiline=True, hint_text="Ghost of you\nSound of You")
        dialogo.ids.botones.add_widget(campo)
        dialogo.agregar_boton("Guardar programa", "primario",
                              lambda: self._guardar([n.strip() for n in campo.text.splitlines() if n.strip()]))
        dialogo.agregar_boton("Cancelar", "fantasma")
        dialogo.open()

    def importar(self):
        ruta = self.app.config_karaoke.ruta("programa", "archivo")
        if not ruta.exists() and ruta.with_suffix("").exists():
            ruta = ruta.with_suffix("")

        def leer(destino):
            try:
                self._guardar(leer_programa(destino))
            except (OSError, ValueError) as ex:
                self.app.avisar(f"No se pudo leer: {ex}", "error")

        try:
            from kivy.utils import platform
            from plyer import filechooser

            if platform == "android":
                filechooser.open_file(on_selection=lambda r: r and leer(r[0]))
                return
        except Exception:
            pass
        if ruta.exists():
            leer(ruta)
        else:
            self.app.avisar(f"No se encontró {ruta.name}", "error")

    def reiniciar(self):
        def hacer():
            self.app.bd.reiniciar_programa()
            self.app.datos_cambiaron()
            self.app.avisar("Todas las canciones quedaron pendientes")

        confirmar("¿Reiniciar el avance?", "Todas las canciones del programa volverán a estar pendientes.",
                  "Reiniciar", hacer, icono="restart")
