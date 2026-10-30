"""Acceso a la base de datos SQLite "CANCIONES".

Tablas (ver el manual técnico para el detalle de cada campo):

* ``NOMBRES``      código y nombre de cada canción (tabla de la especificación).
* ``LETRAS``       una fila por línea de la letra, enlazada por ``codigo``.
* ``TEMP_NOMBRES`` y ``TEMP_LETRAS``  canciones aprendidas por el modo
  automático que todavía no se han revisado (tablas temporales).
* ``PROGRAMA``     lista preplaneada de canciones del cantante.
* ``SESIONES`` e ``HISTORIAL``  registro de lo que se cantó en cada sesión.
* ``METADATOS``    versión del esquema.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .texto import detectar_idioma, normalizar, semejanza

VERSION_ESQUEMA = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS NOMBRES (
    codigo              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_cancion      TEXT    NOT NULL,
    nombre_normalizado  TEXT    NOT NULL UNIQUE,
    artista             TEXT    NOT NULL DEFAULT '',
    idioma              TEXT    NOT NULL DEFAULT 'es',
    origen              TEXT    NOT NULL DEFAULT 'manual',
    fecha_registro      TEXT    NOT NULL,
    veces_cantada       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS LETRAS (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo              INTEGER NOT NULL
                        REFERENCES NOMBRES(codigo) ON DELETE CASCADE,
    numero_linea        INTEGER NOT NULL,
    linea               TEXT    NOT NULL,
    linea_normalizada   TEXT    NOT NULL,
    UNIQUE (codigo, numero_linea)
);
CREATE INDEX IF NOT EXISTS idx_letras_codigo ON LETRAS(codigo);

CREATE TABLE IF NOT EXISTS TEMP_NOMBRES (
    id_temporal         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_sugerido     TEXT    NOT NULL DEFAULT '',
    fecha_registro      TEXT    NOT NULL,
    motor               TEXT    NOT NULL DEFAULT '',
    estado              TEXT    NOT NULL DEFAULT 'pendiente'
);

CREATE TABLE IF NOT EXISTS TEMP_LETRAS (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_temporal         INTEGER NOT NULL
                        REFERENCES TEMP_NOMBRES(id_temporal) ON DELETE CASCADE,
    numero_linea        INTEGER NOT NULL,
    linea               TEXT    NOT NULL,
    confianza           REAL    NOT NULL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS PROGRAMA (
    orden               INTEGER PRIMARY KEY,
    nombre_solicitado   TEXT    NOT NULL,
    codigo              INTEGER REFERENCES NOMBRES(codigo) ON DELETE SET NULL,
    estado              TEXT    NOT NULL DEFAULT 'pendiente'
);

CREATE TABLE IF NOT EXISTS SESIONES (
    id_sesion           INTEGER PRIMARY KEY AUTOINCREMENT,
    modo                TEXT    NOT NULL,
    inicio              TEXT    NOT NULL,
    fin                 TEXT
);

CREATE TABLE IF NOT EXISTS HISTORIAL (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    id_sesion           INTEGER REFERENCES SESIONES(id_sesion) ON DELETE CASCADE,
    codigo              INTEGER,
    nombre_cancion      TEXT    NOT NULL,
    modo                TEXT    NOT NULL,
    inicio              TEXT    NOT NULL,
    fin                 TEXT,
    lineas_mostradas    INTEGER NOT NULL DEFAULT 0,
    completada          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS METADATOS (
    clave               TEXT PRIMARY KEY,
    valor               TEXT NOT NULL
);
"""


class CancionDuplicada(Exception):
    """Ya existe una canción con ese nombre."""


@dataclass
class Cancion:
    codigo: int
    nombre: str
    lineas: list[str] = field(default_factory=list)
    artista: str = ""
    origen: str = ""
    veces_cantada: int = 0
    idioma: str = "es"


@dataclass
class CancionTemporal:
    id_temporal: int
    nombre_sugerido: str
    fecha: str
    motor: str
    lineas: list[str] = field(default_factory=list)


@dataclass
class EntradaPrograma:
    orden: int
    nombre_solicitado: str
    codigo: int | None
    estado: str


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class BaseDatos:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        self.existia = self.ruta.exists() and self.ruta.stat().st_size > 0
        if not self.existia:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.conexion = sqlite3.connect(str(self.ruta), check_same_thread=False)
        self.conexion.row_factory = sqlite3.Row
        # Se incrementa con cada cambio para que el buscador sepa cuándo
        # reconstruir su índice.
        self.revision = 0
        self._preparar()

    # ------------------------------------------------------------------ setup
    def _preparar(self) -> None:
        c = self.conexion
        c.execute("PRAGMA foreign_keys = ON")
        c.executescript(ESQUEMA)
        c.execute(
            "INSERT OR IGNORE INTO METADATOS(clave, valor) VALUES ('version_esquema', ?)",
            (str(VERSION_ESQUEMA),),
        )
        c.execute(
            "INSERT OR IGNORE INTO METADATOS(clave, valor) VALUES ('fecha_creacion', ?)",
            (_ahora(),),
        )
        # Cierra sesiones que quedaron abiertas si el programa se cerró mal.
        c.execute("UPDATE SESIONES SET fin = inicio WHERE fin IS NULL")
        c.commit()

    def integridad(self) -> str:
        return self.conexion.execute("PRAGMA quick_check").fetchone()[0]

    def cerrar(self) -> None:
        self.conexion.close()

    def _cambio(self) -> None:
        self.conexion.commit()
        self.revision += 1

    # -------------------------------------------------------------- canciones
    def contar_canciones(self) -> int:
        return self.conexion.execute("SELECT COUNT(*) FROM NOMBRES").fetchone()[0]

    def existe_nombre(self, nombre: str) -> int | None:
        fila = self.conexion.execute(
            "SELECT codigo FROM NOMBRES WHERE nombre_normalizado = ?",
            (normalizar(nombre),),
        ).fetchone()
        return fila[0] if fila else None

    def agregar_cancion(
        self,
        nombre: str,
        lineas: list[str],
        origen: str = "manual",
        artista: str = "",
        idioma: str | None = None,
    ) -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El nombre de la canción no puede estar vacío.")
        lineas = [l.strip() for l in lineas if l.strip()]
        if not lineas:
            raise ValueError("La canción debe tener al menos una línea.")
        if self.existe_nombre(nombre) is not None:
            raise CancionDuplicada(f"Ya existe una canción llamada «{nombre}».")
        cur = self.conexion.execute(
            "INSERT INTO NOMBRES(nombre_cancion, nombre_normalizado, artista, idioma, origen,"
            " fecha_registro) VALUES (?, ?, ?, ?, ?, ?)",
            (nombre, normalizar(nombre), artista.strip(), idioma or detectar_idioma(lineas), origen, _ahora()),
        )
        codigo = cur.lastrowid
        self._insertar_lineas(codigo, lineas)
        self._cambio()
        return codigo

    def _insertar_lineas(self, codigo: int, lineas: list[str]) -> None:
        self.conexion.executemany(
            "INSERT INTO LETRAS(codigo, numero_linea, linea, linea_normalizada) VALUES (?, ?, ?, ?)",
            [(codigo, i, l, normalizar(l)) for i, l in enumerate(lineas, start=1)],
        )

    def obtener_cancion(self, codigo: int) -> Cancion | None:
        fila = self.conexion.execute(
            "SELECT codigo, nombre_cancion, artista, origen, veces_cantada, idioma FROM NOMBRES"
            " WHERE codigo = ?",
            (codigo,),
        ).fetchone()
        if not fila:
            return None
        lineas = [
            r[0]
            for r in self.conexion.execute(
                "SELECT linea FROM LETRAS WHERE codigo = ? ORDER BY numero_linea", (codigo,)
            )
        ]
        return Cancion(fila[0], fila[1], lineas, fila[2], fila[3], fila[4], fila[5])

    def listar_canciones(self, desde: int = 0, cantidad: int = -1) -> list[tuple[int, str, int]]:
        """Devuelve (código, nombre, número de líneas) ordenado por código."""
        return [
            (r[0], r[1], r[2])
            for r in self.conexion.execute(
                "SELECT n.codigo, n.nombre_cancion, COUNT(l.id) FROM NOMBRES n"
                " LEFT JOIN LETRAS l ON l.codigo = n.codigo"
                " GROUP BY n.codigo ORDER BY n.codigo LIMIT ? OFFSET ?",
                (cantidad, desde),
            )
        ]

    def todas_las_letras(self) -> dict[int, Cancion]:
        canciones: dict[int, Cancion] = {}
        for r in self.conexion.execute("SELECT codigo, nombre_cancion, idioma FROM NOMBRES"):
            canciones[r[0]] = Cancion(r[0], r[1], idioma=r[2])
        for r in self.conexion.execute(
            "SELECT codigo, linea FROM LETRAS ORDER BY codigo, numero_linea"
        ):
            if r[0] in canciones:
                canciones[r[0]].lineas.append(r[1])
        return canciones

    def buscar_por_nombre(self, texto: str, limite: int = 10) -> list[tuple[int, str]]:
        """Busca canciones por nombre: exacto, luego que contenga el texto y
        finalmente por semejanza (para tolerar errores de dedo)."""
        consulta = normalizar(texto)
        if not consulta:
            return []
        filas = self.conexion.execute(
            "SELECT codigo, nombre_cancion, nombre_normalizado FROM NOMBRES"
        ).fetchall()
        exactos = [(f[0], f[1]) for f in filas if f[2] == consulta]
        if exactos:
            return exactos
        contiene = [(f[0], f[1]) for f in filas if consulta in f[2]]
        if contiene:
            return contiene[:limite]
        puntuados = []
        for f in filas:
            puntaje = semejanza(consulta, f[2])
            if puntaje >= 0.6:
                puntuados.append((puntaje, f[0], f[1]))
        puntuados.sort(reverse=True)
        return [(c, n) for _, c, n in puntuados[:limite]]

    def resolver(self, texto: str) -> list[tuple[int, str]]:
        """Interpreta ``texto`` como código numérico o como nombre."""
        texto = texto.strip()
        if texto.isdigit():
            cancion = self.obtener_cancion(int(texto))
            return [(cancion.codigo, cancion.nombre)] if cancion else []
        return self.buscar_por_nombre(texto)

    def actualizar_letra(self, codigo: int, lineas: list[str]) -> None:
        lineas = [l.strip() for l in lineas if l.strip()]
        if not lineas:
            raise ValueError("La canción debe tener al menos una línea.")
        self.conexion.execute("DELETE FROM LETRAS WHERE codigo = ?", (codigo,))
        self._insertar_lineas(codigo, lineas)
        self.conexion.execute(
            "UPDATE NOMBRES SET idioma = ? WHERE codigo = ?", (detectar_idioma(lineas), codigo)
        )
        self._cambio()

    def renombrar(self, codigo: int, nombre: str) -> None:
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El nombre de la canción no puede estar vacío.")
        otro = self.existe_nombre(nombre)
        if otro is not None and otro != codigo:
            raise CancionDuplicada(f"Ya existe una canción llamada «{nombre}».")
        self.conexion.execute(
            "UPDATE NOMBRES SET nombre_cancion = ?, nombre_normalizado = ? WHERE codigo = ?",
            (nombre, normalizar(nombre), codigo),
        )
        self._cambio()

    def borrar_cancion(self, codigo: int) -> bool:
        cur = self.conexion.execute("DELETE FROM NOMBRES WHERE codigo = ?", (codigo,))
        self._cambio()
        return cur.rowcount > 0

    # ----------------------------------------------------- tablas temporales
    def crear_temporal(self, nombre_sugerido: str = "", motor: str = "") -> int:
        cur = self.conexion.execute(
            "INSERT INTO TEMP_NOMBRES(nombre_sugerido, fecha_registro, motor) VALUES (?, ?, ?)",
            (nombre_sugerido, _ahora(), motor),
        )
        self.conexion.commit()
        return cur.lastrowid

    def agregar_linea_temporal(self, id_temporal: int, linea: str, confianza: float = 1.0) -> int:
        siguiente = self.conexion.execute(
            "SELECT COALESCE(MAX(numero_linea), 0) + 1 FROM TEMP_LETRAS WHERE id_temporal = ?",
            (id_temporal,),
        ).fetchone()[0]
        self.conexion.execute(
            "INSERT INTO TEMP_LETRAS(id_temporal, numero_linea, linea, confianza) VALUES (?, ?, ?, ?)",
            (id_temporal, siguiente, linea.strip(), confianza),
        )
        self.conexion.commit()
        return siguiente

    def sugerir_nombre_temporal(self, id_temporal: int, nombre: str) -> None:
        self.conexion.execute(
            "UPDATE TEMP_NOMBRES SET nombre_sugerido = ? WHERE id_temporal = ?",
            (nombre, id_temporal),
        )
        self.conexion.commit()

    def listar_temporales(self) -> list[CancionTemporal]:
        resultado = []
        for r in self.conexion.execute(
            "SELECT id_temporal FROM TEMP_NOMBRES WHERE estado = 'pendiente' ORDER BY id_temporal"
        ).fetchall():
            temporal = self.obtener_temporal(r[0])
            if temporal:
                resultado.append(temporal)
        return resultado

    def obtener_temporal(self, id_temporal: int) -> CancionTemporal | None:
        fila = self.conexion.execute(
            "SELECT id_temporal, nombre_sugerido, fecha_registro, motor FROM TEMP_NOMBRES"
            " WHERE id_temporal = ?",
            (id_temporal,),
        ).fetchone()
        if not fila:
            return None
        lineas = [
            r[0]
            for r in self.conexion.execute(
                "SELECT linea FROM TEMP_LETRAS WHERE id_temporal = ? ORDER BY numero_linea",
                (id_temporal,),
            )
        ]
        return CancionTemporal(fila[0], fila[1], fila[2], fila[3], lineas)

    def actualizar_temporal(self, id_temporal: int, lineas: list[str]) -> None:
        self.conexion.execute("DELETE FROM TEMP_LETRAS WHERE id_temporal = ?", (id_temporal,))
        self.conexion.executemany(
            "INSERT INTO TEMP_LETRAS(id_temporal, numero_linea, linea) VALUES (?, ?, ?)",
            [(id_temporal, i, l.strip()) for i, l in enumerate(lineas, 1) if l.strip()],
        )
        self.conexion.commit()

    def promover_temporal(self, id_temporal: int, nombre: str, artista: str = "") -> int:
        """Pasa una canción de las tablas temporales a las permanentes."""
        temporal = self.obtener_temporal(id_temporal)
        if temporal is None:
            raise ValueError("No existe esa canción temporal.")
        codigo = self.agregar_cancion(nombre, temporal.lineas, origen="automatico", artista=artista)
        self.borrar_temporal(id_temporal)
        return codigo

    def borrar_temporal(self, id_temporal: int) -> None:
        self.conexion.execute("DELETE FROM TEMP_NOMBRES WHERE id_temporal = ?", (id_temporal,))
        self.conexion.commit()

    # --------------------------------------------------------------- programa
    def guardar_programa(self, entradas: list[tuple[str, int | None]]) -> None:
        self.conexion.execute("DELETE FROM PROGRAMA")
        self.conexion.executemany(
            "INSERT INTO PROGRAMA(orden, nombre_solicitado, codigo) VALUES (?, ?, ?)",
            [(i, n, c) for i, (n, c) in enumerate(entradas, start=1)],
        )
        self.conexion.commit()

    def obtener_programa(self) -> list[EntradaPrograma]:
        return [
            EntradaPrograma(r[0], r[1], r[2], r[3])
            for r in self.conexion.execute(
                "SELECT orden, nombre_solicitado, codigo, estado FROM PROGRAMA ORDER BY orden"
            )
        ]

    def marcar_programa(self, orden: int, estado: str) -> None:
        self.conexion.execute("UPDATE PROGRAMA SET estado = ? WHERE orden = ?", (estado, orden))
        self.conexion.commit()

    def reiniciar_programa(self) -> None:
        self.conexion.execute("UPDATE PROGRAMA SET estado = 'pendiente'")
        self.conexion.commit()

    def vincular_programa(self) -> int:
        """Vuelve a enlazar las entradas sin código (por si la canción se
        agregó después de cargar el programa). Devuelve cuántas enlazó."""
        enlazadas = 0
        for entrada in self.obtener_programa():
            if entrada.codigo is None:
                codigo = self.existe_nombre(entrada.nombre_solicitado)
                if codigo is not None:
                    self.conexion.execute(
                        "UPDATE PROGRAMA SET codigo = ? WHERE orden = ?", (codigo, entrada.orden)
                    )
                    enlazadas += 1
        self.conexion.commit()
        return enlazadas

    # -------------------------------------------------------------- historial
    def iniciar_sesion(self, modo: str) -> int:
        cur = self.conexion.execute(
            "INSERT INTO SESIONES(modo, inicio) VALUES (?, ?)", (modo, _ahora())
        )
        self.conexion.commit()
        return cur.lastrowid

    def terminar_sesion(self, id_sesion: int) -> None:
        self.conexion.execute("UPDATE SESIONES SET fin = ? WHERE id_sesion = ?", (_ahora(), id_sesion))
        self.conexion.commit()

    def registrar_interpretacion(
        self,
        id_sesion: int | None,
        codigo: int | None,
        nombre: str,
        modo: str,
        inicio: str,
        lineas_mostradas: int,
        completada: bool,
    ) -> None:
        self.conexion.execute(
            "INSERT INTO HISTORIAL(id_sesion, codigo, nombre_cancion, modo, inicio, fin,"
            " lineas_mostradas, completada) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (id_sesion, codigo, nombre, modo, inicio, _ahora(), lineas_mostradas, int(completada)),
        )
        if codigo is not None:
            self.conexion.execute(
                "UPDATE NOMBRES SET veces_cantada = veces_cantada + 1 WHERE codigo = ?", (codigo,)
            )
        self.conexion.commit()

    def historial(self, limite: int = 50) -> list[sqlite3.Row]:
        return self.conexion.execute(
            "SELECT h.id_sesion, h.nombre_cancion, h.modo, h.inicio, h.lineas_mostradas, h.completada"
            " FROM HISTORIAL h ORDER BY h.id DESC LIMIT ?",
            (limite,),
        ).fetchall()

    def mas_cantadas(self, limite: int = 10) -> list[tuple[int, str, int]]:
        return [
            (r[0], r[1], r[2])
            for r in self.conexion.execute(
                "SELECT codigo, nombre_cancion, veces_cantada FROM NOMBRES"
                " WHERE veces_cantada > 0 ORDER BY veces_cantada DESC, codigo LIMIT ?",
                (limite,),
            )
        ]


def ahora() -> str:
    return _ahora()
