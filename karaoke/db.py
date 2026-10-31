"""Acceso a la base de datos SQLite "CANCIONES".

Tablas (ver el manual técnico para el detalle de cada campo):

* ``NOMBRES``      código y nombre de cada canción (tabla de la especificación).
* ``LETRAS``       una fila por línea de la letra, enlazada por ``codigo``.
* ``TEMP_NOMBRES`` y ``TEMP_LETRAS``  canciones aprendidas por el modo
  automático que todavía no se han revisado (tablas temporales).
* ``PROGRAMA``     lista preplaneada de canciones del cantante.
* ``SESIONES`` e ``HISTORIAL``  registro de lo que se cantó en cada sesión.
* ``METADATOS``    versión del esquema.

Borrar una canción NO la elimina de inmediato: se mueve a la **papelera**
(``NOMBRES.eliminada_en``). Desde ahí se puede restaurar o eliminar
definitivamente; las que llevan más de ``[letras] dias_papelera`` días se
eliminan solas al abrir el programa.

Seguridad: todas las consultas usan parámetros (nunca se arma SQL con el texto
del usuario), las escrituras de varias tablas van en una transacción (todo o
nada), los textos se limpian de caracteres de control y se limita su longitud.
Antes de migrar el esquema a una versión nueva se guarda un respaldo.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .texto import detectar_idioma, normalizar, semejanza

VERSION_ESQUEMA = 4

# Límites de seguridad (protegen la memoria y la base de datos de entradas
# anómalas). La longitud "normal" de una línea se configura en karaoke.ini.
MAX_NOMBRE = 150
MAX_LINEA = 1000
MAX_LINEAS = 2000

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def limpiar_texto(texto: str, maximo: int) -> str:
    """Quita caracteres de control y espacios de los extremos y recorta."""
    return _CONTROL.sub("", str(texto)).strip()[:maximo]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS NOMBRES (
    codigo              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_cancion      TEXT    NOT NULL,
    nombre_normalizado  TEXT    NOT NULL UNIQUE,
    artista             TEXT    NOT NULL DEFAULT '',
    idioma              TEXT    NOT NULL DEFAULT 'es',
    origen              TEXT    NOT NULL DEFAULT 'manual',
    fecha_registro      TEXT    NOT NULL,
    veces_cantada       INTEGER NOT NULL DEFAULT 0,
    eliminada_en        TEXT
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

-- Pista de audio de cada canción (versión 3): se agrega desde un MP3/WAV y
-- se ofrece en el modo automático. La ruta es relativa a la carpeta del programa.
CREATE TABLE IF NOT EXISTS PISTAS (
    codigo              INTEGER PRIMARY KEY REFERENCES NOMBRES(codigo) ON DELETE CASCADE,
    archivo             TEXT    NOT NULL,
    fecha_registro      TEXT    NOT NULL
);

-- Segundo en que empieza cada línea en la pista (versión 4): la letra se
-- muestra a tiempo al reproducir la canción. Se borra si cambia la letra.
CREATE TABLE IF NOT EXISTS TIEMPOS (
    codigo              INTEGER NOT NULL REFERENCES NOMBRES(codigo) ON DELETE CASCADE,
    numero_linea        INTEGER NOT NULL,
    inicio              REAL    NOT NULL,
    PRIMARY KEY (codigo, numero_linea)
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


class CancionEnPapelera(CancionDuplicada):
    """Hay una canción con ese nombre en la papelera."""

    def __init__(self, nombre: str, codigo: int):
        super().__init__(f"«{nombre}» está en la papelera (código {codigo}). "
                         "Restáurela o elimínela definitivamente.")
        self.codigo = codigo


@dataclass
class Cancion:
    codigo: int
    nombre: str
    lineas: list[str] = field(default_factory=list)
    artista: str = ""
    origen: str = ""
    veces_cantada: int = 0
    idioma: str = "es"
    favorita: bool = False
    genero: str = ""
    portada: str | None = None


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
        version = self._version_guardada()
        if self.existia and version < VERSION_ESQUEMA:
            self._respaldar(f"antes-de-v{VERSION_ESQUEMA}")
        c.executescript(ESQUEMA)
        self._migrar(version)
        c.execute("CREATE INDEX IF NOT EXISTS idx_nombres_papelera ON NOMBRES(eliminada_en)")
        c.execute(
            "INSERT OR REPLACE INTO METADATOS(clave, valor) VALUES ('version_esquema', ?)",
            (str(VERSION_ESQUEMA),),
        )
        c.execute(
            "INSERT OR IGNORE INTO METADATOS(clave, valor) VALUES ('fecha_creacion', ?)",
            (_ahora(),),
        )
        # Cierra sesiones que quedaron abiertas si el programa se cerró mal.
        c.execute("UPDATE SESIONES SET fin = inicio WHERE fin IS NULL")
        c.commit()

    def _version_guardada(self) -> int:
        try:
            fila = self.conexion.execute(
                "SELECT valor FROM METADATOS WHERE clave = 'version_esquema'").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(fila[0]) if fila else 0

    def _columnas(self, tabla: str) -> set[str]:
        return {f[1] for f in self.conexion.execute(f"PRAGMA table_info({tabla})")}

    def _migrar(self, desde: int) -> None:
        """Migraciones del esquema. Cada versión nueva agrega aquí sus pasos;
        las bases de versiones anteriores se actualizan solas al abrirse."""
        columnas = self._columnas("NOMBRES")
        if "eliminada_en" not in columnas:  # versión 2: papelera
            self.conexion.execute("ALTER TABLE NOMBRES ADD COLUMN eliminada_en TEXT")
        # versión 4: favoritas, género o carpeta y portada (imagen)
        if "favorita" not in columnas:
            self.conexion.execute("ALTER TABLE NOMBRES ADD COLUMN favorita INTEGER NOT NULL DEFAULT 0")
        if "genero" not in columnas:
            self.conexion.execute("ALTER TABLE NOMBRES ADD COLUMN genero TEXT NOT NULL DEFAULT ''")
        if "portada" not in columnas:
            self.conexion.execute("ALTER TABLE NOMBRES ADD COLUMN portada TEXT")

    def _respaldar(self, motivo: str) -> Path | None:
        """Copia la base de datos antes de una operación delicada."""
        if not self.ruta.exists() or self.ruta.name == ":memory:":
            return None
        destino = self.ruta.with_name(f"{self.ruta.stem}.respaldo-{motivo}{self.ruta.suffix}")
        self.conexion.commit()
        shutil.copy2(self.ruta, destino)
        return destino

    @contextmanager
    def _transaccion(self):
        """Todo o nada: si algo falla a la mitad no queda la canción a medias."""
        try:
            yield self.conexion
            self.conexion.commit()
        except Exception:
            self.conexion.rollback()
            raise
        self.revision += 1

    def integridad(self) -> str:
        return self.conexion.execute("PRAGMA quick_check").fetchone()[0]

    def cerrar(self) -> None:
        self.conexion.close()

    # -------------------------------------------------------------- canciones
    def contar_canciones(self) -> int:
        return self.conexion.execute(
            "SELECT COUNT(*) FROM NOMBRES WHERE eliminada_en IS NULL").fetchone()[0]

    def existe_nombre(self, nombre: str) -> int | None:
        """Código de la canción ACTIVA con ese nombre (sin contar la papelera)."""
        fila = self.conexion.execute(
            "SELECT codigo FROM NOMBRES WHERE nombre_normalizado = ? AND eliminada_en IS NULL",
            (normalizar(nombre),),
        ).fetchone()
        return fila[0] if fila else None

    def _verificar_nombre_libre(self, nombre: str, propio: int | None = None) -> None:
        fila = self.conexion.execute(
            "SELECT codigo, eliminada_en FROM NOMBRES WHERE nombre_normalizado = ?",
            (normalizar(nombre),),
        ).fetchone()
        if fila and fila[0] != propio:
            if fila[1] is not None:
                raise CancionEnPapelera(nombre, fila[0])
            raise CancionDuplicada(f"Ya existe una canción llamada «{nombre}».")

    @staticmethod
    def _validar(nombre: str | None, lineas: list[str] | None) -> tuple[str, list[str]]:
        if nombre is not None:
            nombre = limpiar_texto(nombre, MAX_NOMBRE)
            if not normalizar(nombre):
                raise ValueError("El nombre de la canción no puede estar vacío.")
        if lineas is not None:
            lineas = [l for l in (limpiar_texto(x, MAX_LINEA) for x in lineas) if l]
            if not lineas:
                raise ValueError("La canción debe tener al menos una línea.")
            if len(lineas) > MAX_LINEAS:
                raise ValueError(f"La canción no puede tener más de {MAX_LINEAS} líneas.")
        return nombre, lineas

    def agregar_cancion(
        self,
        nombre: str,
        lineas: list[str],
        origen: str = "manual",
        artista: str = "",
        idioma: str | None = None,
    ) -> int:
        nombre, lineas = self._validar(nombre, lineas)
        self._verificar_nombre_libre(nombre)
        with self._transaccion() as c:
            cur = c.execute(
                "INSERT INTO NOMBRES(nombre_cancion, nombre_normalizado, artista, idioma, origen,"
                " fecha_registro) VALUES (?, ?, ?, ?, ?, ?)",
                (nombre, normalizar(nombre), limpiar_texto(artista, MAX_NOMBRE),
                 idioma or detectar_idioma(lineas), origen, _ahora()),
            )
            codigo = cur.lastrowid
            self._insertar_lineas(codigo, lineas)
        return codigo

    def _insertar_lineas(self, codigo: int, lineas: list[str]) -> None:
        self.conexion.executemany(
            "INSERT INTO LETRAS(codigo, numero_linea, linea, linea_normalizada) VALUES (?, ?, ?, ?)",
            [(codigo, i, l, normalizar(l)) for i, l in enumerate(lineas, start=1)],
        )

    def obtener_cancion(self, codigo: int, incluir_papelera: bool = False) -> Cancion | None:
        fila = self.conexion.execute(
            "SELECT codigo, nombre_cancion, artista, origen, veces_cantada, idioma, favorita, genero, portada"
            " FROM NOMBRES WHERE codigo = ? AND (? OR eliminada_en IS NULL)",
            (codigo, incluir_papelera),
        ).fetchone()
        if not fila:
            return None
        lineas = [
            r[0]
            for r in self.conexion.execute(
                "SELECT linea FROM LETRAS WHERE codigo = ? ORDER BY numero_linea", (codigo,)
            )
        ]
        return Cancion(fila[0], fila[1], lineas, fila[2], fila[3], fila[4], fila[5], bool(fila[6]), fila[7], fila[8])

    def listar_canciones(self, desde: int = 0, cantidad: int = -1) -> list[tuple[int, str, int]]:
        """Devuelve (código, nombre, número de líneas) ordenado por código."""
        return [
            (r[0], r[1], r[2])
            for r in self.conexion.execute(
                "SELECT n.codigo, n.nombre_cancion, COUNT(l.id) FROM NOMBRES n"
                " LEFT JOIN LETRAS l ON l.codigo = n.codigo WHERE n.eliminada_en IS NULL"
                " GROUP BY n.codigo ORDER BY n.codigo LIMIT ? OFFSET ?",
                (cantidad, desde),
            )
        ]

    def todas_las_letras(self) -> dict[int, Cancion]:
        canciones: dict[int, Cancion] = {}
        for r in self.conexion.execute(
            "SELECT codigo, nombre_cancion, idioma FROM NOMBRES WHERE eliminada_en IS NULL"
        ):
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
            "SELECT codigo, nombre_cancion, nombre_normalizado FROM NOMBRES WHERE eliminada_en IS NULL"
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
        _, lineas = self._validar(None, lineas)
        with self._transaccion() as c:
            c.execute("DELETE FROM LETRAS WHERE codigo = ?", (codigo,))
            c.execute("DELETE FROM TIEMPOS WHERE codigo = ?", (codigo,))  # ya no corresponden
            self._insertar_lineas(codigo, lineas)
            c.execute("UPDATE NOMBRES SET idioma = ? WHERE codigo = ?", (detectar_idioma(lineas), codigo))

    def renombrar(self, codigo: int, nombre: str) -> None:
        nombre, _ = self._validar(nombre, None)
        self._verificar_nombre_libre(nombre, propio=codigo)
        with self._transaccion() as c:
            c.execute(
                "UPDATE NOMBRES SET nombre_cancion = ?, nombre_normalizado = ? WHERE codigo = ?",
                (nombre, normalizar(nombre), codigo),
            )

    # --------------------------------------------------------------- papelera
    def borrar_cancion(self, codigo: int) -> bool:
        """Mueve la canción a la papelera (se puede restaurar)."""
        with self._transaccion() as c:
            cur = c.execute(
                "UPDATE NOMBRES SET eliminada_en = ? WHERE codigo = ? AND eliminada_en IS NULL",
                (_ahora(), codigo),
            )
        return cur.rowcount > 0

    def en_papelera(self, codigo: int) -> bool:
        fila = self.conexion.execute(
            "SELECT eliminada_en FROM NOMBRES WHERE codigo = ?", (codigo,)).fetchone()
        return bool(fila and fila[0])

    def listar_papelera(self) -> list[tuple[int, str, int, str]]:
        """(código, nombre, número de líneas, fecha en que se borró)."""
        return [
            (r[0], r[1], r[2], r[3])
            for r in self.conexion.execute(
                "SELECT n.codigo, n.nombre_cancion, COUNT(l.id), n.eliminada_en FROM NOMBRES n"
                " LEFT JOIN LETRAS l ON l.codigo = n.codigo WHERE n.eliminada_en IS NOT NULL"
                " GROUP BY n.codigo ORDER BY n.eliminada_en DESC, n.codigo DESC"
            )
        ]

    def restaurar_cancion(self, codigo: int) -> bool:
        with self._transaccion() as c:
            cur = c.execute(
                "UPDATE NOMBRES SET eliminada_en = NULL WHERE codigo = ? AND eliminada_en IS NOT NULL",
                (codigo,),
            )
        return cur.rowcount > 0

    def eliminar_definitivamente(self, codigo: int) -> bool:
        """Borra para siempre una canción que está en la papelera (y su letra)."""
        with self._transaccion() as c:
            cur = c.execute(
                "DELETE FROM NOMBRES WHERE codigo = ? AND eliminada_en IS NOT NULL", (codigo,))
        return cur.rowcount > 0

    def vaciar_papelera(self, mas_de_dias: float | None = None) -> int:
        """Elimina definitivamente lo que está en la papelera (o solo lo que
        lleva más de ``mas_de_dias`` días)."""
        if mas_de_dias is None:
            limite = "9999-12-31 23:59:59"
        else:
            limite = (datetime.now() - timedelta(days=mas_de_dias)).strftime("%Y-%m-%d %H:%M:%S")
        with self._transaccion() as c:
            cur = c.execute(
                "DELETE FROM NOMBRES WHERE eliminada_en IS NOT NULL AND eliminada_en <= ?", (limite,))
        return cur.rowcount

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
            (id_temporal, siguiente, limpiar_texto(linea, MAX_LINEA), confianza),
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
        lineas = [l for l in (limpiar_texto(x, MAX_LINEA) for x in lineas) if l]
        with self._transaccion() as c:
            c.execute("DELETE FROM TEMP_LETRAS WHERE id_temporal = ?", (id_temporal,))
            c.executemany(
                "INSERT INTO TEMP_LETRAS(id_temporal, numero_linea, linea) VALUES (?, ?, ?)",
                [(id_temporal, i, l) for i, l in enumerate(lineas, 1)],
            )

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
    # ------------------------------------------------- tiempos de la letra
    def guardar_tiempos(self, codigo: int, tiempos: list[float]) -> None:
        with self._transaccion() as c:
            c.execute("DELETE FROM TIEMPOS WHERE codigo = ?", (codigo,))
            c.executemany("INSERT INTO TIEMPOS(codigo, numero_linea, inicio) VALUES (?, ?, ?)",
                          [(codigo, n, float(t)) for n, t in enumerate(tiempos, 1)])

    def obtener_tiempos(self, codigo: int) -> list[float] | None:
        """Tiempos de todas las líneas, o ``None`` si no están (o no cuadran)."""
        filas = self.conexion.execute(
            "SELECT inicio FROM TIEMPOS WHERE codigo = ? ORDER BY numero_linea", (codigo,)).fetchall()
        lineas = self.conexion.execute("SELECT COUNT(*) FROM LETRAS WHERE codigo = ?", (codigo,)).fetchone()[0]
        if not filas or len(filas) != lineas:
            return None
        return [f[0] for f in filas]

    # ------------------------------------------ favoritas, géneros y portadas
    def marcar_favorita(self, codigo: int, favorita: bool = True) -> None:
        with self._transaccion() as c:
            c.execute("UPDATE NOMBRES SET favorita = ? WHERE codigo = ?", (int(favorita), codigo))

    def establecer_genero(self, codigo: int, genero: str) -> None:
        with self._transaccion() as c:
            c.execute("UPDATE NOMBRES SET genero = ? WHERE codigo = ?", (limpiar_texto(genero, 60), codigo))

    def establecer_portada(self, codigo: int, portada: str | None) -> None:
        with self._transaccion() as c:
            c.execute("UPDATE NOMBRES SET portada = ? WHERE codigo = ?",
                      (limpiar_texto(portada, 500) if portada else None, codigo))

    def detalles_listado(self) -> dict[int, tuple[bool, str]]:
        """código -> (favorita, género) para mostrarlos en las listas."""
        return {f[0]: (bool(f[1]), f[2]) for f in self.conexion.execute(
            "SELECT codigo, favorita, genero FROM NOMBRES WHERE eliminada_en IS NULL")}

    def generos(self) -> list[tuple[str, int]]:
        """(género o carpeta, número de canciones), sin las que no tienen."""
        return [tuple(f) for f in self.conexion.execute(
            "SELECT genero, COUNT(*) FROM NOMBRES WHERE eliminada_en IS NULL AND genero != ''"
            " GROUP BY genero ORDER BY genero COLLATE NOCASE")]

    def listar_filtradas(self, genero: str | None = None, favoritas: bool = False) -> list[tuple[int, str, int]]:
        """Como ``listar_canciones`` pero solo un género o solo las favoritas."""
        condiciones, parametros = ["n.eliminada_en IS NULL"], []
        if genero is not None:
            condiciones.append("n.genero = ?")
            parametros.append(genero)
        if favoritas:
            condiciones.append("n.favorita = 1")
        return [(r[0], r[1], r[2]) for r in self.conexion.execute(
            "SELECT n.codigo, n.nombre_cancion, COUNT(l.id) FROM NOMBRES n"
            " LEFT JOIN LETRAS l ON l.codigo = n.codigo WHERE " + " AND ".join(condiciones) +
            " GROUP BY n.codigo ORDER BY n.codigo", parametros)]

    # ------------------------------------------------------------ pistas
    def guardar_pista(self, codigo: int, archivo: str) -> None:
        with self._transaccion() as c:
            c.execute("INSERT OR REPLACE INTO PISTAS(codigo, archivo, fecha_registro) VALUES (?, ?, ?)",
                      (codigo, limpiar_texto(archivo, 500), _ahora()))

    def obtener_pista(self, codigo: int) -> str | None:
        fila = self.conexion.execute("SELECT archivo FROM PISTAS WHERE codigo = ?", (codigo,)).fetchone()
        return fila[0] if fila else None

    def listar_pistas(self) -> list[tuple[int, str, str]]:
        """(código, nombre, archivo) de las canciones con pista (sin la papelera)."""
        return [tuple(f) for f in self.conexion.execute(
            "SELECT n.codigo, n.nombre_cancion, p.archivo FROM PISTAS p "
            "JOIN NOMBRES n ON n.codigo = p.codigo WHERE n.eliminada_en IS NULL ORDER BY n.codigo")]

    def guardar_programa(self, entradas: list[tuple[str, int | None]]) -> None:
        with self._transaccion() as c:
            c.execute("DELETE FROM PROGRAMA")
            c.executemany(
                "INSERT INTO PROGRAMA(orden, nombre_solicitado, codigo) VALUES (?, ?, ?)",
                [(i, limpiar_texto(n, MAX_NOMBRE), cod) for i, (n, cod) in enumerate(entradas, start=1)],
            )

    def obtener_programa(self) -> list[EntradaPrograma]:
        """Las canciones que están en la papelera aparecen sin código."""
        return [
            EntradaPrograma(r[0], r[1], r[2], r[3])
            for r in self.conexion.execute(
                "SELECT p.orden, p.nombre_solicitado,"
                " CASE WHEN n.eliminada_en IS NULL THEN p.codigo END, p.estado"
                " FROM PROGRAMA p LEFT JOIN NOMBRES n ON n.codigo = p.codigo ORDER BY p.orden"
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
        if codigo is not None and completada:
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
                " WHERE veces_cantada > 0 AND eliminada_en IS NULL"
                " ORDER BY veces_cantada DESC, codigo LIMIT ?",
                (limite,),
            )
        ]


def ahora() -> str:
    return _ahora()
