import sqlite3

import pytest

from karaoke.db import BaseDatos, CancionDuplicada


@pytest.fixture
def bd(tmp_path):
    base = BaseDatos(tmp_path / "CANCIONES.db")
    yield base
    base.cerrar()


def test_crea_todas_las_tablas(tmp_path):
    base = BaseDatos(tmp_path / "nueva.db")
    assert not base.existia
    tablas = {r[0] for r in base.conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"NOMBRES", "LETRAS", "TEMP_NOMBRES", "TEMP_LETRAS", "PROGRAMA", "SESIONES",
            "HISTORIAL", "METADATOS"} <= tablas
    base.cerrar()


def test_detecta_base_existente_y_conserva_datos(tmp_path):
    ruta = tmp_path / "CANCIONES.db"
    base = BaseDatos(ruta)
    base.agregar_cancion("Uno", ["linea"])
    base.cerrar()
    otra = BaseDatos(ruta)
    assert otra.existia
    assert otra.contar_canciones() == 1
    assert otra.integridad() == "ok"
    otra.cerrar()


def test_prepara_una_base_creada_por_otra_version(tmp_path):
    """Una base que solo tiene las tablas mínimas de la especificación."""
    ruta = tmp_path / "CANCIONES.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute("CREATE TABLE METADATOS (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
    conexion.commit()
    conexion.close()
    base = BaseDatos(ruta)
    assert base.existia
    base.agregar_cancion("Funciona", ["si"])
    base.cerrar()


def test_codigo_autogenerado_y_consecutivo(bd):
    a = bd.agregar_cancion("A", ["x"])
    b = bd.agregar_cancion("B", ["y"])
    assert b == a + 1


def test_codigo_no_se_reutiliza_despues_de_borrar(bd):
    a = bd.agregar_cancion("A", ["x"])
    bd.borrar_cancion(a)
    assert bd.agregar_cancion("B", ["y"]) != a


def test_lineas_en_orden_y_sin_vacias(bd):
    codigo = bd.agregar_cancion("Orden", ["primera", "  ", "segunda", "tercera"])
    assert bd.obtener_cancion(codigo).lineas == ["primera", "segunda", "tercera"]


def test_nombre_duplicado_ignora_mayusculas_y_tildes(bd):
    bd.agregar_cancion("Canción Azul", ["x"])
    with pytest.raises(CancionDuplicada):
        bd.agregar_cancion("cancion azul", ["y"])


@pytest.mark.parametrize("nombre, lineas", [("", ["x"]), ("  ", ["x"]), ("Sin letra", []), ("Vacia", ["", " "])])
def test_validaciones_al_agregar(bd, nombre, lineas):
    with pytest.raises(ValueError):
        bd.agregar_cancion(nombre, lineas)


def test_obtener_inexistente(bd):
    assert bd.obtener_cancion(999) is None


def test_borrar_elimina_la_letra_en_cascada(bd):
    codigo = bd.agregar_cancion("Borrar", ["a", "b"])
    assert bd.borrar_cancion(codigo)
    assert bd.conexion.execute("SELECT COUNT(*) FROM LETRAS WHERE codigo=?", (codigo,)).fetchone()[0] == 0
    assert not bd.borrar_cancion(codigo)


def test_actualizar_letra_y_renombrar(bd):
    codigo = bd.agregar_cancion("Vieja", ["a", "b", "c"])
    bd.actualizar_letra(codigo, ["nueva uno", "nueva dos"])
    bd.renombrar(codigo, "Nueva")
    cancion = bd.obtener_cancion(codigo)
    assert cancion.nombre == "Nueva"
    assert cancion.lineas == ["nueva uno", "nueva dos"]
    with pytest.raises(ValueError):
        bd.actualizar_letra(codigo, [])


def test_renombrar_a_un_nombre_existente(bd):
    bd.agregar_cancion("Ocupado", ["x"])
    codigo = bd.agregar_cancion("Libre", ["y"])
    with pytest.raises(CancionDuplicada):
        bd.renombrar(codigo, "ocupado")
    bd.renombrar(codigo, "LIBRE")  # cambiar solo mayúsculas sí se permite


def test_buscar_por_nombre(bd):
    a = bd.agregar_cancion("Ghost of you", ["x"])
    b = bd.agregar_cancion("Sound of You", ["y"])
    assert bd.buscar_por_nombre("ghost of you") == [(a, "Ghost of you")]
    assert {c for c, _ in bd.buscar_por_nombre("of you")} == {a, b}
    assert bd.buscar_por_nombre("Gost of yu")[0][0] == a
    assert bd.buscar_por_nombre("") == []


def test_resolver_por_codigo_o_nombre(bd):
    codigo = bd.agregar_cancion("Por Nombre", ["x"])
    assert bd.resolver(str(codigo)) == [(codigo, "Por Nombre")]
    assert bd.resolver("por nombre") == [(codigo, "Por Nombre")]
    assert bd.resolver("12345") == []


def test_listar_paginado(bd):
    for i in range(25):
        bd.agregar_cancion(f"Canción {i:02d}", ["x", "y"])
    assert len(bd.listar_canciones(0, 10)) == 10
    assert len(bd.listar_canciones(20, 10)) == 5
    assert bd.listar_canciones(0, 1)[0][2] == 2  # número de líneas


def test_idioma_se_detecta_y_se_actualiza(bd):
    codigo = bd.agregar_cancion("Idioma", ["la noche de los que no duermen"])
    assert bd.obtener_cancion(codigo).idioma == "es"
    bd.actualizar_letra(codigo, ["you and me and the night"])
    assert bd.obtener_cancion(codigo).idioma == "en"


def test_revision_cambia_con_cada_escritura(bd):
    antes = bd.revision
    bd.agregar_cancion("R", ["x"])
    assert bd.revision > antes


def test_tablas_temporales_y_promocion(bd):
    temporal = bd.crear_temporal("sugerido", "Vosk")
    bd.agregar_linea_temporal(temporal, "uno")
    bd.agregar_linea_temporal(temporal, "dos")
    assert [t.lineas for t in bd.listar_temporales()] == [["uno", "dos"]]
    bd.actualizar_temporal(temporal, ["uno corregido", "dos", "tres"])
    codigo = bd.promover_temporal(temporal, "Aprendida")
    cancion = bd.obtener_cancion(codigo)
    assert cancion.lineas == ["uno corregido", "dos", "tres"]
    assert cancion.origen == "automatico"
    assert bd.listar_temporales() == []


def test_promover_con_nombre_duplicado_conserva_la_temporal(bd):
    bd.agregar_cancion("Existe", ["x"])
    temporal = bd.crear_temporal()
    bd.agregar_linea_temporal(temporal, "linea")
    with pytest.raises(CancionDuplicada):
        bd.promover_temporal(temporal, "existe")
    assert bd.obtener_temporal(temporal) is not None


def test_programa_y_vinculo_posterior(bd):
    bd.guardar_programa([("Aun no existe", None), ("Otra", None)])
    codigo = bd.agregar_cancion("Aun no existe", ["x"])
    assert bd.vincular_programa() == 1
    assert bd.obtener_programa()[0].codigo == codigo
    bd.marcar_programa(1, "cantada")
    bd.reiniciar_programa()
    assert {e.estado for e in bd.obtener_programa()} == {"pendiente"}


def test_borrar_cancion_del_programa_deja_la_entrada(bd):
    codigo = bd.agregar_cancion("En programa", ["x"])
    bd.guardar_programa([("En programa", codigo)])
    bd.borrar_cancion(codigo)
    assert bd.obtener_programa()[0].codigo is None


def test_historial_y_mas_cantadas(bd):
    codigo = bd.agregar_cancion("Popular", ["x"])
    sesion = bd.iniciar_sesion("manual")
    bd.registrar_interpretacion(sesion, codigo, "Popular", "manual", "2026-01-01 00:00:00", 3, True)
    bd.registrar_interpretacion(sesion, codigo, "Popular", "manual", "2026-01-01 00:01:00", 1, False)
    bd.terminar_sesion(sesion)
    assert bd.mas_cantadas() == [(codigo, "Popular", 1)]  # solo cuenta las completas
    assert len(bd.historial()) == 2


def test_sesion_abierta_se_cierra_al_reabrir(tmp_path):
    ruta = tmp_path / "CANCIONES.db"
    base = BaseDatos(ruta)
    base.iniciar_sesion("manual")
    base.cerrar()  # simula que el programa se cerró sin terminar la sesión
    otra = BaseDatos(ruta)
    assert otra.conexion.execute("SELECT COUNT(*) FROM SESIONES WHERE fin IS NULL").fetchone()[0] == 0
    otra.cerrar()
