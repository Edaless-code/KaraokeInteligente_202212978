"""Nombres a partir de archivos de audio (sin NumPy: sirve también en Android)."""

from __future__ import annotations

import re
from pathlib import Path

_RUIDO_NOMBRE = re.compile(
    r"[\(\[]?\b(official|audio|video|lyrics?|letra|hq|hd|mp3|final|mix|master)\b[\)\]]?", re.IGNORECASE)


def nombre_desde_archivo(ruta: Path) -> str:
    """"Ghost_of_you (Official Audio).mp3" -> "Ghost of you"."""
    nombre = ruta.stem.replace("_", " ").replace(".", " ")
    nombre = _RUIDO_NOMBRE.sub(" ", nombre)
    nombre = re.sub(r"[\(\[]\s*[\)\]]", " ", nombre)
    nombre = re.sub(r"\s*-\s*$", "", " ".join(nombre.split()))
    return nombre.strip(" -") or ruta.stem


def nombre_seguro(texto: str) -> str:
    """Nombre válido para un archivo en Windows, Linux y Android."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto).strip(" .")
    return limpio[:80] or "pista"
