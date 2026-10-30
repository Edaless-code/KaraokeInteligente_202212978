"""Fuentes de voz para el modo automático de la app móvil.

* ``VozAndroid``: usa el reconocedor de voz del propio teléfono
  (``android.speech.SpeechRecognizer`` a través de ``plyer.stt``). En la
  mayoría de los teléfonos funciona sin internet si el paquete de idioma está
  descargado, y entrega resultados parciales mientras se canta. El
  reconocedor de Android se detiene solo tras unos segundos de silencio, así
  que se vuelve a iniciar automáticamente para escuchar de forma continua.
* ``VozDemostracion``: reproduce un guion de texto con tiempos (el mismo
  ``MotorSimulado`` del programa de escritorio). Sirve para mostrar el modo
  automático sin cantar, y en la computadora mientras se desarrolla.

Las dos entregan objetos ``Transcripcion`` al ``ControladorAutomatico``, el
mismo que usa la versión de Windows.
"""

from __future__ import annotations

import time
from pathlib import Path

from kivy.utils import platform

from karaoke.transcripcion import Transcripcion

IDIOMAS_ANDROID = {"es": "es-ES", "en": "en-US"}


class FuenteVoz:
    nombre = "voz"
    idioma = "es"

    def iniciar(self) -> None: ...

    def detener(self) -> None: ...

    def cambiar_idioma(self, idioma: str) -> None:
        self.idioma = idioma

    def recoger(self, segundo: float) -> tuple[list[Transcripcion], bool]:
        """Transcripciones nuevas y si ahora mismo hay voz."""
        return [], False


class VozAndroid(FuenteVoz):
    nombre = "Reconocedor de voz de Android"

    def __init__(self, idioma: str = "es"):
        from plyer import stt

        self.stt = stt
        self.idioma = idioma
        self.activa = False
        self._ultimo_parcial = ""
        self._ultimo_inicio = 0.0
        self._ultima_voz = 0.0
        self.error = ""

    @staticmethod
    def pedir_permiso(al_responder) -> None:
        """Pide el permiso de micrófono (Android 6+). Es el único permiso
        que usa la app."""
        from android.permissions import Permission, request_permissions

        request_permissions([Permission.RECORD_AUDIO],
                            lambda _p, concedidos: al_responder(all(concedidos)))

    def _arrancar(self) -> None:
        self.stt.language = IDIOMAS_ANDROID.get(self.idioma, "es-ES")
        try:
            self.stt.prefer_offline = True
        except Exception:
            pass
        self._ultimo_parcial = ""
        self._ultimo_inicio = time.monotonic()
        try:
            self.stt.start()
        except Exception as ex:
            self.error = str(ex)

    def iniciar(self) -> None:
        self.activa = True
        self._arrancar()

    def detener(self) -> None:
        self.activa = False
        try:
            self.stt.stop()
        except Exception:
            pass

    def cambiar_idioma(self, idioma: str) -> None:
        if idioma == self.idioma:
            return
        self.idioma = idioma
        if self.activa:
            self.detener()
            self.iniciar()

    def recoger(self, segundo: float) -> tuple[list[Transcripcion], bool]:
        resultados: list[Transcripcion] = []
        if not self.activa:
            return resultados, False
        parciales = list(getattr(self.stt, "partial_results", []) or [])
        if parciales:
            texto = str(parciales[-1]).strip()
            if texto and texto != self._ultimo_parcial:
                self._ultimo_parcial = texto
                self._ultima_voz = time.monotonic()
                resultados.append(Transcripcion("parcial", texto, "libre", self.idioma, 1.0, segundo))
        if not self.stt.listening and time.monotonic() - self._ultimo_inicio > 0.6:
            finales = list(getattr(self.stt, "results", []) or [])
            texto = str(finales[0]).strip() if finales else self._ultimo_parcial
            if texto:
                resultados.append(Transcripcion("final", texto, "libre", self.idioma, 1.0, segundo))
            self._arrancar()  # escucha continua
        hay_voz = time.monotonic() - self._ultima_voz < 2.0
        return resultados, hay_voz


class VozDemostracion(FuenteVoz):
    nombre = "Demostración (guion de Sound of You)"

    def __init__(self, guion: Path, idioma: str = "en"):
        from karaoke.motor_simulado import MotorSimulado

        self.motor = MotorSimulado(str(guion), segundos_por_palabra=0.38, idioma=idioma)
        self.idioma = idioma
        self._inicio = None
        self._ultimo = 0.0

    def iniciar(self) -> None:
        self._inicio = time.monotonic()

    def recoger(self, segundo: float) -> tuple[list[Transcripcion], bool]:
        if self._inicio is None:
            return [], False
        transcurrido = time.monotonic() - self._inicio
        resultados = self.motor.procesar_hasta(transcurrido)
        hablando = any(f.inicio <= transcurrido <= f.inicio + len(f.palabras) * 0.38 + 0.5
                       for f in self.motor.frases)
        return resultados, hablando


def crear_fuente(demostracion: bool, guion: Path, idioma: str = "es") -> FuenteVoz:
    if demostracion or platform != "android":
        return VozDemostracion(guion)
    return VozAndroid(idioma)
