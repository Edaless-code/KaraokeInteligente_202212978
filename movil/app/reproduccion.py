"""Reproducción de una pista con su letra a tiempo, en cualquier dispositivo.

* En la computadora se usa el reproductor del núcleo (NumPy + sounddevice):
  reloj preciso y control de la voz del artista (100, 75, 50 o 25 %).
* En el teléfono (o si falta algo) se usa el reproductor de Kivy: la letra va
  a tiempo igual, pero sin control de voz.
"""

from __future__ import annotations

from pathlib import Path

from kivy.logger import Logger

NIVELES_VOZ = (1.0, 0.75, 0.5, 0.25)


class Reproduccion:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self._nucleo = None
        self._sonido = None
        self._pausa_en = 0.0
        self.pausado = False
        self._iniciada = False
        try:
            from karaoke.audio.reproductor import Reproductor

            self._nucleo = Reproductor(self.ruta)
        except Exception as ex:  # Android o sin NumPy/sounddevice
            Logger.info(f"Karaoke: reproductor sencillo ({ex})")
            from kivy.core.audio import SoundLoader

            self._sonido = SoundLoader.load(str(self.ruta))
            if self._sonido is None:
                raise RuntimeError(f"No se puede reproducir {self.ruta.name} en este dispositivo")

    # --------------------------------------------------------------- datos
    @property
    def voz_disponible(self) -> bool:
        return self._nucleo is not None

    @property
    def voz(self) -> float:
        return self._nucleo.voz if self._nucleo is not None else 1.0

    @property
    def duracion(self) -> float:
        if self._nucleo is not None:
            return self._nucleo.duracion
        return float(self._sonido.length or 0.0)

    @property
    def segundo(self) -> float:
        if self._nucleo is not None:
            return self._nucleo.segundo
        if self.pausado:
            return self._pausa_en
        return float(self._sonido.get_pos() or 0.0)

    @property
    def terminada(self) -> bool:
        if self._nucleo is not None:
            return self._nucleo.terminada
        return self._sonido.state == "stop" and not self.pausado and self.segundo <= 0.01 and self._iniciada

    # ------------------------------------------------------------- control
    def iniciar(self) -> None:
        self._iniciada = False
        if self._nucleo is not None:
            self._nucleo.iniciar()
        else:
            self._sonido.play()
        self._iniciada = True

    def alternar_pausa(self) -> None:
        if self._nucleo is not None:
            self._nucleo.alternar_pausa()
            self.pausado = self._nucleo.pausado
            return
        if self.pausado:
            self._sonido.play()
            self._sonido.seek(self._pausa_en)
        else:
            self._pausa_en = self.segundo
            self._sonido.stop()
        self.pausado = not self.pausado

    def mover(self, segundos: float) -> None:
        if self._nucleo is not None:
            self._nucleo.mover(segundos)
        else:
            self._sonido.seek(max(0.0, self.segundo + segundos))

    def siguiente_nivel_voz(self) -> float:
        """100 → 75 → 50 → 25 → 100 %."""
        if self._nucleo is None:
            return 1.0
        actual = min(range(len(NIVELES_VOZ)), key=lambda i: abs(NIVELES_VOZ[i] - self._nucleo.voz))
        nivel = NIVELES_VOZ[(actual + 1) % len(NIVELES_VOZ)]
        self._nucleo.ajustar_voz(nivel)
        return nivel

    def detener(self) -> None:
        if self._nucleo is not None:
            self._nucleo.detener()
        elif self._sonido is not None:
            self._sonido.stop()
