"""Pruebas de integración: ejecutan el programa completo con entradas
escritas, como lo haría un usuario, y revisan la base de datos al final."""

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def ejecutar(carpeta: Path, teclas: list[str], tiempo: int = 60) -> str:
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8")
    proceso = subprocess.run(
        [sys.executable, str(RAIZ / "main.py"), "--carpeta", str(carpeta)],
        input="\n".join(teclas) + "\n", capture_output=True, text=True, encoding="utf-8",
        timeout=tiempo, env=entorno,
    )
    assert proceso.returncode == 0, proceso.stderr
    return proceso.stdout


def consulta(carpeta: Path, sql: str):
    conexion = sqlite3.connect(carpeta / "CANCIONES.db")
    try:
        return conexion.execute(sql).fetchall()
    finally:
        conexion.close()


@pytest.fixture
def carpeta(tmp_path):
    shutil.copy(RAIZ / "ejemplos" / "canciones.txt", tmp_path / "canciones.txt")
    return tmp_path


def test_arranca_crea_la_base_y_sale(carpeta):
    salida = ejecutar(carpeta, ["s"])
    assert "creada" in salida and "Gracias" in salida
    salida = ejecutar(carpeta, ["s"])
    assert "encontrada" in salida  # la segunda vez la detecta


def test_alimentacion_desde_archivo_y_listado(carpeta):
    salida = ejecutar(carpeta, ["f", "t", "", "", "r", "w", "", "s"])
    assert "+ [1] Sound of You" in salida and "+ [2] Ghost of you" in salida
    assert consulta(carpeta, "SELECT COUNT(*) FROM NOMBRES") == [(2,)]


def test_alimentacion_manual_campo_por_campo(carpeta):
    teclas = ["f", "e", "Mi canción", "primera línea", "segunda línea", "", "", "r", "s"]
    salida = ejecutar(carpeta, teclas)
    assert "código 1" in salida
    assert consulta(carpeta, "SELECT linea FROM LETRAS ORDER BY numero_linea") == [
        ("primera línea",), ("segunda línea",)]


def test_ver_letra_y_codigo_inexistente(carpeta):
    salida = ejecutar(carpeta, ["f", "t", "", "", "r", "x", "2", "", "", "x", "77", "", "s"])
    assert "I wake up in the dead of night" in salida
    assert "NO EXISTE ninguna canción con el código 77" in salida


def test_corregir_y_borrar_con_confirmacion(carpeta):
    teclas = ["f", "t", "", "", "r",
              "u", "ghost", "e 1", "Primera línea corregida", "g", "",
              "b", "1", "n", "",
              "b", "sound of you", "s", "", "s"]
    salida = ejecutar(carpeta, teclas)
    assert "No se borró nada" in salida and "Se movió a la papelera" in salida
    assert consulta(carpeta, "SELECT nombre_cancion FROM NOMBRES WHERE eliminada_en IS NULL") == [
        ("Ghost of you",)]
    assert consulta(carpeta, "SELECT nombre_cancion FROM NOMBRES WHERE eliminada_en IS NOT NULL") == [
        ("Sound of You",)]
    assert consulta(carpeta, "SELECT linea FROM LETRAS WHERE codigo = 2 AND numero_linea = 1") == [
        ("Primera línea corregida",)]


def test_papelera_restaurar_y_eliminar(carpeta):
    teclas = ["f", "t", "", "", "r",
              "b", "1", "s", "", "b", "2", "s", "",
              "x", "1", "",                 # la 1 está en la papelera: lo dice claramente
              "b", "p", "1", "r", "",       # restaura la última borrada (Ghost of you)
              "1", "e", "s", "", "",        # elimina definitivamente la otra
              "s"]
    salida = ejecutar(carpeta, teclas)
    assert "está en la PAPELERA" in salida
    assert "se restauró con su mismo código (2)" in salida
    assert "Eliminada definitivamente" in salida
    assert consulta(carpeta, "SELECT codigo, eliminada_en FROM NOMBRES") == [(2, None)]


def test_programa_y_modo_manual(carpeta):
    (carpeta / "PROGRAMA.txt").write_text("1. Ghost of you\n2. Sound of you\n", encoding="utf-8")
    teclas = ["f", "t", "", "", "r", "p", "c", "", "", "r",
              "m", ""] + ["c"] * 19 + ["perfect image that I drew", "c", "b", "f", "", "s"]
    salida = ejecutar(carpeta, teclas)
    assert "Siguiente en el PROGRAMA: [2] Ghost of you" in salida
    assert "Terminó «Ghost of you»" in salida
    historial = consulta(carpeta, "SELECT nombre_cancion, completada FROM HISTORIAL ORDER BY id")
    # Completa la del programa; la segunda vez (buscada por palabras) se abandona con "b".
    assert historial == [("Ghost of you", 1), ("Ghost of you", 0)]
    assert consulta(carpeta, "SELECT estado FROM PROGRAMA ORDER BY orden") == [("cantada",), ("pendiente",)]


def test_modo_manual_busca_por_palabras_con_errores(carpeta):
    teclas = ["f", "t", "", "", "r", "m", "folow me everiwere", "", "f", "", "s"]
    salida = ejecutar(carpeta, teclas)
    assert "Sound of You" in salida and "3 de 24" in salida


def test_opcion_invalida_no_rompe_el_programa(carpeta):
    salida = ejecutar(carpeta, ["z", "999", "x", "abc", "", "s"])
    assert "Gracias" in salida


def test_simulacion_automatica_sin_pantalla(tmp_path):
    guion = tmp_path / "guion.txt"
    guion.write_text("0:02 I wake up in the dead of night and you're the first thing\n"
                     "0:08 it hurts so bad a horror lovely sensation\n"
                     "0:14 I close my eyes and I can almost feel your skin\n", encoding="utf-8")
    proceso = subprocess.run(
        [sys.executable, str(RAIZ / "herramientas" / "simular_automatico.py"), "--guion", str(guion),
         "--canciones", str(RAIZ / "ejemplos" / "canciones.txt")],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"), cwd=RAIZ,
    )
    assert proceso.returncode == 0, proceso.stderr
    assert "Canción identificada: Ghost of you" in proceso.stdout
    assert "línea 3" in proceso.stdout


def test_las_canciones_siguen_ahi_al_volver_a_abrir(carpeta):
    """Lo que se carga queda guardado en CANCIONES.db aunque se cierre el programa."""
    ejecutar(carpeta, ["f", "t", "", "", "r", "s"])  # se cargan las canciones y se sale
    salida = ejecutar(carpeta, ["w", "", "s"])        # se vuelve a abrir el programa
    assert "Base de datos CANCIONES encontrada" in salida or "creada" not in salida
    assert "Sound of You" in salida and "Ghost of you" in salida
