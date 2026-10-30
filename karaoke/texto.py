"""Utilidades de texto: normalización, palabras, división de líneas y lectura."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

_NO_ALFANUMERICO = re.compile(r"[^a-z0-9ñ ]+")
_ESPACIOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes (conserva la ñ), sin signos y con espacios simples.

    >>> normalizar("¡Ay, ay, ay, ay! Canta y no llores")
    'ay ay ay ay canta y no llores'
    """
    texto = texto.lower().replace("ñ", "\x00")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("\x00", "ñ").replace("'", "").replace("’", "")
    texto = _NO_ALFANUMERICO.sub(" ", texto)
    return _ESPACIOS.sub(" ", texto).strip()


def palabras(texto: str) -> list[str]:
    normal = normalizar(texto)
    return normal.split() if normal else []


@lru_cache(maxsize=200_000)
def semejanza(a: str, b: str) -> float:
    """Semejanza entre dos palabras normalizadas (0..1)."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    # Diferencias grandes de longitud no pueden ser la misma palabra.
    if abs(len(a) - len(b)) > max(len(a), len(b)) // 2 + 1:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dividir_linea(linea: str, maximo: int) -> list[str]:
    """Divide una línea larga en partes de a lo sumo ``maximo`` caracteres,
    cortando en los espacios cuando es posible."""
    linea = linea.strip()
    if len(linea) <= maximo:
        return [linea] if linea else []
    partes: list[str] = []
    actual = ""
    for palabra in linea.split():
        while len(palabra) > maximo:
            if actual:
                partes.append(actual)
                actual = ""
            partes.append(palabra[:maximo])
            palabra = palabra[maximo:]
        candidato = f"{actual} {palabra}" if actual else palabra
        if len(candidato) <= maximo:
            actual = candidato
        else:
            partes.append(actual)
            actual = palabra
    if actual:
        partes.append(actual)
    return partes


def ajustar_linea(linea: str, maximo: int, accion: str) -> list[str]:
    """Aplica la acción configurada a una línea que excede el máximo."""
    linea = linea.strip()
    if not linea:
        return []
    if len(linea) <= maximo or accion == "conservar":
        return [linea]
    if accion == "truncar":
        return [linea[:maximo].rstrip()]
    return dividir_linea(linea, maximo)


MAX_BYTES_TEXTO = 5 * 1024 * 1024  # 5 MB: miles de canciones; protege la memoria


def leer_texto(ruta: str | Path, maximo: int = MAX_BYTES_TEXTO) -> str:
    """Lee un archivo de texto probando UTF-8 (con o sin BOM) y luego las
    codificaciones típicas de Windows (Bloc de notas antiguo). Rechaza los
    archivos de más de ``maximo`` bytes."""
    ruta = Path(ruta)
    if ruta.stat().st_size > maximo:
        raise ValueError(f"El archivo {ruta.name} pesa más de {maximo // (1024 * 1024)} MB; "
                         "no parece un archivo de letras.")
    datos = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = datos.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = datos.decode("utf-8", errors="replace")
    # Saltos de línea de Windows (\r\n) y de Mac antiguo (\r) → \n.
    return texto.replace("\r\n", "\n").replace("\r", "\n")


# Palabras muy comunes de cada idioma para detectar en qué idioma está la letra.
_FRECUENTES = {
    "es": set("el la los las de que y en un una por con no se mi tu me te lo le es al del yo pero mas".split()),
    "en": set("the and you i to a of in my is it that me your be for on with all love dont im".split()),
}

# Renglones que solo son etiquetas de una sección de la canción y no se cantan.
_ETIQUETA = re.compile(
    r"^\s*(?:\[.*\]|\(.*\)|(?:coro|chorus|estribillo|verso|verse|puente|bridge|intro|outro|pre-?coro|pre-?chorus)"
    r"\s*\d*\s*(?:\(.*\))?\s*:?)\s*$",
    re.IGNORECASE,
)


def es_etiqueta(renglon: str) -> bool:
    """``True`` si el renglón es una etiqueta como "Coro", "[Verso 2]" o
    "Chorus (Repeat 2x)"."""
    return bool(_ETIQUETA.match(renglon))


def detectar_idioma(lineas: list[str]) -> str:
    """Devuelve "es" o "en" según las palabras frecuentes de la letra."""
    conteo = {idioma: 0 for idioma in _FRECUENTES}
    for linea in lineas:
        for palabra in palabras(linea):
            for idioma, frecuentes in _FRECUENTES.items():
                if palabra in frecuentes:
                    conteo[idioma] += 1
    return max(conteo, key=lambda i: (conteo[i], i == "es"))


_NO_LETRA = re.compile(r"[^\w' ]+")

# Contracciones del inglés que en las letras se suelen escribir sin apóstrofo;
# el modelo de voz las conoce con apóstrofo.
_CONTRACCIONES = {
    "dont": "don't", "cant": "can't", "wont": "won't", "im": "i'm", "ive": "i've",
    "youre": "you're", "isnt": "isn't", "doesnt": "doesn't", "didnt": "didn't",
    "thats": "that's", "whats": "what's", "lets": "let's", "aint": "ain't",
    "youve": "you've", "ill": "i'll", "id": "i'd", "theyre": "they're", "wasnt": "wasn't",
}


def vocabulario(lineas: list[str], idioma: str = "es") -> set[str]:
    """Palabras de la letra tal como las conoce el modelo de voz: en
    minúsculas, sin signos y CONSERVANDO las tildes (Vosk reconoce "canción",
    no "cancion")."""
    resultado: set[str] = set()
    for linea in lineas:
        for palabra in _NO_LETRA.sub(" ", linea.lower().replace("’", "'")).split():
            palabra = palabra.strip("'")
            if not palabra or palabra.isdigit():
                continue
            resultado.add(palabra)
            if idioma == "en" and palabra in _CONTRACCIONES:
                resultado.add(_CONTRACCIONES[palabra])
    return resultado


# Palabras ofensivas que se ocultan en lo que transcribe la IA (que a veces
# entiende mal la letra cantada). Nunca afecta a la letra guardada por el usuario.
_GROSERIAS = re.compile(
    r"\b(bitch(es)?|fuck(ing|er|ed)?|shit|asshole|bastard|dick|cunt|whore|nigga|"
    r"puta|puto|mierda|pendej[oa]s?|cabr[oó]n|verga|chinga\w*|culer[oa]|joto|marica)\b",
    re.IGNORECASE,
)


def censurar(texto: str) -> str:
    """Oculta las groserías dejando la primera letra: "bitch" -> "b****"."""
    return _GROSERIAS.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), texto)
