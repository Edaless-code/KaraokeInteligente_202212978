"""Elección automática del micrófono (con una tarjeta de sonido simulada)."""

import numpy as np
import pytest

from karaoke.audio.fuentes import ErrorAudio, detectar_microfono, listar_microfonos_detalle


class TarjetaFalsa:
    """0: salida · 1: micrófono desconectado (solo ceros) · 2: no abre · 3: funciona."""

    class default:
        device = (1, 0)

    def query_hostapis(self):
        return [{"name": "MME"}, {"name": "Windows WASAPI"}]

    def query_devices(self, indice=None, tipo=None):
        dispositivos = [
            {"name": "Bocinas", "max_input_channels": 0, "hostapi": 0, "default_samplerate": 48000},
            {"name": "Micrófono de la cámara", "max_input_channels": 1, "hostapi": 0, "default_samplerate": 48000},
            {"name": "Micrófono roto", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 48000},
            {"name": "Auriculares USB", "max_input_channels": 1, "hostapi": 1, "default_samplerate": 16000},
        ]
        return dispositivos if indice is None else dispositivos[indice]

    def rec(self, cuadros, samplerate, channels, dtype, device, blocking):
        if device == 2:
            raise RuntimeError("no se puede abrir")
        if device == 1:
            return np.zeros((cuadros, 1), np.float32)
        return (np.random.default_rng(0).standard_normal((cuadros, 1)) * 0.05).astype(np.float32)


def test_lista_completa_con_sistema_de_audio():
    assert listar_microfonos_detalle(TarjetaFalsa()) == [
        (1, "Micrófono de la cámara", "MME"),
        (2, "Micrófono roto", "Windows WASAPI"),
        (3, "Auriculares USB", "Windows WASAPI"),
    ]


def test_elige_el_que_capta_sonido():
    # el predeterminado (1) solo da ceros y el 2 no abre: se queda con el 3
    assert detectar_microfono(None, TarjetaFalsa()) == (3, "Auriculares USB (Windows WASAPI)")


def test_respeta_el_elegido_si_funciona():
    assert detectar_microfono("3", TarjetaFalsa())[0] == 3


def test_ninguno_funciona():
    class SinMicros(TarjetaFalsa):
        def rec(self, *a, **k):
            raise RuntimeError("nada")

    with pytest.raises(ErrorAudio):
        detectar_microfono(None, SinMicros())
