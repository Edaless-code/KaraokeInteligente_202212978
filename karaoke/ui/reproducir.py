"""Opción (r): reproducir una canción de la biblioteca con su letra a tiempo.

La pista suena por las bocinas y la letra cambia sola, cada línea un poco
**antes** de que se cante (``segundos_letra_adelantada``), para poder leerla y
entrar a tiempo aunque no se sepa la canción. En la intro se ve una cuenta
regresiva hasta la primera línea.

La primera vez que se reproduce una canción sin tiempos, la IA escucha la
pista una sola vez y sincroniza la letra (se guarda en la base de datos).

Teclas: espacio pausa · ← → 5 segundos · - + voz del artista (100, 75, 50 o
25 %) · f terminar
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..alineacion import linea_en
from . import consola
from .consola import color
from .pantalla import VistaKaraoke, componer

if TYPE_CHECKING:
    from .menus import Aplicacion

AYUDA = "espacio pausa · ← → 5 segundos · - + voz del artista (100/75/50/25 %) · f terminar"


def _reloj(segundos: float) -> str:
    return f"{int(segundos // 60)}:{int(segundos % 60):02d}"


class ReproducirConLetra:
    def __init__(self, app: Aplicacion):
        self.app = app
        self.bd = app.bd
        self.config = app.config
        self.teclado = app.teclado

    def vincular_ejemplos(self) -> None:
        """Los MP3 de la carpeta ejemplos/ se asocian a su canción (por el
        nombre del archivo) para poder reproducirlos sin configurar nada."""
        from ..audio.desde_audio import FORMATOS, nombre_desde_archivo

        carpeta = self.config.carpeta / "ejemplos"
        if not carpeta.is_dir():
            return
        con_pista = {c for c, _, _ in self.bd.listar_pistas()}
        for ruta in sorted(carpeta.iterdir()):
            if ruta.suffix.lower() not in FORMATOS:
                continue
            encontradas = self.bd.buscar_por_nombre(nombre_desde_archivo(ruta), limite=1)
            if encontradas and encontradas[0][0] not in con_pista:
                self.bd.guardar_pista(encontradas[0][0], ruta.relative_to(self.config.carpeta).as_posix())
                con_pista.add(encontradas[0][0])

    def ejecutar(self) -> None:
        try:
            self.vincular_ejemplos()
        except Exception:  # nunca impide reproducir lo demás
            pass
        consola.limpiar()
        consola.titulo("Reproducir con letra", "karaoke con pista")
        pistas = [(c, n, a) for c, n, a in self.bd.listar_pistas() if (self.config.carpeta / a).exists()]
        if not pistas:
            consola.aviso("  Ninguna canción tiene pista todavía.")
            print(color("  Agréguela con f → m (MP3, WAV, FLAC u OGG); si la canción ya existe solo se "
                        "le asocia la pista.", "tenue"))
            self.teclado.pausa()
            return
        print()
        for numero, (codigo, nombre, _) in enumerate(pistas, 1):
            sincronizada = "" if self.bd.obtener_tiempos(codigo) else color("  (se sincroniza al abrirla)", "tenue")
            print(f"    {color(str(numero), 'negrita', 'cian'):>4}  [{codigo}] {nombre}{sincronizada}")
        print()
        texto = self.app.preguntar("  Número de la canción (Enter = 1): ")
        if texto and not (texto.isdigit() and 1 <= int(texto) <= len(pistas)):
            return
        codigo, _, archivo = pistas[int(texto or 1) - 1]
        cancion = self.bd.obtener_cancion(codigo)
        tiempos = self.bd.obtener_tiempos(codigo) or self._sincronizar(codigo, cancion.lineas, archivo)
        if not tiempos:
            return
        try:
            from ..audio.reproductor import Reproductor

            reproductor = Reproductor(self.config.carpeta / archivo)
            reproductor.iniciar()
        except Exception as ex:
            consola.error(f"  No se pudo reproducir: {ex}")
            self.teclado.pausa()
            return
        consola.entrar_pantalla_completa()
        try:
            self._bucle(reproductor, cancion, tiempos)
        finally:
            reproductor.detener()
            consola.salir_pantalla_completa()

    def _sincronizar(self, codigo: int, lineas: list[str], archivo: str) -> list[float] | None:
        print()
        print("  Sincronizando la letra con la pista (solo la primera vez, alrededor de un minuto)…")

        def progreso(fraccion: float) -> None:
            llenas = int(fraccion * 30)
            print(f"\r  {'━' * llenas}{'─' * (30 - llenas)} {int(fraccion * 100):>3} %", end="", flush=True)

        try:
            from ..audio.desde_audio import sincronizar

            tiempos = sincronizar(self.config.carpeta / archivo, self.config, lineas, progreso)
        except Exception as ex:
            print()
            consola.error(f"  No se pudo sincronizar: {ex}")
            self.teclado.pausa()
            return None
        print()
        self.bd.guardar_tiempos(codigo, tiempos)
        return tiempos

    def _bucle(self, reproductor, cancion, tiempos: list[float]) -> None:
        adelanto = self.config.decimal("automatico", "segundos_letra_adelantada")
        previas = self.config.entero("pantalla", "lineas_previas")
        siguientes = self.config.entero("pantalla", "lineas_siguientes")
        ultima = None
        while True:
            tecla = self.teclado.tecla(0.05)
            if tecla in ("f", "esc", "q"):
                return
            if tecla == " ":
                reproductor.alternar_pausa()
            elif tecla == "izquierda":
                reproductor.mover(-5)
            elif tecla == "derecha":
                reproductor.mover(5)
            elif tecla == "-":
                reproductor.bajar_voz()
            elif tecla in ("+", "="):
                reproductor.subir_voz()
            if reproductor.terminada:
                time.sleep(0.5)
                return
            segundo = reproductor.segundo
            actual = linea_en(tiempos, segundo, adelanto)
            if reproductor.pausado:
                estado, tono = "En pausa · espacio para seguir", "amarillo"
            elif actual < 0:
                faltan = max(0, int(tiempos[0] - adelanto - segundo + 0.99))
                estado, tono = f"Intro · la letra empieza en {faltan} s", "cian"
            else:
                estado, tono = "Reproduciendo", "verde"
            voz = f"voz del artista {int(reproductor.voz * 100)} %"
            if reproductor.voz < 1 and not reproductor.voz_lista:
                voz += " (preparando…)"
            mensaje = f"{_reloj(segundo)} / {_reloj(reproductor.duracion)}   ·   {voz}"
            vista = VistaKaraoke(
                nombre=cancion.nombre, codigo=cancion.codigo, lineas=cancion.lineas,
                actual=max(actual, 0), modo="con pista", estado=estado, tono_estado=tono,
                mensaje=mensaje, ayuda=AYUDA, previas=previas, siguientes=siguientes,
            )
            renglones = componer(vista)
            if renglones != ultima:  # el reloj cambia una vez por segundo; la letra, al cambiar de línea
                consola.redibujar(renglones)
                ultima = renglones
