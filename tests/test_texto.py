import pytest

from karaoke.texto import (ajustar_linea, detectar_idioma, dividir_linea, es_etiqueta, leer_texto,
                           normalizar, palabras, semejanza, vocabulario)


@pytest.mark.parametrize("entrada, esperado", [
    ("¡Ay, ay, ay! Canta y no llores", "ay ay ay canta y no llores"),
    ("Canción del NIÑO", "cancion del niño"),
    ("I don't want, I’m afraid", "i dont want im afraid"),
    ("  muchos   espacios\t y\nsaltos ", "muchos espacios y saltos"),
    ("¿Qué?!...", "que"),
    ("", ""),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_palabras_vacias():
    assert palabras("") == []
    assert palabras("!!!") == []


def test_semejanza():
    assert semejanza("corazon", "corazon") == 1.0
    assert semejanza("corazon", "corason") > 0.8
    assert semejanza("sol", "estrellas") < 0.5
    assert semejanza("", "algo") == 0.0


def test_dividir_linea_respeta_maximo_y_palabras():
    linea = "esta es una linea bastante larga que se debe dividir en varias partes"
    partes = dividir_linea(linea, 20)
    assert all(len(p) <= 20 for p in partes)
    assert " ".join(partes) == linea


def test_dividir_palabra_mas_larga_que_el_maximo():
    partes = dividir_linea("a " + "x" * 25 + " b", 10)
    assert all(len(p) <= 10 for p in partes)
    assert "".join(partes).replace(" ", "") == "a" + "x" * 25 + "b"


@pytest.mark.parametrize("accion, esperado", [
    ("conservar", ["uno dos tres cuatro"]),
    ("truncar", ["uno dos"]),
    ("dividir", ["uno dos", "tres", "cuatro"]),
])
def test_ajustar_linea(accion, esperado):
    assert ajustar_linea("uno dos tres cuatro", 7, accion) == esperado


def test_ajustar_linea_vacia():
    assert ajustar_linea("   ", 80, "dividir") == []


@pytest.mark.parametrize("renglon, es", [
    ("Chorus (Repit 2x Faded)", True), ("Coro:", True), ("[Verso 2]", True), ("(Fade out)", True),
    ("[Beat Drop]", True), ("Verso 2", True), ("Bridge over troubled water", False),
    ("Intro de la noche", False), ("Corazón de melón", False),
])
def test_es_etiqueta(renglon, es):
    assert es_etiqueta(renglon) is es


def test_detectar_idioma():
    assert detectar_idioma(["la noche es de los que no duermen"]) == "es"
    assert detectar_idioma(["I don't want to lose you, you and me"]) == "en"
    assert detectar_idioma([]) == "es"


def test_vocabulario_conserva_tildes_y_contracciones():
    assert "canción" in vocabulario(["¡Canción!"])
    voc = vocabulario(["I dont know, I’m here"], "en")
    assert {"don't", "dont", "i'm"} <= voc


def test_leer_texto_codificaciones(tmp_path):
    texto = "Canción del niño\nañoranza"
    (tmp_path / "utf8.txt").write_text(texto, encoding="utf-8")
    (tmp_path / "bom.txt").write_text(texto, encoding="utf-8-sig")
    (tmp_path / "ansi.txt").write_bytes(texto.encode("cp1252"))
    for nombre in ("utf8.txt", "bom.txt", "ansi.txt"):
        assert leer_texto(tmp_path / nombre) == texto
