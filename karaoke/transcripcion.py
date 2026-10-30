"""Resultado de un motor de voz. Vive aparte (sin NumPy) para que el núcleo
del karaoke también funcione en Android, donde la transcripción la hace el
reconocedor de voz del sistema."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Transcripcion:
    tipo: str  # "parcial" o "final"
    texto: str
    canal: str = "libre"  # "libre" (Vosk), "restringido" (Vosk con la letra) o "whisper"
    idioma: str = "es"
    confianza: float = 1.0
    segundo: float = 0.0

    @property
    def palabras(self) -> list[str]:
        return [p for p in self.texto.split() if p != "[unk]"]

    @property
    def desconocidas(self) -> int:
        return self.texto.split().count("[unk]")
