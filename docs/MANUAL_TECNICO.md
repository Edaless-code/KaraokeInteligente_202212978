# Manual técnico · Karaoke Inteligente

**Autor:** Edgar Alessandro Chocon Oliva · **Carné:** 202212978 · **Versión:** 1.0.0 · **Lenguaje:** Python 3.11+ · **Base de datos:** SQLite

Este documento explica cómo está construido el programa y cómo se resolvió el modo automático. También reúne **todo lo necesario para que el docente lo ponga a funcionar** y las **suposiciones** que se hicieron donde la especificación dejaba decisiones abiertas.

---

## Contenido

1. [Puesta en marcha para el docente](#1-puesta-en-marcha-para-el-docente)
2. [Arquitectura y módulos](#2-arquitectura-y-módulos)
3. [Base de datos CANCIONES](#3-base-de-datos-canciones)
4. [Búsqueda de canciones por palabras](#4-búsqueda-de-canciones-por-palabras)
5. [Modo automático: cómo se resolvió](#5-modo-automático-cómo-se-resolvió)
6. [Limpieza del sonido](#6-limpieza-del-sonido)
7. [Evaluación con canciones reales](#7-evaluación-con-canciones-reales)
8. [Configuración (`karaoke.ini`)](#8-configuración-karaokeini)
9. [Pruebas automatizadas e integración continua](#9-pruebas-automatizadas-e-integración-continua)
10. [Construcción del ejecutable de Windows](#10-construcción-del-ejecutable-de-windows)
11. [Versión para Android](#11-versión-para-android)
12. [Suposiciones y decisiones de diseño](#12-suposiciones-y-decisiones-de-diseño)
13. [Limitaciones conocidas y mejoras futuras](#13-limitaciones-conocidas-y-mejoras-futuras)
14. [Seguridad](#14-seguridad)
15. [Escalabilidad y versiones futuras](#15-escalabilidad-y-versiones-futuras)
16. [Derechos de autor de las canciones de ejemplo](#derechos-de-autor-de-las-canciones-de-ejemplo)

---

## 1. Puesta en marcha para el docente

### Windows con el ejecutable (sin instalar nada)

1. Descargue `KaraokeInteligente-Windows.zip`, de *Releases* o de *Actions → Ejecutable de Windows → Artifacts*, y extráigalo.
2. Ejecute `KaraokeInteligente.exe`. Los modelos de voz ya vienen en la carpeta `modelo\`.
3. En el menú, escriba `f` → `t` → Enter → Enter para cargar las canciones de ejemplo. Después `m` (manual) o `a` (automático).
4. Para comprobar el modo automático **sin micrófono**, ejecute en PowerShell, dentro de la carpeta del programa:

   ```powershell
   .\KaraokeInteligente.exe --simular ejemplos\Ghost_of_you_Remastered.mp3
   ```

   Imprime con su tiempo cada decisión de la IA: canción identificada, cambios de línea, pausas y fin.

### Desde el código fuente (Windows, Linux o macOS)

```bash
git clone https://github.com/Edaless-code/KaraokeInteligente_202212978.git
cd KaraokeInteligente_202212978
pip install -r requirements.txt
pip install faster-whisper          # opcional, mejora el modo automático
python main.py                      # programa interactivo
python -m pytest                    # 147 pruebas automatizadas
```

Los modelos de Vosk se descargan desde el propio programa la primera vez: el modo automático lo ofrece y también la opción *d*. También se pueden copiar a mano en `modelo/`:

| Idioma | Modelo | Tamaño |
|---|---|---|
| Español | [`vosk-model-small-es-0.42`](https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip) | 39 MB |
| Inglés | [`vosk-model-small-en-us-0.15`](https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip) | 40 MB |
| Whisper base | `Systran/faster-whisper-base` | 145 MB, se descarga solo |

### Dependencias

| Paquete | Uso |
|---|---|
| `numpy` | Procesamiento de la señal (STFT, filtros, ganancia) |
| `sounddevice` | Micrófono y bocinas (PortAudio) |
| `miniaudio` | Lectura de MP3, WAV, FLAC y OGG sin ffmpeg |
| `vosk` | Reconocimiento de voz sin internet, en tiempo real |
| `faster-whisper` *(opcional)* | Whisper optimizado para CPU |

`sqlite3`, `argparse`, `configparser`, `difflib`, `threading` y `wave` vienen con Python.

---

## 2. Arquitectura y módulos

El programa está en capas. El núcleo (datos, búsqueda y lógica del karaoke) **no depende de la interfaz**, de modo que la misma lógica la usan la consola de Windows, la herramienta sin pantalla y la versión de Android.

```
                    ┌───────────────────────────────────────────┐
  Interfaz          │ ui/menus.py   ui/modo_manual.py           │
  (consola)         │ ui/modo_automatico.py   ui/diagnostico.py │
                    │ ui/pantalla.py   ui/consola.py            │
                    └──────────────┬────────────────────────────┘
                                   │
  Lógica del        ┌──────────────▼────────────────────────────┐
  karaoke           │ sesion.py   programa.py   automatico.py   │
                    │ seguimiento.py   buscador.py              │
                    └──────────────┬────────────────────────────┘
                                   │
  Datos y audio     ┌──────────────▼──────────────┐ ┌────────────────────────────┐
                    │ db.py   importador.py        │ │ audio/fuentes.py           │
                    │ texto.py   config.py         │ │ audio/limpieza.py          │
                    └──────────────────────────────┘ │ audio/motores.py           │
                                                     │ audio/modelos.py           │
                                                     │ audio/proceso.py           │
                                                     └────────────────────────────┘
```

| Módulo | Responsabilidad |
|---|---|
| `main.py`, `karaoke/app.py` | Arranque: lee la configuración, detecta o crea la base de datos y abre el menú. Opciones `--carpeta`, `--simular` y `--version` |
| `karaoke/config.py` | Lee y crea `karaoke.ini`. Todos los parámetros ajustables con sus valores por omisión |
| `karaoke/texto.py` | Normalización (minúsculas, sin tildes, conserva la ñ), semejanza de palabras, división de líneas largas, lectura de archivos UTF-8/ANSI, etiquetas de sección, idioma y vocabulario para el reconocedor |
| `karaoke/db.py` | Acceso a SQLite: esquema, canciones, tablas temporales, programa, sesiones e historial |
| `karaoke/importador.py` | Opción *f → t*: lee el archivo de canciones en sus dos formatos |
| `karaoke/buscador.py` | Índice en memoria y alineamiento Smith-Waterman tolerante a errores (sección 4) |
| `karaoke/programa.py` | Archivo PROGRAMA y cursor de orden flexible |
| `karaoke/sesion.py` | Canción en curso y sesión (c, i, r, g, s, a), común a los dos modos |
| `karaoke/seguimiento.py` | `Seguidor`: posición del cantante dentro de la letra (sección 5.4) |
| `karaoke/automatico.py` | `ControladorAutomatico`: máquina de estados del modo automático (sección 5.3) |
| `karaoke/simulacion.py` | Modo automático sin pantalla (`--simular`) para pruebas y demostraciones |
| `karaoke/audio/fuentes.py` | Micrófono (`sounddevice`) y archivos de audio (`miniaudio`) al ritmo real |
| `karaoke/audio/limpieza.py` | Filtro pasa banda, sustracción espectral, detector de voz, AGC y aislamiento de voz estéreo |
| `karaoke/audio/motores.py` | `MotorVosk`, `MotorWhisper` y `MotorSimulado` con una misma interfaz |
| `karaoke/audio/modelos.py` | Ubicación, validación y descarga de los modelos de Vosk |
| `karaoke/audio/proceso.py` | Cadena fuente → limpieza → motores en un hilo aparte |
| `karaoke/audio/desde_audio.py` | *f → m*: transcribe una pista completa con Whisper (Vosk si no está), la convierte en líneas (descarta alucinaciones, separa oraciones, corta bucles de la IA, oculta groserías) y copia la pista a `pistas/` |
| `karaoke/alineacion.py` | Alinea una letra conocida con las palabras (y tiempos) que oyó la IA: alineamiento global de dos estados con bono a coincidencias seguidas; da el segundo de inicio de cada línea |
| `karaoke/audio/reproductor.py` | Reproduce la pista con un reloj que descuenta la latencia de la tarjeta y baja la voz del artista (resta lo que es igual en ambos canales, por frecuencia, en 180–5000 Hz) |
| `karaoke/ui/reproducir.py` | Opción *r*: letra a tiempo con la pista (junto con la voz; `segundos_letra_adelantada` la puede adelantar) |
| `karaoke/sincronia.py` | Línea de tiempo que muestra la letra adelantada a la voz cuando la pista suena por las bocinas |
| `karaoke/ui/*` | Menús, pantalla del karaoke (diseño fijo en pantalla alterna, redibujo solo al cambiar), modos manual y automático, agregar desde audio, diagnóstico de audio |
| `herramientas/transcribir.py` | Mide la transcripción de un audio con cada motor (sección 7) |
| `herramientas/simular_automatico.py` | Atajo para `karaoke/simulacion.py` |

**Concurrencia.** El audio se captura, se limpia y se transcribe en un hilo aparte (`ProcesadorAudio`), que deja los resultados en una cola. El hilo principal lee la cola, aplica las decisiones, atiende el teclado y redibuja la pantalla. **Todas las escrituras a la base de datos ocurren en el hilo principal**, así que no hay condiciones de carrera sobre SQLite. Whisper, que es más lento, trabaja en su propio hilo con una cola de una sola ventana: si sigue ocupado, se descarta la ventana y la pantalla no se retrasa.

---

## 3. Base de datos CANCIONES

Archivo: **`CANCIONES.db`**, junto al programa. El nombre se configura en `[base_datos] archivo`.

**Detección.** Al arrancar se revisa si el archivo existe y no está vacío.
- **No existe:** se crean todas las tablas (`CREATE TABLE IF NOT EXISTS`).
- **Existe:** se prepara para usarla: se activan las claves foráneas, se crean las tablas que falten (por ejemplo, si viene de otra versión), se ejecuta `PRAGMA quick_check` y se cierran las sesiones que quedaron abiertas por un cierre inesperado.

### Tablas de la especificación (con campos agregados)

**`NOMBRES`**

| Campo | Tipo | Descripción |
|---|---|---|
| `codigo` | INTEGER PK AUTOINCREMENT | Código de la canción, **generado automáticamente**. `AUTOINCREMENT` garantiza que nunca se reutiliza un código borrado |
| `nombre_cancion` | TEXT | Nombre tal como se escribió |
| `nombre_normalizado` | TEXT UNIQUE | *(agregado)* Nombre sin tildes ni mayúsculas, para evitar duplicados ("Canción" = "cancion") |
| `artista` | TEXT | *(agregado)* Opcional |
| `idioma` | TEXT | *(agregado)* `es` o `en`, detectado de la letra; elige el modelo de voz |
| `origen` | TEXT | *(agregado)* `archivo`, `manual` o `automatico` |
| `fecha_registro` | TEXT | *(agregado)* |
| `veces_cantada` | INTEGER | *(agregado)* Cuenta las interpretaciones completas |
| `eliminada_en` | TEXT, nulo | *(agregado, esquema v2)* Fecha en que se movió a la **papelera**. `NULL` = canción activa |

**`LETRAS`**

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | *(agregado)* |
| `codigo` | INTEGER FK → `NOMBRES` **ON DELETE CASCADE** | Enlaza la línea con su canción. Al borrar la canción se borra toda su letra |
| `numero_linea` | INTEGER | *(agregado)* Orden de la línea. `UNIQUE(codigo, numero_linea)` |
| `linea` | TEXT | La línea de la letra |
| `linea_normalizada` | TEXT | *(agregado)* La línea normalizada, para buscar |

### Tablas agregadas

| Tabla | Campos | Para qué |
|---|---|---|
| `TEMP_NOMBRES` | `id_temporal`, `nombre_sugerido`, `fecha_registro`, `motor`, `estado` | Canciones **aprendidas** por el modo automático que aún no se revisan |
| `TEMP_LETRAS` | `id`, `id_temporal` (FK, cascada), `numero_linea`, `linea`, `confianza` | Letra transcrita de esas canciones |
| `PISTAS` | `codigo` (PK y FK, cascada), `archivo`, `fecha_registro` | Pista de audio de cada canción agregada con *f → m*; la ruta es relativa a la carpeta del programa (`pistas/…`) |
| `TIEMPOS` | `codigo` (FK, cascada), `numero_linea`, `inicio` | Segundo en que empieza cada línea en la pista (versión 4); se borra si cambia la letra |
| `PROGRAMA` | `orden`, `nombre_solicitado`, `codigo` (FK, `ON DELETE SET NULL`), `estado` | Programa del cantante: `pendiente`, `cantada` o `saltada` |
| `SESIONES` | `id_sesion`, `modo`, `inicio`, `fin` | Cada sesión de karaoke |
| `HISTORIAL` | `id`, `id_sesion`, `codigo`, `nombre_cancion`, `modo`, `inicio`, `fin`, `lineas_mostradas`, `completada` | Cada interpretación, para la opción *h* |
| `METADATOS` | `clave`, `valor` | Versión del esquema (actualmente **4**: la 2 agregó la papelera, la 3 la tabla `PISTAS` y la 4 la tabla `TIEMPOS` y las columnas `favorita`, `genero` y `portada` de `NOMBRES`; antes de migrar se respalda la base) y fecha de creación |

### Papelera

Borrar una canción **no la elimina de inmediato**: `borrar_cancion()` llena `NOMBRES.eliminada_en` (borrado lógico) y la letra se conserva.

- Todas las consultas de uso normal filtran `eliminada_en IS NULL`: lista, búsqueda, índice del buscador, programa y estadísticas.
- `restaurar_cancion()` la devuelve **con el mismo código**.
- `eliminar_definitivamente()` la borra de verdad. Por `ON DELETE CASCADE`, se va también su letra.
- `vaciar_papelera(mas_de_dias)` elimina lo que lleva más de `dias_papelera` días (30 por omisión). Se ejecuta al abrir el programa.
- El nombre de una canción en la papelera **no se puede reutilizar** (excepción `CancionEnPapelera`), para no perder la posibilidad de restaurarla. El usuario decide si la restaura o la elimina.

> **Tablas temporales.** Son tablas **permanentes de "pendientes"**, no `CREATE TEMP TABLE` de SQLite. Una tabla TEMP desaparece al cerrar la conexión, y la especificación pide poder **corregir la letra y averiguar el nombre después**, quizás en otra sesión. La revisión se hace en *f → v*, y `promover_temporal()` las pasa a `NOMBRES`/`LETRAS`.

**Nombres de los campos.** Se usaron sin tildes (`codigo`, `nombre_cancion`, `linea`). SQLite acepta tildes en los identificadores, pero muchas herramientas y controladores fallan con ellas.

---

## 4. Búsqueda de canciones por palabras

`Buscador` (`karaoke/buscador.py`) resuelve "con dos o tres palabras, ¿qué canción es y en qué línea va?". Lo usan el modo manual, con lo que escribe el operador, y el automático, con lo que transcribe la IA.

1. **Índice en memoria.** Al arrancar y cada vez que la base cambia, se carga cada letra como una secuencia de palabras normalizadas, junto con la línea a la que pertenece cada palabra. Se mantiene un índice invertido palabra → canciones.
2. **Peso de cada palabra (tipo IDF).** Una palabra que aparece en muchas líneas ("la", "de", "the", "you") pesa poco. Una poco frecuente ("contrabando", "everywhere") pesa mucho: `peso = clamp(log(1 + N/df)/2, 0.35, 2.0)`.
3. **Tolerancia a errores.** Dos palabras coinciden si su semejanza (`difflib.SequenceMatcher`) es al menos `semejanza_palabra` (0.78). Así "negos" coincide con "negros" y "everiwere" con "everywhere".
4. **Candidatas.** Solo se alinean las canciones que comparten al menos el 25 % del peso de la consulta (como máximo 60).
5. **Alineamiento local Smith-Waterman** entre la consulta y la letra completa:
   - coincidencia: `+peso × semejanza`; palabra diferente: `−peso`;
   - palabra de la letra que no se escuchó: `−0.15 × peso medio`;
   - palabra escuchada que no está en la letra: `−0.5 × peso`.

   Respeta el **orden** de las palabras pero permite huecos, así que una palabra mal escuchada no impide encontrar la canción. Se recorre la consulta contra la letra completa, de modo que también encuentra frases **que cruzan dos líneas**.
6. **Resultado:** puntaje de 0 a 1 (peso alineado entre peso total), línea de inicio y de fin, posición de la siguiente palabra y **evidencia** (peso bruto alineado).
7. **Identificación segura** (`identificar`). Se acepta una canción solo si:
   - el puntaje es al menos `puntaje_minimo` (0.55);
   - la evidencia es al menos `evidencia_minima` (2.5, unas tres palabras significativas), para que "the" o "la" solas no identifiquen nada;
   - le saca un margen de 0.08 a la segunda canción.

   La **siguiente canción del PROGRAMA** recibe un bono de 0.12 que se usa para ordenar y desempatar.

---

## 5. Modo automático: cómo se resolvió

### 5.1 Elección del reconocedor de voz

Se compararon varias opciones gratuitas, todas sin internet:

| Opción | Ventajas | Desventajas | Decisión |
|---|---|---|---|
| **Vosk (Kaldi)** | Tiempo real con **resultados parciales** mientras se canta. Modelos de 40 MB. **Vocabulario restringible** en tiempo de ejecución. Existe para Windows, Linux y **Android** | Con música mezclada reconoce poco | ✅ Seguimiento línea por línea |
| **Whisper (faster-whisper)** | Entiende muy bien la voz **con música de fondo**. Detecta el idioma, incluso en canciones bilingües | Trabaja por ventanas de segundos, sin resultados parciales; modelo de 145 MB | ✅ Identificación y anclas de posición |
| Windows Speech (SAPI) | Viene en Windows | Dictado de baja calidad, sin control del vocabulario, solo Windows | ❌ |
| APIs en la nube | Alta precisión | Requieren internet y cuenta; costo | ❌ |

**Diseño híbrido.** Whisper identifica la canción y cada pocos segundos confirma en qué parte va. Vosk, con el vocabulario restringido a la letra, sigue palabra por palabra en tiempo real. Si Whisper no está instalado, todo funciona solo con Vosk. Se elige en `[audio] motor = hibrido | vosk | whisper | simulado`.

### 5.2 Cadena de procesamiento

```
micrófono / archivo ─► limpieza del sonido ─┬─► Vosk canal LIBRE (es, en) ──────────┐
   (16 kHz mono)       (sección 6)          ├─► Vosk canal RESTRINGIDO a la letra ──┼─► ControladorAutomatico ─► pantalla
                       + detector de voz    └─► Whisper (ventanas de 6 s) ──────────┘         ▲
                                                                                    teclado (correcciones)
```

**Vosk con dos canales sobre el mismo audio:**
- **Libre:** reconoce cualquier palabra del idioma. Sirve para identificar y para aprender canciones nuevas.
- **Restringido:** cuando ya se sabe qué canción es, se crea un reconocedor con una **gramática que contiene solo las palabras de esa letra**, más `[unk]` para todo lo demás. La voz cantada se reconoce mucho peor que la hablada, y limitar el vocabulario a unas decenas de palabras hace que lo reconocido casi siempre sea de la letra. Las palabras se pasan **con tildes**, porque así las conoce el modelo, y para el inglés se agregan las contracciones ("dont" → "don't").

### 5.2.0 Idiomas

`proceso.idiomas_escucha` une los idiomas de `[audio] idiomas_automatico` (por omisión `es,en`) con los de las canciones de la base, y `crear_motores` carga un canal libre de Vosk por cada uno. Antes solo se usaban los de las canciones, y con una biblioteca en inglés no se entendía a quien cantaba en español. El controlador lleva la cuenta de cada canal por idioma (`libre:es`, `libre:en`) para que los parciales de un idioma no corten ni repitan las palabras del otro. Sin Whisper, para aprender una canción nueva confía en el idioma con más confianza media de Vosk. Whisper, con idioma "auto", detecta el idioma de la ventana y `motores.elegir_idioma` lo limita a esos idiomas: si la probabilidad del más probable es menor a 0.65 entre ellos, usa el preferido (el primero). Si el detectado no es el elegido, vuelve a transcribir la ventana en el idioma elegido.

### 5.2.1 Entrada de la pista al reconocer la canción

Con el micrófono, en cuanto el controlador pasa a SIGUIENDO con una canción que tiene pista y tiempos, `ControladorAutomatico.posicion_cantada()` devuelve la línea y la fracción ya cantada. `karaoke.pistas.punto_de_entrada(tiempos, linea, fraccion, latencia)` lo convierte en el segundo de la pista: el inicio de la línea, más la fracción de su duración, más la latencia del reconocimiento. Entonces se detiene la escucha y se reproduce la pista desde ese segundo, con la voz del artista en `voz_pista_al_reconocer` (0.25 por defecto). Así lo hacen la consola (`ModoAutomatico.revisar_entrada_pista`), la interfaz Kivy (`Escenario._entrar_con_pista`) y la web (`entrarConPista`). Los tiempos de las canciones de ejemplo vienen en `ejemplos/tiempos.json`, que calcula `herramientas/tiempos_ejemplos.py` y que `vincular_ejemplos` carga en la tabla TIEMPOS.

### 5.3 Máquina de estados (`ControladorAutomatico`)

```
             identifica (evidencia suficiente)
 ESPERANDO ─────────────────────────────────────► SIGUIENDO ◄────┐
    │  ▲                                           │    │        │ vuelve la voz
    │  │ terminó la canción / x                    │    │ 6 s sin voz y letra
    │  └───────────────────────────────────────────┘    ▼        │
    │ ≥14 palabras sin identificar                       PAUSA ───┘
    ▼
 APRENDIENDO ── 8 s de silencio o t ──► guarda en TEMP_* con nombre sugerido ──► ESPERANDO
 (en cualquier estado)  g ─► IGNORANDO ─ s ─► estado anterior      f ─► FIN
```

Así se automatizan las acciones del modo manual:

| Manual | Automático |
|---|---|
| Teclear 2-3 palabras | Se juntan las últimas palabras del canal libre y de Whisper (unos 20 s) y se identifica en cuanto hay evidencia suficiente, con bono para la siguiente del PROGRAMA y un bono menor para repetir la última |
| **c** continuar | El `Seguidor` avanza cuando se cantó el 70 % de la línea |
| **i** igual | El `Seguidor` detecta que las palabras volvieron al inicio de la misma línea |
| **r** repetir | Se detecta el inicio de la canción después de haber avanzado. Si la canción terminó, el bono de "última cantada" la identifica de nuevo |
| **g** ignorar / **s** seguir | Pausa automática tras `segundos_silencio_pausa` sin palabras reconocidas, y reanudación en cuanto la letra vuelve a coincidir |
| **f** finalizar | Tecla **f**, o silencio prolongado si `segundos_silencio_fin_sesion > 0` |
| Elegir del PROGRAMA | Bono de prioridad; tecla **n** para forzarla. La canción cantada se marca aunque se rompa el orden |
| *(nuevo)* Canción desconocida | Estado **APRENDIENDO** (sección 5.5) |

Si la letra deja de coincidir durante más de 8 s y una frase larga pertenece con claridad a **otra canción**, se cambia a esa canción: el cantante cambió de canción.

### 5.4 Sincronización con el cantante (`Seguidor`)

El `Seguidor` mantiene la **posición** (la siguiente palabra a cantar) y la **línea mostrada**:

1. **Alineamiento local que termina en la última palabra escuchada.** Las últimas 8 palabras reconocidas se alinean contra una ventana: la línea anterior, la actual y las dos siguientes. Se exige que el alineamiento termine en la palabra más reciente, porque al seguir a un cantante importa dónde está *ahora* y no la coincidencia más larga del pasado. Se encontró con *Sound of You*: sus líneas 3 y 4 empiezan con "It seems that you…", y sin esa condición el seguidor saltaba a la línea equivocada.
2. **Avance anticipado.** Se muestra la siguiente línea cuando ya se cantó el 70 % de la actual (`avance_linea`), para que el público la lea a tiempo.
3. **Repeticiones.** Si las palabras regresan al inicio de la línea actual o anterior, es una línea **igual**. Si regresan al inicio de la canción después de la línea 2, es una **repetición**.
4. **Cambios de estructura.** Si la ventana no coincide pero 4 o más palabras coinciden con claridad en otra parte de la canción (evidencia ≥ 3.2), se **salta** allí. Cubre coros repetidos de más, estrofas saltadas u otro orden.
5. **Predicción por tempo.** Se aprende cuántos segundos dura cada palabra para *este* cantante, con promedio móvil y solo con avances confirmados. Si hay voz y se reconocen palabras pero la letra no coincide durante más de `1.4 × duración esperada + 1 s`, se avanza una línea. El máximo es de **2 líneas seguidas sin confirmación**, para que la pantalla no se quede congelada ni se escape sola.
6. **Anclas de Whisper.** Las frases largas, de más de 6 palabras, llegan con unos segundos de retraso. Se alinean en una ventana más amplia y el retraso se compensa con el tempo estimado: `palabras = retraso / segundos_por_palabra`.
7. **Variaciones entre canciones.**
   - **Tono:** voces graves, agudas o en falsete. Lo cubren los modelos de voz, que se entrenaron con muchas voces, y el control de ganancia.
   - **Tempo:** se aprende de cada cantante.
   - **Improvisaciones** ("oh yeah"): se ignoran porque no alinean con la letra.
   - **Partes instrumentales:** no se predice si no se reconocen palabras, porque con música mezclada el detector de energía solo no basta.

8. **Letra adelantada a la voz con pistas grabadas (`karaoke/sincronia.py`).** Los motores reconocen una palabra después de oírla (Vosk ~1 s, Whisper varios segundos), así que mostrar la letra al reconocerla haría que la voz siempre fuera adelantada. Con un archivo de audio se trabaja como un reproductor con subtítulos:
   - el análisis lee la pista `segundos_analisis_adelantado` (3 s) **antes** de que suene por las bocinas;
   - cada estado de la pantalla se guarda con su segundo de análisis;
   - se muestra el estado de lo que se canta con `segundos_letra_adelantada` (0 s por omisión: junto con la voz), descontando `segundos_latencia_reconocimiento` (1 s). La pantalla va `3 − 0 − 1 = 2 s` detrás del análisis.
   - Las teclas del operador se ven al instante, sin ese retraso.
   - Con el micrófono no se puede retrasar al cantante: la letra se adelanta con el avance anticipado, la predicción por tempo y las líneas siguientes visibles.

### 5.5 Canciones nuevas (aprendizaje)

Solo se considera **nueva** si se acumulan 20 palabras (`palabras_cancion_nueva`) del motor más confiable (Whisper si está, si no Vosk) y **ninguna** canción de la base se parece a lo escuchado (puntaje menor que `parecido_cancion_conocida`, 0.45). Cada motor se analiza por separado, para que el ruido de Vosk no se mezcle con las frases correctas de Whisper. Las groserías que la IA transcribe por error se ocultan (`censurar_transcripcion`). Entonces:

1. Se crea un registro en `TEMP_NOMBRES` y cada frase que entrega el canal libre se guarda como una línea en `TEMP_LETRAS`. Las frases de Vosk terminan en las pausas naturales del canto, que suelen coincidir con las líneas, y se dividen si pasan de 80 caracteres.
2. Termina con 8 s de silencio o con la tecla **t**.
3. **Nombre sugerido:** la línea que más se repite, que normalmente es el coro y suele contener el título. Si ninguna se repite, las primeras palabras de la primera línea.
4. Lo que tiene **menos de 3 líneas se descarta**: un comentario o el murmullo del final de una pista no es una canción.
5. Si mientras aprende lo que se canta resulta pertenecer a una canción existente, se cancela el aprendizaje y se sigue esa canción.
6. En *f → v* el usuario corrige la letra, confirma o cambia el nombre y la pasa a las tablas permanentes.

---

## 6. Limpieza del sonido

`LimpiadorAudio` (`karaoke/audio/limpieza.py`) procesa el audio en tiempo real, en tramas de 512 muestras (32 ms) con 50 % de traslape y ventana raíz de Hann, que reconstruye la señal perfectamente (error < 10⁻⁷). Solo usa NumPy, para que funcione igual en Windows y en Android.

1. **Filtro pasa banda de 100 a 4000 Hz** en el dominio de la frecuencia, con bordes de coseno de 60 Hz. Quita el zumbido de la red eléctrica (50/60 Hz), el bajo, el bombo y los agudos que no aportan a la inteligibilidad.
2. **Sustracción espectral.** Durante los primeros 1.5 s se mide el espectro del ruido. Después se resta, con factor `factor_sustraccion` (1.0), un piso espectral de 0.25 y un suavizado temporal de la ganancia para evitar el "ruido musical". El perfil del ruido se sigue actualizando en las tramas sin voz.
3. **Detector de voz (VAD).** Hay voz si la energía en la banda supera 4 veces (+6 dB) la del ruido, con una cola de 0.3 s para no cortar entre sílabas. Se combina con "¿el motor reconoce palabras?".
4. **Control automático de ganancia** hacia −20 dBFS: baja rápido para no saturar y sube despacio para no "bombear", con un máximo de +20 dB. Le sigue un **limitador suave** `tanh`, que nunca pasa de 1.0.
5. **Aislamiento de voz estéreo** (archivos ya mezclados). La voz principal suele estar al **centro** de la mezcla. Se calcula M = (L+R)/2 y S = (L−R)/2, y el espectro de S, que es lo que no está al centro, se resta del de M.

**Resultado medido:** con una voz sintética mezclada con ruido y zumbido de 50 Hz, la relación señal/ruido pasó de **4.7 dB a 15.7 dB**. El aislamiento estéreo mejoró una mezcla de prueba de 6.5 a 9.8 dB.

**Lección importante.** Con una canción ya mezclada, el "ruido" que se mide al inicio **es la música**, y restarlo también borra parte de la voz: Vosk reconoció menos palabras con la sustracción que sin ella. Por eso, **con archivos se usa el aislamiento estéreo sin sustracción**. Con el micrófono, donde el ruido sí es ruido del lugar, se usa la limpieza completa.

---

## 7. Evaluación con canciones reales

Se probó con dos canciones **escritas por el autor del proyecto** (audio producido con Suno), que se incluyen en `ejemplos/`. Sus derechos se describen al final de este manual:

- *Sound of You*: 3:07, inglés.
- *Ghost of you (Remastered)*: 2:09, inglés con versos en español.

Las mediciones se hicieron en GitHub Actions (`.github/workflows/prueba-voz.yml`) con `herramientas/transcribir.py`. "Palabras de la letra" cuenta las palabras reconocidas que existen en la letra; "identificadas" son las frases que, solas, identificaron la canción y la línea correctas.

**Sound of You**

| Variante | Palabras de la letra | Frases identificadas | Velocidad |
|---|---|---|---|
| Vosk libre, sin limpieza | 22 | 2 | 21× tiempo real |
| Vosk libre, con sustracción espectral | 17 | 0 | 18× |
| Vosk restringido + aislamiento | 20 (todas de la letra) | 1 | 34× |
| Whisper base con su filtro VAD interno | 32 | 2 | 40× |
| **Whisper base sin VAD + aislamiento** | **185** | **17** | 8.6× |

**Ghost of you** (bilingüe)

| Variante | Palabras de la letra | Frases identificadas | Velocidad |
|---|---|---|---|
| Whisper base, inglés | 190 | 20 de 29 | 8.7× |
| Whisper base, idioma automático | 199 (incluye el español) | 16 de 32 | 3.6× |

**Hallazgos que cambiaron el diseño:**
1. El filtro de voz interno de Whisper **descartaba la voz cantada** sobre música; se desactivó.
2. Whisper "inventa" texto en la música o el silencio ("Music", "2.5%"); se filtra con `es_alucinacion()`.
3. Mientras espera, Whisper detecta el idioma; al seguir una canción usa el idioma de esa canción, que es más rápido y preciso.

**Prueba de punta a punta del modo automático** (`--simular`, Vosk + Whisper):

| Canción | Identificada | Seguimiento |
|---|---|---|
| Sound of You | a los 21 s, línea 1 | las 24 líneas, completa a los 2:26 |
| Ghost of you | a los 16 s, línea 2 | las 19 líneas, incluidas las de español; completa a los 1:53 |

### 7.1 Escribir la letra desde un MP3 (*f → m*)

Se midió qué tanto se parece la letra que escribe la IA a la letra real (porcentaje de palabras en el mismo orden, `herramientas/borrador_desde_audio.py`):

| Configuración | Sound of You | Ghost of you |
|---|---|---|
| Whisper base, voz aislada (primera versión) | 41 % | 81 % |
| Whisper base, mezcla original | 89 % | 68 % |
| Whisper small, voz aislada | 90 % | 84 % |
| **Whisper small, mezcla original (elegida)** | **91 %** | **87 %** |

Además de usar el modelo *small*, las líneas se cortan con las **marcas de tiempo de cada palabra**: en las pausas del cantante, al inicio de cada verso (palabra con mayúscula) y en respiros cortos si la línea ya es larga. Antes Whisper juntaba dos versos en una línea. Cada línea guarda el segundo en que empieza en la pista.

---

## 8. Configuración (`karaoke.ini`)

Se crea la primera vez junto al programa. Si falta una clave, se usa su valor por omisión (definidos en `VALORES_POR_OMISION`, en `karaoke/config.py`). Un valor inválido también se reemplaza por el de omisión.

| Sección | Clave | Omisión | Descripción |
|---|---|---|---|
| `base_datos` | `archivo` | `CANCIONES.db` | Archivo SQLite |
| `letras` | `caracteres_por_linea` | **80** | Longitud promedio/máxima de una línea |
| `letras` | `accion_linea_larga` | `dividir` | `dividir`, `truncar` o `conservar` |
| `letras` | `lineas_promedio_cancion` | **10** | Promedio de líneas (aviso si una canción es muy corta) |
| `letras` | `lineas_maximas_cancion` | 500 | Máximo de líneas aceptado al importar |
| `letras` | `elementos_por_pagina` | 10 | Paginación de las opciones *w* y *x* |
| `programa` | `archivo` | `PROGRAMA.txt` | Archivo del programa (también se acepta `PROGRAMA`) |
| `busqueda` | `puntaje_minimo` | 0.55 | Puntaje mínimo para identificar |
| `busqueda` | `semejanza_palabra` | 0.78 | Tolerancia a errores por palabra |
| `busqueda` | `evidencia_minima` | 2.5 | Evidencia mínima para identificar |
| `audio` | `motor` | `hibrido` | `hibrido`, `vosk`, `whisper` o `simulado` |
| `audio` | `modelo_vosk_es`, `modelo_vosk_en` | `modelo/...` | Carpetas de los modelos de Vosk |
| `audio` | `modelo_whisper`, `carpeta_whisper` | `base`, `modelo/whisper-base` | Modelo de Whisper |
| `audio` | `dispositivo` | (vacío) | Micrófono; se elige en *d → e* |
| `audio` | `filtro_pasa_altos_hz`, `filtro_pasa_bajos_hz` | 100, 4000 | Banda de la voz |
| `audio` | `reduccion_ruido`, `factor_sustraccion`, `segundos_calibracion` | sí, 1.0, 1.5 | Sustracción espectral |
| `audio` | `control_ganancia`, `nivel_objetivo_db` | sí, −20 | AGC |
| `audio` | `aislar_voz_archivo` | sí | Aislamiento estéreo para archivos |
| `automatico` | `palabras_muestra` | 4 | Palabras mínimas para intentar identificar |
| `automatico` | `palabras_cancion_nueva` | 14 | Palabras sin identificar para aprender una canción nueva |
| `automatico` | `avance_linea` | 0.70 | Fracción de la línea para mostrar la siguiente |
| `automatico` | `segundos_silencio_pausa` | 6 | Pausa automática |
| `automatico` | `segundos_silencio_fin_aprendizaje` | 8 | Fin del aprendizaje |
| `automatico` | `segundos_silencio_fin_sesion` | 0 | Fin automático de la sesión (0 = nunca) |
| `automatico` | `prediccion_tempo`, `vocabulario_restringido` | sí, sí | Predicción por tempo y canal restringido |
| `pantalla` | `lineas_previas`, `lineas_siguientes`, `colores` | 1, 2, sí | Pantalla del karaoke |

**Dónde cambiar los 80 caracteres y las 10 líneas:** en `karaoke.ini` (`[letras] caracteres_por_linea` y `lineas_promedio_cancion`), sin recompilar. Los valores por omisión están en `karaoke/config.py`. La base de datos no impone límites, porque `TEXT` en SQLite no tiene longitud máxima. La pantalla envuelve cualquier línea al ancho de la ventana.

---

## 9. Pruebas automatizadas e integración continua

```bash
python -m pytest        # 147 pruebas, unos 6 segundos
```

| Archivo | Qué prueba |
|---|---|
| `test_texto.py` | Normalización, tildes, ñ, apóstrofos, división de líneas, etiquetas, idioma, archivos UTF-8/ANSI/BOM/CRLF |
| `test_config.py` | Creación y lectura de `karaoke.ini`, valores inválidos, `KARAOKE_HOME` |
| `test_db.py` | Creación y detección de la base, códigos automáticos que no se reutilizan, duplicados, papelera (restaurar, eliminar, purga por antigüedad), transacciones, limpieza de textos, inyección SQL, migración v1 → v2 con respaldo, temporales, programa, historial, sesiones abiertas |
| `test_importador.py` | Los dos formatos, etiquetas, CRLF, duplicadas, líneas largas, archivos ANSI |
| `test_buscador.py` | Identificación con errores de dedo, rechazo con poca evidencia, desempate por programa, índice que se actualiza |
| `test_programa_sesion.py` | PROGRAMA flexible, acciones c/i/r/g/s/a, sesión completa |
| `test_seguimiento.py` | Avance, tolerancia, línea igual, repetición, fin, tempo, anclas de Whisper |
| `test_automatico.py` | Sesiones simuladas: identificar, empezar a mitad, pausa y reanudación, programa, aprender una canción nueva, descartar aprendizajes cortos, teclas |
| `test_audio.py` | PCM, remuestreo, reconstrucción perfecta, mejora de SNR, detector de voz, AGC sin saturar, aislamiento estéreo, WAV/MP3, motor simulado, alucinaciones |
| `test_interfaz.py` | **Integración:** ejecutan `main.py` con entradas escritas (alimentación, consultas, corrección, borrado con confirmación, programa y modo manual) y revisan la base de datos |

Las pruebas encontraron y corrigieron errores reales antes de la entrega:
- el bono del programa no desempataba;
- el limitador podía saturar;
- los saltos de línea de Windows no se normalizaban, lo que solo falló en Windows.

**GitHub Actions:**
- `pruebas.yml`: todas las pruebas en **Windows y Linux**, con Python 3.11 y 3.12, en cada cambio.
- `prueba-voz.yml`: mide la transcripción con Vosk y Whisper y ejecuta el modo automático de punta a punta con las canciones reales.
- `windows-exe.yml`: construye y **prueba** el ejecutable de Windows (sección 10).

---

## 10. Construcción del ejecutable de Windows

`.github/workflows/windows-exe.yml` corre en `windows-latest`:

1. Instala las dependencias y ejecuta las pruebas.
2. Construye con **PyInstaller** en modo carpeta (`--onedir`). Arranca más rápido y es más confiable que `--onefile` con bibliotecas nativas grandes. Usa `--collect-all vosk faster_whisper ctranslate2` y los binarios de PortAudio de `sounddevice`.
3. Descarga los modelos de Vosk (español e inglés) y Whisper base dentro de `modelo/`, para que el programa funcione **sin internet**.
4. Copia `ejemplos/`, `docs/` y `canciones.txt`.
5. **Prueba el `.exe`:**
   - con un guion de teclas: crea la base, importa las canciones, las lista y sale;
   - con `--simular` sobre *Ghost of you*: debe identificar la canción dentro del ejecutable.
6. Comprime todo como `KaraokeInteligente-Windows.zip` y lo publica como artefacto. Con una etiqueta `v*`, también lo publica en *Releases*.

Para construirlo a mano en Windows:

```powershell
pip install -r requirements.txt faster-whisper pyinstaller
pyinstaller --noconfirm --onedir --console --name KaraokeInteligente `
  --collect-all vosk --collect-all faster_whisper --collect-all ctranslate2 `
  --collect-binaries sounddevice --collect-data _sounddevice_data --collect-submodules karaoke main.py
# Copie la carpeta modelo\ y ejemplos\ dentro de dist\KaraokeInteligente\
```

El ejecutable busca `karaoke.ini`, `CANCIONES.db`, `PROGRAMA.txt` y `modelo/` **en su propia carpeta**. La variable de entorno `KARAOKE_HOME` o la opción `--carpeta` permiten usar otra.

---

## 11. Versión para Android

### Tecnología

**Kivy 2.3** (Python), compilado a APK con **Buildozer / python-for-android** en GitHub Actions (`.github/workflows/android-apk.yml`). La app (`movil/`) usa **el mismo paquete `karaoke`** que la versión de Windows: base de datos, buscador, programa, sesión, seguidor y controlador automático. Solo cambian la interfaz y la fuente de voz.

| Módulo | Contenido |
|---|---|
| `movil/main.py` | Punto de entrada; agrega el núcleo `karaoke` al `sys.path` |
| `movil/app/tema.py` | **Sistema de diseño**: paleta fría y mate con contraste verificado (WCAG ≥ 4.5:1 en textos), tipografía Inter con jerarquía por peso y tamaño, espaciado, radios, movimiento e íconos |
| `movil/app/componentes.py` | Componentes reutilizables: tarjetas, botones con respuesta inmediata al presionar, campos, chips, filas, barra de pestañas, diálogos y avisos |
| `movil/app/aplicacion.py` | Datos (en el almacenamiento privado de la app), navegación con pila y transiciones, botón *atrás* de Android |
| `movil/app/pantallas/*` | Cantar, Biblioteca + Detalle, Agregar / Nueva / Editor, Buscar, Escenario, Programa, Más (Historial, Ajustes, Acerca de, Papelera) |
| `movil/app/voz.py` | `VozAndroid` (reconocedor del sistema) y `VozDemostracion` (guion) |

### Modo automático en Android

Vosk y Whisper necesitan NumPy y modelos de cientos de MB, demasiado pesados para una APK liviana. Por eso, en Android se usa el **reconocedor de voz del propio sistema** (`android.speech.SpeechRecognizer`, a través de `plyer.stt`). Es lo que sugiere la especificación: aprovechar los recursos locales de Android.

- Entrega **resultados parciales** mientras se canta y, con el paquete de idioma descargado, funciona **sin internet** (`prefer_offline`).
- Se detiene solo tras un silencio, así que `VozAndroid` lo **reinicia automáticamente** para escuchar de forma continua.
- El idioma pasa al de la canción identificada (`es-ES` / `en-US`).
- Las transcripciones se convierten en `Transcripcion` y van al **mismo `ControladorAutomatico`** de Windows: identificación con evidencia mínima, seguidor línea por línea, pausas automáticas, aprendizaje de canciones nuevas y programa.
- El núcleo se separó de NumPy para esto: `karaoke/transcripcion.py` y `karaoke/motor_simulado.py` no lo usan, y la APK no incluye `karaoke/audio` ni la interfaz de consola.
- **Permisos:** solo `RECORD_AUDIO`, pedido en tiempo de ejecución la primera vez. Para Android 11+ se declara en el manifiesto la consulta a `android.speech.RecognitionService` (`recursos/consultas_voz.xml`).

### Compilación

```bash
cd movil
cp -r ../karaoke ./karaoke        # el flujo de GitHub Actions lo hace solo
buildozer -v android debug        # genera bin/karaokeinteligente-1.0.0-...-debug.apk
```

`buildozer.spec`:

| Clave | Valor |
|---|---|
| Requisitos | `python3, kivy==2.3.1, plyer==2.1.0, pyjnius` |
| API | 34; mínimo 24 (Android 7) |
| Arquitecturas | `arm64-v8a` (64 bits; con dos arquitecturas python-for-android mezcla versiones de pip en su entorno virtual y falla) |
| Ícono y pantalla de inicio | `recursos/` |

Para probar la interfaz en la computadora: `python movil/main.py` (requiere `pip install kivy plyer`). `herramientas/capturas_movil.py` genera capturas de cada pantalla.

---

## 12. Suposiciones y decisiones de diseño

| # | Situación en la especificación | Decisión |
|---|---|---|
| 1 | La letra **i** se pide para "igual" y para "ignorar" | **i = igual**, **g = ignorar**, **s = seguir** |
| 2 | Campos `código`, `nombre_canción`, `línea` | Se escribieron sin tildes (`codigo`, `nombre_cancion`, `linea`) por compatibilidad |
| 3 | La base de datos se llama "CANCIONES" | El archivo es `CANCIONES.db` (configurable) |
| 4 | El archivo se llama "PROGRAMA" | Se usa `PROGRAMA.txt` y también se acepta `PROGRAMA` sin extensión |
| 5 | Formato del archivo de canciones: nombre y luego la letra | Las canciones se separan con una línea en blanco; si la letra tiene estrofas, se marcan los nombres con `#` o `NOMBRE:`. Se ignoran etiquetas como `[Coro]` y comentarios `//` |
| 6 | 10 líneas y 80 caracteres en promedio | Son valores de `karaoke.ini`. Las líneas más largas se **dividen** por omisión, y se puede elegir truncar o conservar |
| 7 | "Tablas temporales" para canciones aprendidas | Tablas permanentes `TEMP_NOMBRES`/`TEMP_LETRAS`, porque deben sobrevivir hasta que se revisen |
| 8 | "Averiguar el nombre" de una canción aprendida | Se sugiere la línea más repetida (el coro) y el usuario la confirma |
| 9 | Código generado automáticamente | `INTEGER PRIMARY KEY AUTOINCREMENT`; un código borrado nunca se reutiliza |
| 10 | Nombres duplicados | No se permiten dos canciones con el mismo nombre normalizado (sin tildes ni mayúsculas) |
| 11 | ¿Desde qué línea se muestra al buscar con palabras? | Desde la línea **donde terminan** las palabras escuchadas, que es la que se está cantando |
| 12 | ¿Cuándo pasar a la siguiente línea en automático? | Al 70 % de la línea actual, un poco antes para que el público no se atrase |
| 13 | Canciones en varios idiomas | Se detecta el idioma de cada letra (`es`/`en`). Whisper detecta el idioma solo mientras identifica |
| 14 | El orden del PROGRAMA no es estricto | Siempre se sugiere la primera pendiente; cantar otra la marca como cantada; una canción abandonada (**b**/**x**) sigue pendiente |
| 15 | ¿Cuándo termina la sesión? | Con **f**. En automático, opcionalmente, tras un silencio configurable |
| 16 | Opciones agregadas | **a** atrás, **b** buscar otra, **n** siguiente del programa, **x** abandonar, **t** terminar de aprender; menú **h** historial, **d** diagnóstico de audio, **k** configuración |
| 17 | Interfaz | Consola, que funciona igual en Windows y Android/Termux. Letra resaltada en amarillo y grande, colores ANSI y teclas sin Enter |
| 18 | Borrar una canción | Se mueve a una **papelera** discreta (opción *b* → *P*; en Android, *Más → Papelera*) y se elimina sola a los 30 días. La especificación pide confirmar antes de borrar; la papelera agrega la posibilidad de recuperarla |

---

## 13. Limitaciones conocidas y mejoras futuras

- **Voz y música mezcladas en un mismo canal** (micrófono junto a la bocina): es el caso más difícil. Mejoras previstas:
  - **cancelación de la pista conocida**: cuando el programa reproduce la música, restarla del micrófono, como la cancelación de eco de las videollamadas;
  - **separación de fuentes con IA** (Demucs / MDX-Net) para archivos.
- **Vosk solo tiene modelos pequeños en algunos idiomas.** Las líneas en español de una canción en inglés no las reconoce el canal restringido de Vosk en inglés; las cubren Whisper y la predicción por tempo.
- **Whisper en una CPU lenta** puede tardar más que la ventana de 6 s. El programa descarta ventanas para no retrasarse, y Vosk sigue funcionando.
- **Interfaz gráfica:** la versión actual es de consola. Está prevista una interfaz gráfica y una versión web.

---

## 14. Seguridad

| Riesgo | Medida |
|---|---|
| **Inyección SQL** | Todas las consultas usan **parámetros** (`?`); nunca se arma SQL con texto del usuario. Una prueba guarda el nombre `x'); DROP TABLE NOMBRES; --` y verifica que se trata como texto |
| **Datos a medias** si algo falla | Las escrituras que tocan varias tablas (canción + letra, programa, temporales) van en una **transacción**: todo o nada (`_transaccion()`, con `rollback` si hay error). Hay una prueba que simula una falla a la mitad |
| **Integridad referencial** | `PRAGMA foreign_keys = ON`, `ON DELETE CASCADE` para la letra y `ON DELETE SET NULL` para el programa. Al abrir se ejecuta `PRAGMA quick_check` |
| **Entradas anómalas** | Los textos se limpian de caracteres de control y se limitan: nombre ≤ 150, línea ≤ 1000 caracteres y ≤ 2000 líneas por canción. Los archivos de texto de más de **5 MB** se rechazan |
| **Borrado accidental** | Confirmación + **papelera** con restauración + purga automática configurable |
| **Pérdida de datos al actualizar** | Antes de migrar el esquema se guarda un **respaldo** automático (`CANCIONES.respaldo-antes-de-vN.db`) |
| **Archivos descargados** | Los modelos de voz se descargan solo por **HTTPS** desde direcciones fijas. Al descomprimir se verifica que ningún archivo quede **fuera de la carpeta destino** (protección contra *zip slip*), con su prueba |
| **Privacidad del audio** | El reconocimiento de voz es **local**: Vosk y Whisper corren en el equipo y el audio nunca sale de él. En Android se pide únicamente el permiso de micrófono |
| **Fallos inesperados** | El menú atrapa cualquier excepción y la muestra sin cerrar el programa; la sesión abierta se cierra bien al volver a abrir |

## 15. Escalabilidad y versiones futuras

- **Capas independientes.** El núcleo (`db`, `buscador`, `seguimiento`, `automatico`) no conoce la interfaz. La consola de Windows, la app de Android y la herramienta sin pantalla lo reutilizan tal cual; una versión web (Vercel) o de escritorio gráfica usaría el mismo núcleo.
- **Migraciones de esquema.** `METADATOS.version_esquema` y `BaseDatos._migrar()` actualizan solas las bases de versiones anteriores (v1 → v2 agregó la papelera), con respaldo previo. Cada versión nueva agrega su paso.
- **Motores de voz intercambiables.** Todos los motores (`Vosk`, `Whisper`, `Simulado` y el reconocedor de Android) cumplen la misma interfaz (`procesar` → `Transcripcion`). Agregar otro, como un servicio en la nube o un modelo nuevo, no toca el resto del programa.
- **Configuración externa.** Todos los umbrales y tiempos están en `karaoke.ini`; ajustar el comportamiento no requiere recompilar.
- **Volumen de canciones.** El buscador mantiene un índice invertido en memoria y solo alinea las canciones candidatas (como máximo 60). Es instantáneo con cientos o algunos miles de canciones. Para decenas de miles, el siguiente paso es prefiltrar con **SQLite FTS5**, que ya viene en Python, antes del alineamiento.
- **Calidad continua.** 147 pruebas automáticas en Windows y Linux en cada cambio, más la prueba de punta a punta con audio real y la construcción y prueba del ejecutable.

---

## Derechos de autor de las canciones de ejemplo

Las letras de las canciones **"Sound of You"** y **"Ghost of you"** son obra original de **Edgar Alessandro Chocon Oliva** (carné 202212978), igual que las grabaciones `ejemplos/Sound_of_You.mp3` y `ejemplos/Ghost_of_you_Remastered.mp3`, que el autor produjo con la herramienta Suno.

© 2026 Edgar Alessandro Chocon Oliva. **Todos los derechos reservados.**

Se incluyen en este proyecto **únicamente como material de ejemplo y de prueba** del Karaoke Inteligente. No se autoriza copiarlas, distribuirlas, interpretarlas públicamente ni usarlas con otro fin sin el permiso escrito del autor. La licencia del código del programa no se extiende a estas letras ni a estos audios.
