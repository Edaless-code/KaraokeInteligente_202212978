"""Menús de la aplicación de consola.

Menú principal (primer nivel):

    (m) modo manual            (a) modo automático
    (f) modo alimentación      (p) programa tentativo del cantante
    (w) ver todas las canciones de 10 en 10
    (x) ver la letra de una canción por su código
    (u) corregir la letra de una canción
    (b) borrar una canción
    (h) historial y estadísticas   (extra)
    (d) diagnóstico de audio       (extra)
    (k) configuración              (extra)
    (s) salir
"""

from __future__ import annotations

from pathlib import Path

from ..buscador import Buscador
from ..config import Config
from ..db import BaseDatos, Cancion, CancionDuplicada
from ..importador import importar_archivo
from ..programa import cargar_programa, leer_programa
from ..texto import ajustar_linea
from . import consola
from .consola import Teclado, color
from .pantalla import paginar

OPCIONES_PRINCIPALES = [
    ("m", "Modo manual (buscar con palabras y avanzar con la tecla c)"),
    ("a", "Modo automático (escucha al cantante con inteligencia artificial)"),
    ("f", "Modo alimentación (agregar canciones a la base de datos)"),
    ("p", "Programa tentativo del cantante (archivo PROGRAMA)"),
    ("w", "Ver todos los códigos y nombres de canciones (de 10 en 10)"),
    ("x", "Ver la letra de una canción por su código (de 10 en 10)"),
    ("u", "Corregir la letra de una canción (por nombre o código)"),
    ("b", "Borrar una canción (por nombre o código)"),
    ("h", "Historial y estadísticas"),
    ("d", "Diagnóstico de audio (micrófono y limpieza del sonido)"),
    ("k", "Configuración"),
    ("s", "Salir"),
]


class Aplicacion:
    def __init__(self, config: Config, bd: BaseDatos, teclado: Teclado | None = None):
        self.config = config
        self.bd = bd
        self.teclado = teclado or Teclado()
        self.buscador = Buscador(bd, config)

    # ------------------------------------------------------------ utilidades
    def preguntar(self, mensaje: str) -> str:
        return self.teclado.linea(color(mensaje, "cian")).strip()

    def elegir_cancion(self, mensaje: str = "Nombre o código de la canción: ") -> Cancion | None:
        """Pide un nombre o código; si hay varias coincidencias deja elegir."""
        texto = self.preguntar(mensaje)
        if not texto:
            return None
        encontradas = self.bd.resolver(texto)
        if not encontradas:
            consola.error(f"No existe ninguna canción con el código o nombre «{texto}».")
            return None
        if len(encontradas) > 1:
            print("Se encontraron varias canciones:")
            for numero, (codigo, nombre) in enumerate(encontradas, 1):
                print(f"  {numero}. [{codigo}] {nombre}")
            eleccion = self.preguntar("Elija el número (Enter para cancelar): ")
            if not eleccion.isdigit() or not 1 <= int(eleccion) <= len(encontradas):
                return None
            codigo = encontradas[int(eleccion) - 1][0]
        else:
            codigo = encontradas[0][0]
        return self.bd.obtener_cancion(codigo)

    def leer_lineas(self, primera: int = 1) -> list[str]:
        """Pide líneas una por una; una línea vacía termina."""
        maximo = self.config.caracteres_por_linea
        accion = self.config.texto("letras", "accion_linea_larga")
        lineas: list[str] = []
        print(color(f"Escriba la letra línea por línea (máx. {maximo} caracteres). "
                    "Deje la línea vacía para terminar.", "tenue"))
        while True:
            texto = self.teclado.linea(f"  Línea {primera + len(lineas)}: ").strip()
            if not texto:
                return lineas
            partes = ajustar_linea(texto, maximo, accion)
            if len(partes) > 1 or partes[0] != texto:
                consola.aviso(f"  La línea tenía {len(texto)} caracteres; se ajustó ({accion}).")
            lineas.extend(partes)

    # --------------------------------------------------------- menú principal
    def ejecutar(self) -> None:
        acciones = {
            "m": self.modo_manual,
            "a": self.modo_automatico,
            "f": self.menu_alimentacion,
            "p": self.menu_programa,
            "w": self.ver_canciones,
            "x": self.ver_letra,
            "u": self.corregir_cancion,
            "b": self.borrar_cancion,
            "h": self.ver_historial,
            "k": self.ver_configuracion,
            "d": self.diagnostico,
        }
        while True:
            consola.limpiar()
            consola.titulo("KARAOKE INTELIGENTE · Menú principal")
            print(color(f"  Canciones en la base de datos: {self.bd.contar_canciones()}", "tenue"))
            pendientes = len(self.bd.listar_temporales())
            if pendientes:
                consola.aviso(f"  Hay {pendientes} canción(es) aprendida(s) por revisar en (f) → (v).")
            print()
            for tecla, texto in OPCIONES_PRINCIPALES:
                print(f"  ({color(tecla, 'negrita', 'amarillo')}) {texto}")
            print()
            opcion = self.teclado.linea(color("Elija una opción: ", "cian")).strip().lower()[:1]
            if opcion == "s":
                return
            accion = acciones.get(opcion)
            if accion is None:
                continue
            try:
                accion()
            except (KeyboardInterrupt, EOFError):
                raise
            except Exception as ex:  # el programa nunca debe cerrarse por un error
                consola.error(f"Ocurrió un error: {ex}")
                self.teclado.pausa()

    # Los modos de canto se implementan en sus propios módulos.
    def modo_manual(self) -> None:
        from .modo_manual import ModoManual

        ModoManual(self).ejecutar()

    def diagnostico(self) -> None:
        from .diagnostico import Diagnostico

        Diagnostico(self).ejecutar()

    def modo_automatico(self) -> None:
        from .modo_automatico import ModoAutomatico

        ModoAutomatico(self).ejecutar()

    # ------------------------------------------------------------- (w) y (x)
    def ver_canciones(self) -> None:
        canciones = self.bd.listar_canciones()
        if not canciones:
            consola.aviso("La base de datos no tiene canciones. Use (f) para agregarlas.")
            self.teclado.pausa()
            return
        renglones = [f"  {'CÓDIGO':>6}  {'NOMBRE DE LA CANCIÓN':<50} LÍNEAS"]
        datos = [f"  {c:>6}  {n[:50]:<50} {l:>6}" for c, n, l in canciones]
        paginar(datos, self.config.por_pagina, self.teclado,
                f"Canciones registradas ({len(canciones)})\n{renglones[0]}")

    def ver_letra(self) -> None:
        texto = self.preguntar("Ingrese el código de la canción: ")
        if not texto:
            return
        if not texto.isdigit():
            consola.error("El código debe ser un número entero.")
            self.teclado.pausa()
            return
        cancion = self.bd.obtener_cancion(int(texto))
        if cancion is None:
            consola.error(f"NO EXISTE ninguna canción con el código {texto}.")
            self.teclado.pausa()
            return
        renglones = [f"  {i:>3}. {l}" for i, l in enumerate(cancion.lineas, 1)]
        paginar(renglones, self.config.por_pagina, self.teclado,
                f"[{cancion.codigo}] {cancion.nombre}  ({len(cancion.lineas)} líneas, idioma {cancion.idioma})")

    # ------------------------------------------------------------------ (u)
    def corregir_cancion(self) -> None:
        consola.titulo("Corregir una canción")
        cancion = self.elegir_cancion()
        if cancion is None:
            self.teclado.pausa()
            return
        lineas = self.editar_lineas(cancion.nombre, list(cancion.lineas), permitir_renombrar=True)
        if lineas is None:
            consola.aviso("No se guardaron cambios.")
        elif isinstance(lineas, tuple):
            nombre, nuevas = lineas
            try:
                if nombre != cancion.nombre:
                    self.bd.renombrar(cancion.codigo, nombre)
                self.bd.actualizar_letra(cancion.codigo, nuevas)
                consola.exito(f"Canción [{cancion.codigo}] actualizada.")
            except (CancionDuplicada, ValueError) as ex:
                consola.error(str(ex))
        self.teclado.pausa()

    def editar_lineas(
        self, nombre: str, lineas: list[str], permitir_renombrar: bool = False
    ) -> tuple[str, list[str]] | None:
        """Editor sencillo de la letra. Devuelve (nombre, líneas) al guardar o
        ``None`` si se cancela."""
        maximo = self.config.caracteres_por_linea
        accion = self.config.texto("letras", "accion_linea_larga")
        while True:
            consola.limpiar()
            consola.titulo(f"Editando: {nombre}")
            for i, linea in enumerate(lineas, 1):
                print(f"  {i:>3}. {linea}")
            print()
            ayuda = ("[e N] editar línea N   [i N] insertar antes de N   [d N] borrar línea N\n"
                     "[a] agregar líneas al final   [t] reemplazar toda la letra")
            if permitir_renombrar:
                ayuda += "   [n] cambiar nombre"
            ayuda += "\n[g] guardar   [c] cancelar"
            print(color(ayuda, "cian"))
            orden = self.preguntar("Orden: ").lower().split()
            if not orden:
                continue
            comando = orden[0]
            numero = int(orden[1]) if len(orden) > 1 and orden[1].isdigit() else None
            if comando == "g":
                if not lineas:
                    consola.error("La canción debe tener al menos una línea.")
                    self.teclado.pausa()
                    continue
                return nombre, lineas
            if comando == "c":
                return None
            if comando == "n" and permitir_renombrar:
                nuevo = self.preguntar(f"Nuevo nombre [{nombre}]: ")
                nombre = nuevo or nombre
            elif comando == "a":
                lineas.extend(self.leer_lineas(len(lineas) + 1))
            elif comando == "t":
                nuevas = self.leer_lineas()
                if nuevas:
                    lineas = nuevas
            elif comando in ("e", "i", "d"):
                if numero is None:
                    numero_texto = self.preguntar("Número de línea: ")
                    numero = int(numero_texto) if numero_texto.isdigit() else None
                limite = len(lineas) + (1 if comando == "i" else 0)
                if numero is None or not 1 <= numero <= limite:
                    consola.error("Número de línea inválido.")
                    self.teclado.pausa()
                    continue
                if comando == "d":
                    del lineas[numero - 1]
                    continue
                if comando == "e":
                    print(color(f"  Actual: {lineas[numero - 1]}", "tenue"))
                texto = self.preguntar("  Nuevo texto: ")
                if not texto:
                    continue
                partes = ajustar_linea(texto, maximo, accion)
                if comando == "e":
                    lineas[numero - 1 : numero] = partes
                else:
                    lineas[numero - 1 : numero - 1] = partes

    # ------------------------------------------------------------------ (b)
    def borrar_cancion(self) -> None:
        consola.titulo("Borrar una canción")
        cancion = self.elegir_cancion()
        if cancion is None:
            self.teclado.pausa()
            return
        print(f"\n  [{cancion.codigo}] {cancion.nombre} ({len(cancion.lineas)} líneas)")
        for linea in cancion.lineas[:3]:
            print(color(f"      {linea}", "tenue"))
        if self.teclado.confirmar(color(
            f"¿Está SEGURO de borrar «{cancion.nombre}» y toda su letra? No se puede deshacer",
            "rojo", "negrita")):
            self.bd.borrar_cancion(cancion.codigo)
            consola.exito("Canción borrada.")
        else:
            consola.aviso("No se borró nada.")
        self.teclado.pausa()

    # ------------------------------------------------------------------ (f)
    def menu_alimentacion(self) -> None:
        while True:
            consola.limpiar()
            consola.titulo("Modo alimentación")
            print("  (t) Leer canciones de un archivo de texto plano")
            print("  (e) Escribir una canción en pantalla (campo por campo)")
            temporales = len(self.bd.listar_temporales())
            print(f"  (v) Revisar canciones aprendidas por el modo automático ({temporales})")
            print("  (r) Regresar")
            opcion = self.preguntar("Opción: ").lower()[:1]
            if opcion == "t":
                self.alimentar_archivo()
            elif opcion == "e":
                self.alimentar_manual()
            elif opcion == "v":
                self.revisar_temporales()
            elif opcion in ("r", "q", ""):
                return

    def alimentar_archivo(self) -> None:
        predeterminado = self.config.carpeta / "canciones.txt"
        ruta_texto = self.preguntar(f"Ruta del archivo [{predeterminado}]: ").strip('"')
        ruta = Path(ruta_texto) if ruta_texto else predeterminado
        if not ruta.is_absolute() and not ruta.exists():
            ruta = self.config.carpeta / ruta
        if not ruta.exists():
            consola.error(f"No se encontró el archivo {ruta}")
            self.teclado.pausa()
            return
        resultado = importar_archivo(self.bd, ruta, self.config)
        for codigo, nombre in resultado.agregadas:
            consola.exito(f"  + [{codigo}] {nombre}")
        for nombre, motivo in resultado.omitidas:
            consola.aviso(f"  - {nombre}: {motivo}")
        print(f"\nAgregadas: {len(resultado.agregadas)}   Omitidas: {len(resultado.omitidas)}"
              f"   Líneas ajustadas por longitud: {resultado.lineas_ajustadas}")
        self.teclado.pausa()

    def alimentar_manual(self) -> None:
        consola.titulo("Nueva canción")
        while True:
            nombre = self.preguntar("Nombre de la canción (vacío para cancelar): ")
            if not nombre:
                return
            existente = self.bd.existe_nombre(nombre)
            if existente is None:
                break
            consola.error(f"Ya existe la canción [{existente}] con ese nombre.")
        lineas = self.leer_lineas()
        if not lineas:
            consola.aviso("La canción no tiene letra; no se guardó.")
            self.teclado.pausa()
            return
        promedio = self.config.entero("letras", "lineas_promedio_cancion")
        if len(lineas) < promedio // 3:
            consola.aviso(f"Aviso: la canción tiene solo {len(lineas)} líneas (promedio {promedio}).")
        codigo = self.bd.agregar_cancion(nombre, lineas, origen="manual")
        consola.exito(f"Canción guardada con el código {codigo} ({len(lineas)} líneas).")
        self.teclado.pausa()

    def revisar_temporales(self) -> None:
        while True:
            temporales = self.bd.listar_temporales()
            consola.limpiar()
            consola.titulo("Canciones aprendidas (tablas temporales)")
            if not temporales:
                consola.aviso("No hay canciones pendientes de revisar.")
                self.teclado.pausa()
                return
            for t in temporales:
                print(f"  {t.id_temporal:>3}. «{t.nombre_sugerido or 'sin nombre'}» "
                      f"{len(t.lineas)} líneas · {t.fecha} · {t.motor}")
            elegido = self.preguntar("Número a revisar (Enter para regresar): ")
            if not elegido.isdigit():
                return
            temporal = self.bd.obtener_temporal(int(elegido))
            if temporal is None:
                continue
            resultado = self.editar_lineas(
                temporal.nombre_sugerido or "Canción nueva", list(temporal.lineas)
            )
            if resultado is None:
                if self.teclado.confirmar("¿Descartar esta canción aprendida?"):
                    self.bd.borrar_temporal(temporal.id_temporal)
                continue
            _, lineas = resultado
            self.bd.actualizar_temporal(temporal.id_temporal, lineas)
            nombre = self.preguntar(
                f"Nombre definitivo [{temporal.nombre_sugerido}] (Enter = sugerido): "
            ) or temporal.nombre_sugerido
            try:
                codigo = self.bd.promover_temporal(temporal.id_temporal, nombre)
                consola.exito(f"Guardada en la base de datos permanente con el código {codigo}.")
            except (CancionDuplicada, ValueError) as ex:
                consola.error(str(ex))
            self.teclado.pausa()

    # ------------------------------------------------------------------ (p)
    def ruta_programa(self) -> Path:
        ruta = self.config.ruta("programa", "archivo")
        sin_extension = ruta.with_suffix("")
        if not ruta.exists() and sin_extension.exists():
            return sin_extension  # se acepta "PROGRAMA" sin extensión
        return ruta

    def menu_programa(self) -> None:
        while True:
            consola.limpiar()
            consola.titulo("Programa tentativo del cantante")
            entradas = self.bd.obtener_programa()
            print(color(f"  Canciones en el programa: {len(entradas)}", "tenue"))
            print("  (c) Cargar el archivo PROGRAMA")
            print("  (e) Escribir el programa en pantalla")
            print("  (v) Ver el programa y su avance")
            print("  (l) Volver a poner todas como pendientes")
            print("  (r) Regresar")
            opcion = self.preguntar("Opción: ").lower()[:1]
            if opcion == "c":
                self.cargar_programa_archivo()
            elif opcion == "e":
                self.escribir_programa()
            elif opcion == "v":
                self.ver_programa()
            elif opcion == "l":
                self.bd.reiniciar_programa()
                consola.exito("Todas las canciones del programa quedaron pendientes.")
                self.teclado.pausa()
            elif opcion in ("r", "q", ""):
                return

    def _informar_programa(self, entradas: list[tuple[str, int | None]]) -> None:
        for orden, (nombre, codigo) in enumerate(entradas, 1):
            if codigo is None:
                consola.aviso(f"  {orden:>2}. {nombre}  → NO está en la base de datos")
            else:
                consola.exito(f"  {orden:>2}. {nombre}  → código {codigo}")
        self.teclado.pausa()

    def cargar_programa_archivo(self) -> None:
        predeterminado = self.ruta_programa()
        texto = self.preguntar(f"Ruta del archivo [{predeterminado}]: ").strip('"')
        ruta = Path(texto) if texto else predeterminado
        if not ruta.exists():
            consola.error(f"No se encontró el archivo {ruta}")
            self.teclado.pausa()
            return
        nombres = leer_programa(ruta)
        if not nombres:
            consola.aviso("El archivo no tiene canciones.")
            self.teclado.pausa()
            return
        self._informar_programa(cargar_programa(self.bd, nombres))

    def escribir_programa(self) -> None:
        print(color("Escriba el nombre de cada canción en orden. Línea vacía para terminar.", "tenue"))
        nombres = []
        while True:
            nombre = self.teclado.linea(f"  {len(nombres) + 1}. ").strip()
            if not nombre:
                break
            nombres.append(nombre)
        if not nombres:
            return
        ruta = self.config.ruta("programa", "archivo")
        try:
            ruta.write_text("\n".join(f"{i}. {n}" for i, n in enumerate(nombres, 1)) + "\n",
                            encoding="utf-8")
            consola.exito(f"Programa guardado también en {ruta}")
        except OSError as ex:
            consola.aviso(f"No se pudo guardar el archivo: {ex}")
        self._informar_programa(cargar_programa(self.bd, nombres))

    def ver_programa(self) -> None:
        entradas = self.bd.obtener_programa()
        if not entradas:
            consola.aviso("No hay programa cargado.")
            self.teclado.pausa()
            return
        marcas = {"pendiente": "·", "cantada": "✓", "saltada": "»"}
        renglones = [
            f"  {e.orden:>2}. {marcas.get(e.estado, '?')} {e.nombre_solicitado:<45} "
            f"{'[' + str(e.codigo) + ']' if e.codigo else '(no está en la base)'}  {e.estado}"
            for e in entradas
        ]
        paginar(renglones, self.config.por_pagina, self.teclado, "Programa del cantante")

    # ------------------------------------------------------------- extras
    def ver_historial(self) -> None:
        renglones = ["Canciones más cantadas:"]
        for codigo, nombre, veces in self.bd.mas_cantadas():
            renglones.append(f"  [{codigo}] {nombre}: {veces} vez/veces")
        renglones.append("")
        renglones.append("Últimas interpretaciones:")
        for fila in self.bd.historial():
            estado = "completa" if fila["completada"] else "incompleta"
            renglones.append(f"  sesión {fila['id_sesion']} · {fila['inicio']} · {fila['modo']} · "
                             f"{fila['nombre_cancion']} · {estado}")
        paginar(renglones, max(self.config.por_pagina, 15), self.teclado, "Historial y estadísticas")

    def ver_configuracion(self) -> None:
        consola.titulo("Configuración")
        print(f"  Archivo de configuración: {self.config.carpeta / 'karaoke.ini'}")
        print(f"  Base de datos:            {self.config.ruta_bd}")
        print(f"  Programa del cantante:    {self.ruta_programa()}")
        print(f"  Caracteres por línea:     {self.config.caracteres_por_linea}"
              f" (líneas largas: {self.config.texto('letras', 'accion_linea_larga')})")
        print(f"  Líneas promedio canción:  {self.config.entero('letras', 'lineas_promedio_cancion')}")
        print(f"  Elementos por página:     {self.config.por_pagina}")
        print(f"  Motor de transcripción:   {self.config.texto('audio', 'motor')}")
        print(color("\n  Para cambiar estos valores edite karaoke.ini con el Bloc de notas y "
                    "vuelva a abrir el programa.", "tenue"))
        self.teclado.pausa()
