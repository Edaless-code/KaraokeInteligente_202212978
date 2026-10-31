"""Portadas (imagen) de las canciones. Sin NumPy: sirve también en Android."""

from __future__ import annotations

import shutil
from pathlib import Path

FORMATOS_IMAGEN = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def guardar_portada(carpeta: Path, codigo: int, origen: Path) -> str:
    """Copia la imagen a ``portadas/`` y devuelve su ruta relativa."""
    if origen.suffix.lower() not in FORMATOS_IMAGEN:
        raise ValueError(f"Formato de imagen no admitido ({origen.suffix}); use JPG, PNG o WEBP.")
    if origen.stat().st_size > 15 * 1024 * 1024:
        raise ValueError("La imagen pesa más de 15 MB.")
    destino_dir = carpeta / "portadas"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{codigo:03d}{origen.suffix.lower()}"
    if origen.resolve() != destino.resolve():
        shutil.copy2(origen, destino)
    return destino.relative_to(carpeta).as_posix()
