"""Sincroniza una letra conocida con la pista: en qué segundo empieza cada línea.

Cuando la letra ya está escrita (el autor la conoce o ya está en la base de
datos) no hace falta que la IA la adivine: basta con que diga **cuándo** se
canta cada palabra. Se alinean las palabras de la letra con las palabras que
la IA escuchó (cada una con su tiempo) con programación dinámica, tolerando
errores de la IA (palabras parecidas), palabras que no oyó y palabras de más.

* Cada línea toma el tiempo de su primera palabra alineada.
* Las líneas sin ninguna palabra alineada se reparten entre sus vecinas
  según su número de palabras (los tiempos siempre van en aumento).

No usa NumPy: sirve igual en Windows y en Android.
"""

from __future__ import annotations

from dataclasses import dataclass

from .texto import palabras as normalizar, semejanza

COINCIDE = 2.0       # palabra igual o muy parecida
PARECIDA = 1.0       # parecida (semejanza >= 0.6)
DISTINTA = -1.0
SALTO_LETRA = -0.7   # palabra de la letra que la IA no oyó
SALTO_IA = -0.5      # palabra que la IA "oyó" de más (ruido, coros)
BONO_SEGUIDA = 0.5   # coincidencia justo después de otra coincidencia


@dataclass
class PalabraConTiempo:
    texto: str
    inicio: float
    fin: float


def _puntaje(a: str, b: str) -> float:
    if a == b:
        return COINCIDE
    s = semejanza(a, b)
    if s >= 0.78:
        return COINCIDE * s
    if s >= 0.6:
        return PARECIDA * s
    return DISTINTA


def alinear_palabras(letra: list[str], oidas: list[str]) -> list[int | None]:
    """Para cada palabra de ``letra`` devuelve el índice de la palabra de
    ``oidas`` con la que se alineó (o ``None``).

    Alineamiento global con dos estados (como Gotoh): las coincidencias
    seguidas reciben un bono, así se prefiere alinear una línea completa y no
    pedazos de dos líneas que empiezan igual ("It seems that you…"). Los
    extremos de lo que oyó la IA son libres: la intro y el final no penalizan.
    """
    n, m = len(letra), len(oidas)
    if not n or not m:
        return [None] * n
    menos = float("-inf")
    # coincide[i][j]: el alineamiento termina emparejando letra[i-1] con oidas[j-1]
    # salto[i][j]: termina con un salto (en la letra o en lo oído)
    coincide = [[menos] * (m + 1) for _ in range(n + 1)]
    salto = [[menos] * (m + 1) for _ in range(n + 1)]
    desde_c = [[0] * (m + 1) for _ in range(n + 1)]   # 1 si coincide[i][j] viene de coincide
    desde_s = [[0] * (m + 1) for _ in range(n + 1)]   # 1/2 arriba (desde coincide/salto), 3/4 izquierda
    salto[0][0] = 0.0
    for j in range(1, m + 1):
        salto[0][j], desde_s[0][j] = 0.0, 4           # la letra puede empezar tarde
    for i in range(1, n + 1):
        salto[i][0], desde_s[i][0] = salto[i - 1][0] + SALTO_LETRA, 2
    for i in range(1, n + 1):
        palabra = letra[i - 1]
        extra = 0.0 if i == n else SALTO_IA            # lo que suena después de la letra es libre
        for j in range(1, m + 1):
            puntaje = _puntaje(palabra, oidas[j - 1])
            seguida = coincide[i - 1][j - 1] + (BONO_SEGUIDA if puntaje > 0 else 0.0)
            suelta = salto[i - 1][j - 1]
            if seguida >= suelta:
                coincide[i][j], desde_c[i][j] = seguida + puntaje, 1
            else:
                coincide[i][j], desde_c[i][j] = suelta + puntaje, 0
            opciones = (
                (coincide[i - 1][j] + SALTO_LETRA, 1),
                (salto[i - 1][j] + SALTO_LETRA, 2),
                (coincide[i][j - 1] + extra, 3),
                (salto[i][j - 1] + extra, 4),
            )
            salto[i][j], desde_s[i][j] = max(opciones)
    resultado: list[int | None] = [None] * n
    i, j = n, m
    estado = "c" if coincide[n][m] >= salto[n][m] else "s"
    while i > 0:
        if estado == "c":
            if _puntaje(letra[i - 1], oidas[j - 1]) > 0:
                resultado[i - 1] = j - 1
            estado = "c" if desde_c[i][j] == 1 else "s"
            i, j = i - 1, j - 1
        else:
            paso = desde_s[i][j]
            if paso in (1, 2):
                i -= 1
            else:
                j -= 1
            estado = "c" if paso in (1, 3) else "s"
    return resultado


def tiempos_de_lineas(lineas: list[str], oidas: list[PalabraConTiempo],
                      duracion: float | None = None) -> list[float]:
    """Segundo en que empieza cada línea de ``lineas`` según las palabras con
    tiempo que escuchó la IA."""
    letra: list[str] = []
    linea_de: list[int] = []
    for numero, linea in enumerate(lineas):
        for palabra in normalizar(linea):
            letra.append(palabra)
            linea_de.append(numero)
    tokens: list[str] = []
    tiempo_de: list[float] = []
    for palabra in oidas:
        partes = normalizar(palabra.texto)
        for k, parte in enumerate(partes):
            tokens.append(parte)
            # una "palabra" de la IA con varias partes reparte su duración
            tiempo_de.append(palabra.inicio + (palabra.fin - palabra.inicio) * k / max(1, len(partes)))
    pareja = alinear_palabras(letra, tokens)

    inicios: list[float | None] = [None] * len(lineas)
    for k, j in enumerate(pareja):
        if j is not None and inicios[linea_de[k]] is None:
            inicios[linea_de[k]] = tiempo_de[j]
    return _completar(inicios, lineas, duracion or (oidas[-1].fin if oidas else 0.0))


def _completar(inicios: list[float | None], lineas: list[str], duracion: float) -> list[float]:
    """Rellena las líneas sin tiempo repartiéndolas entre las conocidas y
    obliga a que los tiempos vayan en aumento."""
    n = len(inicios)
    pesos = [max(1, len(normalizar(l))) for l in lineas]
    conocidos = [i for i, t in enumerate(inicios) if t is not None]
    resultado = list(inicios)
    if not conocidos:
        total = sum(pesos) or 1
        acumulado = 0.0
        for i in range(n):
            resultado[i] = duracion * acumulado / total
            acumulado += pesos[i]
        return [float(t) for t in resultado]
    # Se descartan los tiempos que retroceden (alineamientos dudosos).
    ultimo = -1.0
    for i in conocidos:
        if resultado[i] <= ultimo:
            resultado[i] = None
        else:
            ultimo = resultado[i]
    conocidos = [i for i, t in enumerate(resultado) if t is not None]
    # Antes de la primera conocida: hacia atrás, ~0.45 s por palabra.
    primero = conocidos[0]
    for i in range(primero - 1, -1, -1):
        resultado[i] = max(0.0, resultado[i + 1] - pesos[i] * 0.45)
    # Entre conocidas: proporcional a las palabras.
    for a, b in zip(conocidos, conocidos[1:]):
        hueco = range(a + 1, b)
        if not hueco:
            continue
        total = sum(pesos[a:b])
        acumulado = pesos[a]
        for i in hueco:
            resultado[i] = resultado[a] + (resultado[b] - resultado[a]) * acumulado / total
            acumulado += pesos[i]
    # Después de la última conocida: ~0.45 s por palabra, sin pasar del final.
    ultimo = conocidos[-1]
    for i in range(ultimo + 1, n):
        resultado[i] = min(max(duracion, resultado[i - 1]), resultado[i - 1] + pesos[i - 1] * 0.45)
    return [round(float(t), 2) for t in resultado]


def linea_en(tiempos: list[float], segundo: float, adelanto: float = 0.0) -> int:
    """Índice de la línea que se canta en ``segundo`` (mostrándola
    ``adelanto`` segundos antes). -1 antes de la primera línea."""
    actual = -1
    for numero, inicio in enumerate(tiempos):
        if inicio - adelanto <= segundo:
            actual = numero
        else:
            break
    return actual
