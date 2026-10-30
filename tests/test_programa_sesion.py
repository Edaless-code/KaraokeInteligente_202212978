import pytest

from karaoke.db import BaseDatos
from karaoke.programa import CursorPrograma, cargar_programa, leer_programa
from karaoke.sesion import SesionKaraoke


@pytest.fixture
def bd(tmp_path):
    base = BaseDatos(tmp_path / "CANCIONES.db")
    base.agregar_cancion("Primera", ["a1", "a2", "a3"])
    base.agregar_cancion("Segunda", ["b1", "b2"])
    base.agregar_cancion("Tercera", ["c1"])
    yield base
    base.cerrar()


def test_leer_programa_con_numeraciones(tmp_path):
    (tmp_path / "PROGRAMA").write_text(
        "// mi lista\n1. Primera\n2) Segunda\n- Tercera\n* Cuarta\n\n# comentario\n5 - Quinta\n", encoding="utf-8")
    assert leer_programa(tmp_path / "PROGRAMA") == ["Primera", "Segunda", "Tercera", "Cuarta", "Quinta"]


def test_cargar_programa_resuelve_nombres_con_errores(bd):
    entradas = cargar_programa(bd, ["primera", "Segnda", "No existe"])
    assert [c is not None for _, c in entradas] == [True, True, False]


def test_orden_no_estricto(bd):
    cargar_programa(bd, ["Primera", "Segunda", "Tercera"])
    cursor = CursorPrograma(bd)
    assert cursor.siguiente().nombre_solicitado == "Primera"
    cursor.marcar_cantada(bd.existe_nombre("Tercera"))  # se adelantó
    assert [e.nombre_solicitado for e in cursor.pendientes()] == ["Primera", "Segunda"]
    cursor.saltar(cursor.siguiente())
    assert cursor.siguiente().nombre_solicitado == "Segunda"
    cursor.activo = False  # ya no seguir el programa
    assert cursor.siguiente() is None
    assert cursor.prioridad() == {}


def test_misma_cancion_dos_veces_en_el_programa(bd):
    cargar_programa(bd, ["Primera", "Primera"])
    cursor = CursorPrograma(bd)
    cursor.marcar_cantada(bd.existe_nombre("Primera"))
    assert len(cursor.pendientes()) == 1


def test_sesion_completa(bd):
    sesion = SesionKaraoke(bd, "manual")
    curso = sesion.iniciar(bd.obtener_cancion(1))
    assert not curso.continuar() and not curso.continuar()
    assert curso.continuar()  # tercera línea: terminó
    sesion.terminar(completada=True)
    sesion.iniciar(bd.obtener_cancion(2), linea=1)
    cantadas = sesion.finalizar()
    assert [(c.nombre, c.completada) for c in cantadas] == [("Primera", True), ("Segunda", False)]
    assert sesion.finalizada


def test_iniciar_otra_cancion_registra_la_anterior(bd):
    sesion = SesionKaraoke(bd, "manual")
    sesion.iniciar(bd.obtener_cancion(1))
    sesion.iniciar(bd.obtener_cancion(2))
    assert [c.nombre for c in sesion.cantadas] == ["Primera"]


def test_acciones_de_la_cancion(bd):
    sesion = SesionKaraoke(bd, "manual")
    curso = sesion.iniciar(bd.obtener_cancion(1))
    curso.ignorar()
    assert not curso.continuar() and curso.actual == 0  # en pausa no avanza
    curso.seguir()
    curso.continuar()
    curso.igual()
    assert curso.actual == 1 and curso.repeticiones_linea == 1
    curso.atras()
    assert curso.actual == 0
    curso.atras()
    assert curso.actual == 0  # no baja de la primera línea
    curso.continuar(); curso.continuar()
    curso.repetir()
    assert curso.actual == 0 and curso.repeticiones_cancion == 1


def test_linea_inicial_fuera_de_rango(bd):
    sesion = SesionKaraoke(bd, "manual")
    assert sesion.iniciar(bd.obtener_cancion(3), linea=50).actual == 0


def test_repetir_ultima(bd):
    sesion = SesionKaraoke(bd, "manual")
    assert sesion.repetir_ultima() is None
    sesion.iniciar(bd.obtener_cancion(2))
    sesion.terminar(True)
    assert sesion.repetir_ultima().cancion.nombre == "Segunda"
