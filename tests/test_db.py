import sqlite3

import pytest

from karaoke.db import (MAX_LINEA, MAX_NOMBRE, VERSION_ESQUEMA, BaseDatos, CancionDuplicada,
                        CancionEnPapelera)


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
    bd.eliminar_definitivamente(a)
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


def test_borrar_mueve_a_la_papelera_y_se_restaura(bd):
    codigo = bd.agregar_cancion("Borrar", ["a", "b"])
    assert bd.borrar_cancion(codigo)
    assert not bd.borrar_cancion(codigo)  # ya estaba en la papelera
    assert bd.obtener_cancion(codigo) is None
    assert bd.en_papelera(codigo)
    assert bd.contar_canciones() == 0
    assert bd.listar_canciones() == [] and bd.todas_las_letras() == {}
    assert bd.buscar_por_nombre("Borrar") == []
    assert [(c, n, l) for c, n, l, _ in bd.listar_papelera()] == [(codigo, "Borrar", 2)]
    assert bd.restaurar_cancion(codigo)
    assert bd.obtener_cancion(codigo).lineas == ["a", "b"]  # mismo código y letra


def test_eliminar_definitivamente_borra_la_letra_en_cascada(bd):
    codigo = bd.agregar_cancion("Borrar", ["a", "b"])
    assert not bd.eliminar_definitivamente(codigo)  # solo desde la papelera
    bd.borrar_cancion(codigo)
    assert bd.eliminar_definitivamente(codigo)
    assert bd.conexion.execute("SELECT COUNT(*) FROM LETRAS WHERE codigo=?", (codigo,)).fetchone()[0] == 0
    assert bd.obtener_cancion(codigo, incluir_papelera=True) is None


def test_vaciar_papelera_por_antiguedad(bd):
    vieja = bd.agregar_cancion("Vieja", ["x"])
    nueva = bd.agregar_cancion("Nueva", ["y"])
    bd.borrar_cancion(vieja)
    bd.borrar_cancion(nueva)
    bd.conexion.execute("UPDATE NOMBRES SET eliminada_en = '2020-01-01 00:00:00' WHERE codigo = ?", (vieja,))
    bd.conexion.commit()
    assert bd.vaciar_papelera(mas_de_dias=30) == 1
    assert [c for c, *_ in bd.listar_papelera()] == [nueva]
    assert bd.vaciar_papelera() == 1


def test_nombre_en_la_papelera_no_se_puede_reutilizar(bd):
    codigo = bd.agregar_cancion("Única", ["x"])
    bd.borrar_cancion(codigo)
    with pytest.raises(CancionEnPapelera) as error:
        bd.agregar_cancion("unica", ["y"])
    assert error.value.codigo == codigo and "papelera" in str(error.value)


def test_programa_ignora_canciones_en_la_papelera(bd):
    codigo = bd.agregar_cancion("En programa", ["x"])
    bd.guardar_programa([("En programa", codigo)])
    bd.borrar_cancion(codigo)
    assert bd.obtener_programa()[0].codigo is None
    bd.restaurar_cancion(codigo)
    assert bd.obtener_programa()[0].codigo == codigo


def test_transaccion_todo_o_nada(bd, monkeypatch):
    def fallar(*_):
        raise RuntimeError("falla simulada a la mitad")

    monkeypatch.setattr(bd, "_insertar_lineas", fallar)
    with pytest.raises(RuntimeError):
        bd.agregar_cancion("A medias", ["x"])
    assert bd.existe_nombre("A medias") is None  # no quedó el nombre sin letra
    assert bd.conexion.execute("SELECT COUNT(*) FROM NOMBRES").fetchone()[0] == 0


def test_textos_se_limpian_y_se_limitan(bd):
    codigo = bd.agregar_cancion("Nombre\x00 con\x1b control" + "x" * 500, ["linea\x07 uno", "\x00", "y" * 5000])
    cancion = bd.obtener_cancion(codigo)
    assert "\x00" not in cancion.nombre and "\x1b" not in cancion.nombre
    assert len(cancion.nombre) <= MAX_NOMBRE
    assert cancion.lineas[0] == "linea uno" and len(cancion.lineas) == 2
    assert len(cancion.lineas[1]) <= MAX_LINEA


def test_inyeccion_sql_se_guarda_como_texto(bd):
    nombre = "x'); DROP TABLE NOMBRES; --"
    codigo = bd.agregar_cancion(nombre, ["linea"])
    assert bd.obtener_cancion(codigo).nombre == nombre
    assert bd.buscar_por_nombre("DROP TABLE")[0][0] == codigo
    assert bd.contar_canciones() == 1


def test_migra_una_base_de_la_version_1_con_respaldo(tmp_path):
    ruta = tmp_path / "CANCIONES.db"
    vieja = sqlite3.connect(ruta)
    vieja.executescript("""
        CREATE TABLE NOMBRES (codigo INTEGER PRIMARY KEY AUTOINCREMENT, nombre_cancion TEXT NOT NULL,
            nombre_normalizado TEXT NOT NULL UNIQUE, artista TEXT NOT NULL DEFAULT '',
            idioma TEXT NOT NULL DEFAULT 'es', origen TEXT NOT NULL DEFAULT 'manual',
            fecha_registro TEXT NOT NULL, veces_cantada INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE METADATOS (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
        INSERT INTO METADATOS VALUES ('version_esquema', '1');
        INSERT INTO NOMBRES(nombre_cancion, nombre_normalizado, fecha_registro) VALUES ('Vieja', 'vieja', 'hoy');
    """)
    vieja.close()
    base = BaseDatos(ruta)
    assert base.contar_canciones() == 1
    assert base.borrar_cancion(1)  # la papelera ya funciona
    assert base._version_guardada() == VERSION_ESQUEMA
    assert (tmp_path / f"CANCIONES.respaldo-antes-de-v{VERSION_ESQUEMA}.db").exists()
    base.cerrar()


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


def test_eliminar_definitivamente_del_programa_deja_la_entrada(bd):
    codigo = bd.agregar_cancion("En programa", ["x"])
    bd.guardar_programa([("En programa", codigo)])
    bd.borrar_cancion(codigo)
    bd.eliminar_definitivamente(codigo)
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
