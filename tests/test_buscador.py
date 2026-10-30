import pytest

from karaoke.buscador import Buscador, alinear
from karaoke.config import cargar_config
from karaoke.db import BaseDatos
from karaoke.importador import importar_archivo


@pytest.fixture
def buscador(tmp_path):
    config = cargar_config(tmp_path)
    bd = BaseDatos(config.ruta_bd)
    importar_archivo(bd, "ejemplos/canciones.txt", config)
    bd.agregar_cancion("Lluvia de papel", [
        "La lluvia cae sobre la ciudad dormida",
        "y las farolas cuentan historias de papel",
        "camino solo buscando tu sonrisa perdida",
    ])
    yield Buscador(bd, config), bd
    bd.cerrar()


@pytest.mark.parametrize("consulta, nombre, linea", [
    ("follow me everywhere", "Sound of You", 3),
    ("deserve someone better", "Sound of You", 22),
    ("dead of night", "Ghost of you", 1),
    ("no se como salvarme", "Ghost of you", 9),
    ("farolas cuentan historias", "Lluvia de papel", 2),
    ("farolas cuentam istorias", "Lluvia de papel", 2),  # errores de dedo
])
def test_identifica_cancion_y_linea(buscador, consulta, nombre, linea):
    b, _ = buscador
    resultado = b.identificar(consulta)
    assert resultado is not None
    assert resultado.nombre == nombre
    assert resultado.linea_actual + 1 == linea


@pytest.mark.parametrize("consulta", ["the", "la", "you", "do that", "zzz qqq", ""])
def test_no_identifica_con_poca_evidencia(buscador, consulta):
    b, _ = buscador
    assert b.identificar(consulta) is None


def test_prioridad_del_programa_desempata(buscador):
    b, bd = buscador
    a = bd.agregar_cancion("Copia A", ["una frase compartida entre dos canciones"])
    c = bd.agregar_cancion("Copia B", ["una frase compartida entre dos canciones"])
    assert b.identificar("frase compartida entre dos canciones") is None  # empate
    assert b.identificar("frase compartida entre dos canciones", prioridad={c: 0.12}).codigo == c
    assert a != c


def test_el_indice_se_actualiza_con_los_cambios(buscador):
    b, bd = buscador
    assert b.identificar("palabras totalmente originales inventadas hoy") is None
    bd.agregar_cancion("Nueva", ["palabras totalmente originales inventadas hoy"])
    assert b.identificar("palabras totalmente originales inventadas hoy").nombre == "Nueva"


def test_solo_restringe_la_busqueda(buscador):
    b, bd = buscador
    codigo = bd.existe_nombre("Lluvia de papel")
    assert b.buscar("follow me everywhere", solo={codigo}) == []


def test_alinear_exigir_ultima():
    letra = "a b c d e f".split()
    bruto, ini, fin = alinear(["b", "c", "x"], [1, 1, 1], letra, 0.8)
    assert (ini, fin) == (1, 2)
    bruto, ini, fin = alinear(["b", "c", "x"], [1, 1, 1], letra, 0.8, exigir_ultima=True)
    assert fin == -1
