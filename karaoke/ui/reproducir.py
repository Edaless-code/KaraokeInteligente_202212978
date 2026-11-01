"""Opción (r): reproducir una canción de la biblioteca con su letra a tiempo.

La pista suena por las bocinas y la letra cambia sola, cada línea justo
cuando se canta (``segundos_letra_adelantada`` la puede adelantar); la línea
siguiente ya se ve debajo para leerla y entrar a tiempo. En la intro se ve una cuenta
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
        from ..pistas import vincular_ejemplos

        vincular_ejemplos(self.bd, self.config)

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
        self.reproducir(codigo, archivo)

    def pista_de(self, codigo: int) -> str | None:
        """Archivo de la pista de la canción (si tiene y existe)."""
        for c, _, archivo in self.bd.listar_pistas():
            if c == codigo and (self.config.carpeta / archivo).exists():
                return archivo
        return None

    def reproducir(self, codigo: int, archivo: str, desde: float | None = None,
                   voz: float = 1.0, mensaje: str = "",
                   entrada: tuple[int, float, float] | None = None) -> None:
        """Reproduce la pista con su letra. ``desde`` (o ``entrada``: línea,
        fracción cantada y latencia) permite entrar a media canción: el modo
        automático la arranca donde va el cantante. En ese caso, si la canción
        aún no tiene tiempos, no se espera a la IA: empieza con tiempos
        aproximados y la IA los afina mientras suena."""
        cancion = self.bd.obtener_cancion(codigo)
        tiempos = self.bd.obtener_tiempos(codigo)
        if tiempos and len(tiempos) != len(cancion.lineas):
            tiempos = None
        en_vivo = desde is not None or entrada is not None
        if not tiempos and not en_vivo:
            tiempos = self._sincronizar(codigo, cancion.lineas, archivo)
            if not tiempos:
                return
        try:
            from ..audio.reproductor import Reproductor

            reproductor = Reproductor(self.config.carpeta / archivo)
        except Exception as ex:
            consola.error(f"  No se pudo reproducir: {ex}")
            self.teclado.pausa()
            return
        estado = {"tiempos": tiempos, "nuevos": None, "afinando": False}
        if not tiempos:
            from ..alineacion import tiempos_de_lineas

            estado["tiempos"] = tiempos_de_lineas(cancion.lineas, [], reproductor.duracion)
            self._sincronizar_en_segundo_plano(cancion.lineas, archivo, estado)
        if entrada is not None:
            from ..pistas import punto_de_entrada

            desde = punto_de_entrada(estado["tiempos"], *entrada)
        try:
            reproductor.ajustar_voz(voz)
            reproductor.iniciar(desde or 0.0)
        except Exception as ex:
            consola.error(f"  No se pudo reproducir: {ex}")
            self.teclado.pausa()
            return
        consola.entrar_pantalla_completa()
        try:
            self._bucle(reproductor, cancion, estado, mensaje)
        finally:
            reproductor.detener()
            consola.salir_pantalla_completa()

    def _sincronizar_en_segundo_plano(self, lineas: list[str], archivo: str, estado: dict) -> None:
        """Whisper escucha la pista en otro hilo; los tiempos nuevos se guardan
        desde el bucle principal (la base de datos no se comparte entre hilos)."""
        try:
            from ..audio.proceso import whisper_disponible

            if not whisper_disponible():
                return
        except Exception:
            return
        import threading

        def trabajar() -> None:
            estado["afinando"] = True
            try:
                from ..audio.desde_audio import sincronizar

                estado["nuevos"] = sincronizar(self.config.carpeta / archivo, self.config, lineas)
            except Exception:
                pass
            finally:
                estado["afinando"] = False

        threading.Thread(target=trabajar, daemon=True).start()

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

    def _bucle(self, reproductor, cancion, sincronia, aviso: str = "") -> None:
        if not isinstance(sincronia, dict):
            sincronia = {"tiempos": sincronia, "nuevos": None, "afinando": False}
        adelanto = self.config.decimal("automatico", "segundos_letra_adelantada")
        previas = self.config.entero("pantalla", "lineas_previas")
        siguientes = self.config.entero("pantalla", "lineas_siguientes")
        ultima = None
        inicio = time.monotonic()
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
            if sincronia.get("nuevos"):
                # la IA terminó de sincronizar: la letra pasa a ir junto con la voz
                self.bd.guardar_tiempos(cancion.codigo, sincronia["nuevos"])
                sincronia["tiempos"], sincronia["nuevos"] = sincronia["nuevos"], None
                aviso, inicio = "La IA sincronizó la letra con la voz", time.monotonic()
            tiempos = sincronia["tiempos"]
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
            if sincronia.get("afinando"):
                mensaje += "   ·   la IA está sincronizando la letra…"
            if aviso and time.monotonic() - inicio < 6:  # el aviso se ve los primeros segundos
                mensaje = f"{aviso}   ·   {mensaje}"
            vista = VistaKaraoke(
                nombre=cancion.nombre, codigo=cancion.codigo, lineas=cancion.lineas,
                actual=max(actual, 0), modo="con pista", estado=estado, tono_estado=tono,
                mensaje=mensaje, ayuda=AYUDA, previas=previas, siguientes=siguientes,
            )
            renglones = componer(vista)
            if renglones != ultima:  # el reloj cambia una vez por segundo; la letra, al cambiar de línea
                consola.redibujar(renglones)
                ultima = renglones
