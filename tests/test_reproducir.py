"""Reproducir con letra (opción r) y control de la voz del artista."""

import numpy as np

from karaoke.audio.reproductor import mezclar, voz_del_centro


def test_bajar_la_voz_del_centro_conserva_los_lados():
    fs = 44100
    t = np.arange(fs) / fs
    voz = 0.5 * np.sin(2 * np.pi * 440 * t)          # en el centro: igual en ambos canales
    guitarra = 0.3 * np.sin(2 * np.pi * 660 * t)     # solo a la izquierda
    estereo = np.stack([voz + guitarra, voz], axis=1).astype(np.float32)
    centro = voz_del_centro(estereo, fs)
    sin_voz = mezclar(estereo, centro, 0.0)
    # la voz casi desaparece del canal derecho (donde solo estaba la voz)...
    assert np.abs(sin_voz[4000:-4000, 1]).max() < 0.2 * np.abs(voz).max()
    # ...la guitarra de la izquierda se queda casi intacta...
    resto = sin_voz[4000:-4000, 0] - guitarra[4000:-4000]
    assert np.abs(resto).max() < 0.25 * np.abs(guitarra).max()
    # ...y la mezcla original no cambia con la voz al 100 %
    assert np.array_equal(mezclar(estereo, centro, 1.0), estereo)


def test_opcion_r_sin_pistas_avisa(tmp_path):
    from karaoke.config import cargar_config
    from karaoke.db import BaseDatos
    from karaoke.ui.consola import Teclado
    from karaoke.ui.menus import Aplicacion
    from karaoke.ui.reproducir import ReproducirConLetra

    class Teclas(Teclado):
        def __init__(self):
            self.interactivo = False

        def linea(self, mensaje=""):
            return ""

        def tecla(self, espera=None):
            return "\n"

    config = cargar_config(tmp_path)
    bd = BaseDatos(config.ruta_bd)
    ReproducirConLetra(Aplicacion(config, bd, Teclas())).ejecutar()  # no truena
    bd.cerrar()


def test_los_ejemplos_quedan_vinculados(tmp_path):
    import shutil
    from pathlib import Path

    from karaoke.config import cargar_config
    from karaoke.db import BaseDatos
    from karaoke.importador import importar_archivo
    from karaoke.ui.menus import Aplicacion
    from karaoke.ui.reproducir import ReproducirConLetra

    raiz = Path(__file__).resolve().parent.parent
    (tmp_path / "ejemplos").mkdir()
    shutil.copy(raiz / "ejemplos" / "Ghost_of_you_Remastered.mp3", tmp_path / "ejemplos")
    config = cargar_config(tmp_path)
    bd = BaseDatos(config.ruta_bd)
    importar_archivo(bd, raiz / "ejemplos" / "canciones.txt", config)
    ReproducirConLetra(Aplicacion(config, bd, teclado=object())).vincular_ejemplos()
    assert [(n, a) for _, n, a in bd.listar_pistas()] == [("Ghost of you", "ejemplos/Ghost_of_you_Remastered.mp3")]
    bd.cerrar()


def test_niveles_de_voz_y_cambio_suave():
    from karaoke.audio.reproductor import NIVELES_VOZ, Reproductor

    r = Reproductor.__new__(Reproductor)
    import threading
    r._candado, r.voz = threading.Lock(), 1.0
    vistos = []
    for _ in range(6):
        r.bajar_voz()
        vistos.append(r.voz)
    assert vistos == [0.75, 0.5, 0.25, 0.25, 0.25, 0.25]  # nunca baja de 25 %
    r.subir_voz()
    assert r.voz == 0.5
    assert NIVELES_VOZ == (1.0, 0.75, 0.5, 0.25)
    # la rampa evita saltos: el primer valor es el nivel anterior, el último el nuevo
    fs = 1000
    estereo = np.ones((fs, 2), np.float32)
    centro = np.ones(fs, np.float32)
    salida = mezclar(estereo, centro, np.linspace(1.0, 0.5, fs, dtype=np.float32))
    assert abs(salida[0, 0] - 1.0) < 1e-6 and abs(salida[-1, 0] - 0.5) < 1e-6
