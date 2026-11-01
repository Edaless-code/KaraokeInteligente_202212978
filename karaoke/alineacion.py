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
    return sincronia(lineas, oidas, duracion)[0]


def sincronia(lineas: list[str], oidas: list[PalabraConTiempo],
              duracion: float | None = None) -> tuple[list[float], list[bool]]:
    """Como ``tiempos_de_lineas`` y además, por línea, si su tiempo salió
    directo de lo que oyó la IA (True) o se calculó entre sus vecinas."""
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
    directas = [t is not None for t in inicios]
    tiempos = _completar(inicios, lineas, duracion or (oidas[-1].fin if oidas else 0.0))
    return tiempos, directas


def _partes_oidas(oidas: list[PalabraConTiempo]) -> tuple[list[str], list[float], list[float]]:
    """Palabras normalizadas de la IA con su inicio y fin (una palabra con
    varias partes, como "horror-lovely", reparte su duración)."""
    tokens: list[str] = []
    inicios: list[float] = []
    fines: list[float] = []
    for palabra in oidas:
        partes = normalizar(palabra.texto)
        paso = (palabra.fin - palabra.inicio) / max(1, len(partes))
        for k, parte in enumerate(partes):
            tokens.append(parte)
            inicios.append(palabra.inicio + paso * k)
            fines.append(palabra.inicio + paso * (k + 1))
    return tokens, inicios, fines


def _dura(trozo: str) -> float:
    """Duración típica de una palabra cantada, según su largo."""
    return min(0.9, max(0.25, 0.12 + 0.055 * len(trozo)))


def _repartir(trozos: list[str], desde: float, hasta: float) -> list[tuple[float, float]]:
    """Reparte los trozos entre ``desde`` y ``hasta`` según su duración típica
    (si no caben, se comprimen)."""
    duraciones = [_dura(t) for t in trozos]
    total = sum(duraciones) or 1.0
    escala = min(1.0, max(0.0, hasta - desde) / total)
    resultado = []
    t = desde
    for d in duraciones:
        resultado.append((t, t + d * escala))
        t += d * escala
    return resultado


def _compartir(tiempos: list, j: int, antes: list[str], trozo: str) -> float:
    """Cuando unas palabras de la letra no tienen espacio antes de la palabra
    ``j`` (la IA las oyó juntas), toman la primera parte del tiempo de ``j``
    según su largo. Devuelve dónde terminan."""
    inicio, fin = tiempos[j]
    largo = sum(len(t) for t in antes)
    corte = inicio + (fin - inicio) * largo / max(1, largo + len(trozo))
    tiempos[j] = (corte, fin)
    return corte


def tiempos_de_palabras(lineas: list[str], oidas: list[PalabraConTiempo],
                        duracion: float | None = None) -> tuple[list[float], list[list[tuple[float, float]]]]:
    """Inicio de cada línea y, por línea, el (inicio, fin) de cada palabra tal
    como se muestra (cada trozo separado por espacios, con sus signos), para ir
    pintando la letra al ritmo del cantante.

    Las palabras que la IA oyó toman su tiempo; las demás se reparten entre
    sus vecinas según su largo, sin invadir las pausas entre líneas. El inicio
    de cada línea es el de su primera palabra."""
    total = duracion or (oidas[-1].fin if oidas else 0.0)
    base, _ = sincronia(lineas, oidas, total)
    trozos = [linea.split() for linea in lineas]
    letra: list[str] = []
    dueno: list[tuple[int, int]] = []
    for i, fila in enumerate(trozos):
        for j, trozo in enumerate(fila):
            for parte in normalizar(trozo):
                letra.append(parte)
                dueno.append((i, j))
    tokens, ini, fin = _partes_oidas(oidas)
    pareja = alinear_palabras(letra, tokens)
    oido: dict[tuple[int, int], list[float]] = {}
    for k, j in enumerate(pareja):
        if j is None:
            continue
        actual = oido.setdefault(dueno[k], [ini[j], fin[j]])
        actual[0], actual[1] = min(actual[0], ini[j]), max(actual[1], fin[j])
    # Se descartan los tiempos que retroceden (alineamientos dudosos).
    ultimo = -1.0
    for i, fila in enumerate(trozos):
        for j in range(len(fila)):
            t = oido.get((i, j))
            if t is None:
                continue
            if t[0] <= ultimo:
                del oido[(i, j)]
            else:
                ultimo = t[0]

    resultado: list[list[tuple[float, float]]] = []
    fin_anterior = 0.0
    for i, fila in enumerate(trozos):
        siguiente = base[i + 1] if i + 1 < len(base) else max(total, base[i] + 4.0)
        conocidas = [j for j in range(len(fila)) if (i, j) in oido]
        tiempos: list[tuple[float, float] | None] = [None] * len(fila)
        if not fila:
            resultado.append([])
            continue
        if not conocidas:
            inicio = max(base[i], fin_anterior)
            tiempos = list(_repartir(fila, inicio, max(inicio, siguiente - 0.2)))
        else:
            for j in conocidas:
                tiempos[j] = tuple(oido[(i, j)])
            # Antes de la primera conocida: hacia atrás, sin pisar la línea anterior.
            primera = conocidas[0]
            if primera:
                hasta = tiempos[primera][0]
                desde = max(fin_anterior, hasta - sum(_dura(t) for t in fila[:primera]))
                if hasta - desde < 0.1 * primera:  # sin espacio: comparten la palabra oída
                    desde, hasta = hasta, _compartir(tiempos, primera, fila[:primera], fila[primera])
                tiempos[:primera] = _repartir(fila[:primera], desde, hasta)
            # Entre conocidas: se reparten en el hueco.
            for a, b in zip(conocidas, conocidas[1:]):
                if b - a > 1:
                    desde, hasta = tiempos[a][1], tiempos[b][0]
                    if hasta - desde < 0.1 * (b - a - 1):  # p. ej. "every thing" / "everything"
                        desde, hasta = hasta, _compartir(tiempos, b, fila[a + 1:b], fila[b])
                    tiempos[a + 1:b] = _repartir(fila[a + 1:b], desde, hasta)
            # Después de la última conocida: hacia adelante, sin pasar de la siguiente línea.
            ultima = conocidas[-1]
            if ultima < len(fila) - 1:
                desde = tiempos[ultima][1]
                hasta = min(siguiente - 0.1, desde + sum(_dura(t) for t in fila[ultima + 1:]))
                tiempos[ultima + 1:] = _repartir(fila[ultima + 1:], desde, max(desde, hasta))
        # Cada palabra termina antes de que empiece la siguiente (y dura algo).
        limpias: list[tuple[float, float]] = []
        for j, (a, b) in enumerate(tiempos):
            a = max(a, fin_anterior if j == 0 else limpias[-1][0] + 0.01)
            tope = tiempos[j + 1][0] if j + 1 < len(tiempos) else min(siguiente, a + 3.0)
            b = min(max(b, a + 0.08), max(tope, a + 0.08))
            limpias.append((round(a, 2), round(b, 2)))
        resultado.append(limpias)
        fin_anterior = limpias[-1][1]
    inicios = [fila[0][0] if fila else base[i] for i, fila in enumerate(resultado)]
    for i in range(1, len(inicios)):  # siempre en aumento
        inicios[i] = max(inicios[i], inicios[i - 1])
    return [round(t, 2) for t in inicios], resultado


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
