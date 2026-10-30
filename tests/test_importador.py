import pytest

from karaoke.config import cargar_config
from karaoke.db import BaseDatos
from karaoke.importador import analizar_texto, importar_archivo


@pytest.fixture
def entorno(tmp_path):
    config = cargar_config(tmp_path)
    bd = BaseDatos(config.ruta_bd)
    yield config, bd, tmp_path
    bd.cerrar()


def test_bloques_separados_por_linea_en_blanco():
    texto = "Uno\nlinea a\nlinea b\n\n\nDos\nlinea c\n"
    assert analizar_texto(texto) == [("Uno", ["linea a", "linea b"]), ("Dos", ["linea c"])]


def test_encabezados_explicitos_permiten_estrofas():
    texto = "# Uno\nlinea a\n\nlinea b\nNOMBRE: Dos\nlinea c"
    assert analizar_texto(texto) == [("Uno", ["linea a", "linea b"]), ("Dos", ["linea c"])]


def test_ignora_comentarios_y_etiquetas():
    texto = "// comentario\nUno\n[Verse 1]\nlinea a\nChorus (x2)\nlinea b\n(Fade out)"
    assert analizar_texto(texto) == [("Uno", ["linea a", "linea b"])]


def test_saltos_de_linea_de_windows():
    assert analizar_texto("Uno\r\nlinea a\r\n\r\nDos\r\nlinea b") == [("Uno", ["linea a"]), ("Dos", ["linea b"])]


def test_importa_omite_duplicadas_y_sin_letra(entorno):
    config, bd, carpeta = entorno
    bd.agregar_cancion("Ya existe", ["x"])
    (carpeta / "c.txt").write_text("Nueva\nuna linea\n\nYa existe\notra\n\nSolo nombre\n", encoding="utf-8")
    resultado = importar_archivo(bd, carpeta / "c.txt", config)
    assert [n for _, n in resultado.agregadas] == ["Nueva"]
    motivos = dict(resultado.omitidas)
    assert "ya existe" in motivos["Ya existe"]
    assert "no tiene letra" in motivos["Solo nombre"]


def test_divide_lineas_largas(entorno):
    config, bd, carpeta = entorno
    larga = " ".join(["palabra"] * 30)  # 239 caracteres
    (carpeta / "c.txt").write_text(f"Larga\n{larga}\n", encoding="utf-8")
    resultado = importar_archivo(bd, carpeta / "c.txt", config)
    cancion = bd.obtener_cancion(resultado.agregadas[0][0])
    assert resultado.lineas_ajustadas == 1
    assert all(len(l) <= 80 for l in cancion.lineas)
    assert len(cancion.lineas) == 3


def test_archivo_ansi_de_windows(entorno):
    config, bd, carpeta = entorno
    (carpeta / "c.txt").write_bytes("Canción\nañoranza del corazón\n".encode("cp1252"))
    resultado = importar_archivo(bd, carpeta / "c.txt", config)
    assert bd.obtener_cancion(resultado.agregadas[0][0]).lineas == ["añoranza del corazón"]


def test_importa_los_ejemplos_del_proyecto(entorno):
    config, bd, _ = entorno
    resultado = importar_archivo(bd, "ejemplos/canciones.txt", config)
    assert not resultado.omitidas
    assert len(resultado.agregadas) >= 2


def test_importar_avisa_si_la_cancion_esta_en_la_papelera(entorno):
    config, bd, carpeta = entorno
    bd.borrar_cancion(bd.agregar_cancion("Borrada", ["x"]))
    (carpeta / "c.txt").write_text("Borrada\nuna linea\n", encoding="utf-8")
    resultado = importar_archivo(bd, carpeta / "c.txt", config)
    assert "papelera" in dict(resultado.omitidas)["Borrada"]


def test_rechaza_archivos_enormes(entorno, monkeypatch):
    config, bd, carpeta = entorno
    import karaoke.texto as texto
    (carpeta / "grande.txt").write_text("x" * 2000, encoding="utf-8")
    monkeypatch.setattr(texto, "MAX_BYTES_TEXTO", 1000)
    with pytest.raises(ValueError):
        texto.leer_texto(carpeta / "grande.txt", maximo=1000)
