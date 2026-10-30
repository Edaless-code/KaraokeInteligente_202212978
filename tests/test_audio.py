import wave

import numpy as np
import pytest

from karaoke.audio.fuentes import ErrorAudio, FuenteArchivo, leer_archivo_audio
from karaoke.audio.limpieza import (SALTO, LimpiadorAudio, a_pcm16, aislar_voz_estereo, desde_pcm16,
                                    nivel_db, remuestrear)
from karaoke.audio.motores import MotorSimulado, Transcripcion, es_alucinacion

FS = 16000


def snr(referencia, senal):
    n = min(len(referencia), len(senal))
    referencia, senal = referencia[:n], senal[:n]
    escala = np.dot(senal, referencia) / np.dot(referencia, referencia)
    error = senal - escala * referencia
    return 10 * np.log10(np.sum((escala * referencia) ** 2) / np.sum(error ** 2))


def voz_sintetica(segundos=4.0, silencio_inicial=1.5):
    t = np.arange(int(FS * segundos)) / FS
    voz = sum(np.sin(2 * np.pi * 220 * k * t) / k for k in range(1, 8)) * 0.15
    voz *= (np.sin(2 * np.pi * 3 * t) > 0)
    voz[: int(FS * silencio_inicial)] = 0
    return voz.astype(np.float32)


def test_pcm16_ida_y_vuelta():
    x = np.array([0.0, 0.5, -0.5, 1.5], dtype=np.float32)
    y = desde_pcm16(a_pcm16(x))
    assert np.allclose(y[:3], x[:3], atol=1e-4) and y[3] == pytest.approx(1.0, abs=1e-4)


def test_remuestrear_conserva_duracion():
    assert len(remuestrear(np.zeros(48000, np.float32), 48000, 16000)) == 16000
    assert len(remuestrear(np.zeros(8000, np.float32), 8000, 16000)) == 16000


def test_reconstruccion_perfecta_sin_filtros():
    limpiador = LimpiadorAudio(FS, pasa_altos=-100, pasa_bajos=9000, reduccion_ruido=False,
                               control_ganancia=False)
    x = np.random.default_rng(0).normal(0, 0.1, FS * 2).astype(np.float32)
    y = limpiador.procesar_todo(x)
    assert np.max(np.abs(y[SALTO:] - x[SALTO:len(y)])) < 1e-5


def test_la_limpieza_mejora_la_relacion_senal_ruido():
    voz = voz_sintetica(6, 2)
    rng = np.random.default_rng(1)
    t = np.arange(len(voz)) / FS
    mezcla = (voz + rng.normal(0, 0.05, len(voz)) + 0.08 * np.sin(2 * np.pi * 50 * t)).astype(np.float32)
    limpia = LimpiadorAudio(FS, control_ganancia=False).procesar_todo(mezcla)
    assert snr(voz, limpia) > snr(voz, mezcla) + 6


def test_detector_de_voz():
    voz = voz_sintetica(4, 1.5)
    ruido = np.random.default_rng(2).normal(0, 0.01, len(voz)).astype(np.float32)
    limpiador = LimpiadorAudio(FS)
    estados = []
    for i in range(0, len(voz), 1600):
        limpiador.procesar((voz + ruido)[i:i + 1600])
        estados.append(limpiador.voz_activa)
    assert not any(estados[:15])  # silencio inicial
    assert sum(estados[18:]) >= len(estados[18:]) - 1


def test_control_de_ganancia_nivela_y_no_satura():
    voz = voz_sintetica(4, 1.5) * 0.05  # cantante muy bajito
    salida = LimpiadorAudio(FS, reduccion_ruido=False).procesar_todo(voz)
    assert nivel_db(salida[FS * 2:]) > nivel_db(voz[FS * 2:]) + 6
    fuerte = LimpiadorAudio(FS, reduccion_ruido=False).procesar_todo(voz_sintetica() * 6)
    assert np.max(np.abs(fuerte)) <= 1.0


def test_aislar_voz_del_centro():
    voz = voz_sintetica(3, 0)
    rng = np.random.default_rng(3)
    estereo = np.stack([voz + rng.normal(0, 0.1, len(voz)), voz + rng.normal(0, 0.1, len(voz))], 1)
    aislada = aislar_voz_estereo(estereo.astype(np.float32))
    assert len(aislada) == len(voz)
    assert snr(voz, aislada) > snr(voz, estereo.mean(1)) + 2


def escribir_wav(ruta, muestras, frecuencia=FS, canales=1):
    with wave.open(str(ruta), "wb") as archivo:
        archivo.setnchannels(canales)
        archivo.setsampwidth(2)
        archivo.setframerate(frecuencia)
        archivo.writeframes(a_pcm16(muestras))


def test_leer_wav_estereo_44k(tmp_path):
    t = np.arange(44100) / 44100
    tono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    escribir_wav(tmp_path / "a.wav", np.repeat(tono, 2), 44100, canales=2)
    muestras = leer_archivo_audio(tmp_path / "a.wav", FS)
    assert abs(len(muestras) - FS) <= 2
    assert 0.15 < np.max(np.abs(muestras)) < 0.35


def test_leer_mp3_de_ejemplo():
    muestras = leer_archivo_audio("ejemplos/Sound_of_You.mp3", FS)
    assert 185 < len(muestras) / FS < 189


def test_archivo_inexistente():
    with pytest.raises(ErrorAudio):
        leer_archivo_audio("no_existe.wav")


def test_fuente_archivo_entrega_todo_y_termina(tmp_path):
    escribir_wav(tmp_path / "b.wav", np.zeros(FS * 2, np.float32))
    fuente = FuenteArchivo(tmp_path / "b.wav", tiempo_real=False, desde_segundo=0.5)
    fuente.iniciar()
    total = 0
    while (bloque := fuente.leer()) is not None:
        total += len(bloque)
    assert fuente.terminada and total == int(FS * 1.5)


def test_motor_simulado_entrega_parciales_y_final():
    motor = MotorSimulado("0:01 hola mundo", segundos_por_palabra=0.3)
    tipos = []
    for _ in range(30):
        tipos += [(t.tipo, t.texto) for t in motor.procesar(np.zeros(1600, np.float32))]
    assert tipos == [("parcial", "hola"), ("parcial", "hola mundo"), ("final", "hola mundo")]


def test_transcripcion_ignora_unk():
    t = Transcripcion("final", "hola [unk] mundo [unk]")
    assert t.palabras == ["hola", "mundo"] and t.desconocidas == 2


@pytest.mark.parametrize("texto, es", [("Music", True), ("2.5%", True), ("Thank you.", True),
                                       ("...", True), ("I miss the ghost of you", False), ("No sé cómo", False)])
def test_alucinaciones_de_whisper(texto, es):
    assert es_alucinacion(texto) is es


def test_extraccion_segura_de_modelos(tmp_path):
    import zipfile

    from karaoke.audio.modelos import extraer_seguro

    bueno = tmp_path / "bueno.zip"
    with zipfile.ZipFile(bueno, "w") as z:
        z.writestr("modelo/am/final.mdl", "x")
    extraer_seguro(zipfile.ZipFile(bueno), tmp_path / "salida")
    assert (tmp_path / "salida" / "modelo" / "am" / "final.mdl").exists()

    malo = tmp_path / "malo.zip"
    with zipfile.ZipFile(malo, "w") as z:
        z.writestr("../../fuera.txt", "x")
    with pytest.raises(RuntimeError):
        extraer_seguro(zipfile.ZipFile(malo), tmp_path / "salida2")
    assert not (tmp_path / "fuera.txt").exists()
