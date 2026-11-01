from karaoke.config import cargar_config


def test_crea_el_ini_con_los_valores_por_omision(tmp_path):
    config = cargar_config(tmp_path)
    assert (tmp_path / "karaoke.ini").exists()
    assert config.caracteres_por_linea == 80
    assert config.entero("letras", "lineas_promedio_cancion") == 10
    assert config.por_pagina == 10
    assert config.ruta_bd == tmp_path / "CANCIONES.db"


def test_lee_los_cambios_del_ini(tmp_path):
    (tmp_path / "karaoke.ini").write_text(
        "[letras]\ncaracteres_por_linea = 120\nelementos_por_pagina = 5\n[audio]\nreduccion_ruido = no\n",
        encoding="utf-8")
    config = cargar_config(tmp_path)
    assert config.caracteres_por_linea == 120
    assert config.por_pagina == 5
    assert config.booleano("audio", "reduccion_ruido") is False
    assert config.entero("letras", "lineas_promedio_cancion") == 10  # faltante = omisión


def test_valores_invalidos_usan_la_omision(tmp_path):
    (tmp_path / "karaoke.ini").write_text("[letras]\ncaracteres_por_linea = mucho\n", encoding="utf-8")
    assert cargar_config(tmp_path).caracteres_por_linea == 80


def test_guardar_conserva_lo_establecido(tmp_path):
    config = cargar_config(tmp_path)
    config.establecer("audio", "dispositivo", "3")
    config.guardar()
    assert cargar_config(tmp_path).texto("audio", "dispositivo") == "3"


def test_variable_de_entorno_karaoke_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KARAOKE_HOME", str(tmp_path))
    assert cargar_config().carpeta == tmp_path.resolve()


def test_karaoke_ini_viejo_toma_la_letra_junto_con_la_voz(tmp_path):
    from karaoke.config import cargar_config

    (tmp_path / "karaoke.ini").write_text("[automatico]\nsegundos_letra_adelantada = 0.5\n", encoding="utf-8")
    assert cargar_config(tmp_path).decimal("automatico", "segundos_letra_adelantada") == 0.0
    (tmp_path / "karaoke.ini").write_text("[automatico]\nsegundos_letra_adelantada = 0.3\n", encoding="utf-8")
    assert cargar_config(tmp_path).decimal("automatico", "segundos_letra_adelantada") == 0.3  # elegido a mano
