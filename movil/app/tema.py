"""Sistema de diseño de la app móvil "Escenario".

Una sola fuente de verdad para colores, tipografía, espaciado, radios y
movimiento. Inspirado en los principios de diseño de Apple (respuesta
inmediata, jerarquía por peso y tamaño, tracking según el tamaño, animaciones
críticamente amortiguadas) pero con identidad propia: fondo de "escenario"
oscuro, un acento coral y la letra como protagonista.
"""

from __future__ import annotations

from pathlib import Path

from kivy.core.text import LabelBase
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex as hex_a_color

RECURSOS = Path(__file__).resolve().parent.parent / "recursos"


def color(valor: str, alfa: float | None = None) -> list[float]:
    rgba = list(hex_a_color(valor))
    if alfa is not None:
        rgba[3] = alfa
    return rgba


# ------------------------------------------------------------------ colores
FONDO = color("#0A0A10")          # escenario
SUPERFICIE = color("#15151E")     # tarjetas
SUPERFICIE_ALTA = color("#1D1D29")  # tarjetas elevadas, campos
TRAZO = color("#FFFFFF", 0.07)    # bordes sutiles
VELO = color("#000000", 0.55)     # oscurece al mostrar un diálogo

TEXTO = color("#F5F5F7")
TEXTO_2 = color("#A6A6B3")
TEXTO_3 = color("#6E6E7C")

ACENTO = color("#FF5A5F")         # coral: identidad de la app
ACENTO_SUAVE = color("#FF5A5F", 0.14)
VIOLETA = color("#8B7CFF")        # acento secundario (modo automático)
VIOLETA_SUAVE = color("#8B7CFF", 0.16)
EXITO = color("#34D399")
EXITO_SUAVE = color("#34D399", 0.15)
AVISO = color("#FBBF24")
AVISO_SUAVE = color("#FBBF24", 0.15)
PELIGRO = color("#F87171")
PELIGRO_SUAVE = color("#F87171", 0.15)

# --------------------------------------------------------------- tipografía
FUENTE = "Inter"
FUENTE_MEDIA = "InterMedium"
FUENTE_SEMI = "InterSemiBold"
FUENTE_NEGRITA = "InterBold"
FUENTE_EXTRA = "InterExtraBold"
ICONOS = "Iconos"

# (tamaño, fuente, tracking en "espaciado de letras") por nivel. El tracking
# es negativo en los títulos grandes y neutro en el texto pequeño.
TIPOS = {
    "titulo_grande": (sp(32), FUENTE_EXTRA),
    "titulo": (sp(22), FUENTE_NEGRITA),
    "encabezado": (sp(17), FUENTE_SEMI),
    "cuerpo": (sp(15), FUENTE),
    "cuerpo_medio": (sp(15), FUENTE_MEDIA),
    "nota": (sp(13), FUENTE_MEDIA),
    "mini": (sp(11), FUENTE_SEMI),
    "letra_actual": (sp(30), FUENTE_EXTRA),
    "letra": (sp(20), FUENTE_SEMI),
}

# ---------------------------------------------------------- espacio y forma
ESP = {"xs": dp(4), "s": dp(8), "m": dp(12), "l": dp(16), "xl": dp(24), "xxl": dp(32)}
RADIO_TARJETA = dp(20)
RADIO_BOTON = dp(14)
RADIO_CAMPO = dp(12)
ALTO_BOTON = dp(52)
ALTO_FILA = dp(64)

# ------------------------------------------------------------- movimiento
# Transiciones críticamente amortiguadas (sin rebote): "out_cubic" y
# duraciones cortas. La respuesta al toque es inmediata (al presionar).
DURACION_TOQUE = 0.08
DURACION = 0.26
CURVA = "out_cubic"

# ----------------------------------------------------------------- íconos
ICONO = {
    "account-music": "\U000F0803",
    "alert-circle-outline": "\U000F05D6",
    "arrow-left": "\U000F004D",
    "book-open-variant": "\U000F14F7",
    "bookshelf": "\U000F125F",
    "check": "\U000F012C",
    "check-circle": "\U000F05E0",
    "chevron-left": "\U000F0141",
    "chevron-right": "\U000F0142",
    "clock-outline": "\U000F0150",
    "close": "\U000F0156",
    "cog-outline": "\U000F08BB",
    "content-paste": "\U000F0192",
    "delete-outline": "\U000F09E7",
    "dots-horizontal": "\U000F01D8",
    "download": "\U000F01DA",
    "ear-hearing": "\U000F07C5",
    "file-document-outline": "\U000F09EE",
    "flag-checkered": "\U000F023C",
    "format-list-numbered": "\U000F027B",
    "gesture-tap": "\U000F0741",
    "hand-back-left-outline": "\U000F182C",
    "history": "\U000F02DA",
    "import": "\U000F02FA",
    "information-outline": "\U000F02FD",
    "lightbulb-outline": "\U000F0336",
    "magnify": "\U000F0349",
    "microphone": "\U000F036C",
    "microphone-off": "\U000F036D",
    "music-note": "\U000F0387",
    "music-note-plus": "\U000F0DDE",
    "pause": "\U000F03E4",
    "pencil": "\U000F03EB",
    "play": "\U000F040A",
    "playlist-check": "\U000F05C7",
    "playlist-music": "\U000F0CB8",
    "playlist-remove": "\U000F0413",
    "plus": "\U000F0415",
    "repeat": "\U000F0456",
    "repeat-once": "\U000F0458",
    "replay": "\U000F0459",
    "restart": "\U000F0709",
    "robot-outline": "\U000F167A",
    "skip-next": "\U000F04AD",
    "skip-previous": "\U000F04AE",
    "star-four-points-outline": "\U000F0AE3",
    "text-box-plus-outline": "\U000F0EAB",
    "translate": "\U000F05CA",
    "waveform": "\U000F147D",
}


def registrar_fuentes() -> None:
    fuentes = RECURSOS / "fuentes"
    LabelBase.register(FUENTE, str(fuentes / "Inter-Regular.ttf"),
                       fn_bold=str(fuentes / "Inter-Bold.ttf"))
    LabelBase.register(FUENTE_MEDIA, str(fuentes / "Inter-Medium.ttf"))
    LabelBase.register(FUENTE_SEMI, str(fuentes / "Inter-SemiBold.ttf"))
    LabelBase.register(FUENTE_NEGRITA, str(fuentes / "Inter-Bold.ttf"))
    LabelBase.register(FUENTE_EXTRA, str(fuentes / "Inter-ExtraBold.ttf"))
    LabelBase.register(ICONOS, str(fuentes / "MaterialDesignIcons.ttf"))
