from karaoke.sincronia import LineaDeTiempo, desfase_pantalla


def test_desfase_con_pista_grabada():
    # El análisis va 3 s adelante; la letra se quiere 0.5 s antes de la voz y
    # los motores tardan 1 s: la pantalla va 1.5 s detrás del análisis.
    assert desfase_pantalla(3.0, 0.5, 1.0) == 1.5
    # En vivo (micrófono) no hay adelanto: se muestra lo último.
    assert desfase_pantalla(0.0, 0.5, 1.0) == 0.0


def test_muestra_el_estado_que_corresponde_a_lo_que_suena():
    linea = LineaDeTiempo(desfase=1.5)
    for decimas in range(0, 60):  # 6 s de análisis, la línea cambia cada segundo
        linea.guardar(decimas / 10, decimas // 10)
    assert linea.foto(5.9) == 4  # 5.9 - 1.5 = 4.4 s → línea 4
    assert linea.foto(2.0) == 0
    assert linea.foto(0.5) == 0  # antes del primer momento: la primera foto


def test_las_ordenes_del_operador_se_ven_de_inmediato():
    linea = LineaDeTiempo(desfase=1.5)
    for decimas in range(0, 30):
        linea.guardar(decimas / 10, "vieja")
    linea.reiniciar("nueva")
    assert linea.foto(3.0) == "nueva"
    linea.guardar(3.1, "despues")
    assert linea.foto(3.2) == "nueva"  # lo de después espera su desfase
    assert linea.foto(4.7) == "despues"


def test_no_crece_sin_limite():
    linea = LineaDeTiempo(desfase=1.0, conservar=5.0)
    for decimas in range(0, 2000):
        linea.guardar(decimas / 10, decimas)
    assert len(linea._fotos) <= 60
    assert linea.foto(199.9) == 1989
