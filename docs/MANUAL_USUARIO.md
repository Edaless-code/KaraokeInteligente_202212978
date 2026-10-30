# Manual de usuario · Karaoke Inteligente

**Autor:** Edgar Alessandro Chocon Oliva · Carné 202212978
**Versión:** 1.0.0

El Karaoke Inteligente muestra en pantalla, **línea por línea**, la letra de la canción que alguien está cantando, al ritmo del cantante. Así el público puede acompañarlo aunque no se sepa la letra de memoria.

Funciona de dos maneras:

| Modo | Quién avanza la letra |
|---|---|
| **Manual** | El operador escribe 2 o 3 palabras que escucha. El programa encuentra la canción y la línea, y después el operador avanza con la tecla **c**. |
| **Automático** | Una inteligencia artificial escucha al cantante por el micrófono, identifica la canción y avanza la letra sola. |

---

## Contenido

1. [Instalación y ejecución en Windows](#1-instalación-y-ejecución-en-windows)
2. [Instalación y ejecución en Android](#2-instalación-y-ejecución-en-android)
3. [Primer uso en cinco minutos](#3-primer-uso-en-cinco-minutos)
4. [Menú principal](#4-menú-principal)
5. [Modo manual (m)](#5-modo-manual-m)
6. [Modo automático (a)](#6-modo-automático-a)
7. [Modo alimentación (f)](#7-modo-alimentación-f)
8. [Programa del cantante (p)](#8-programa-del-cantante-p)
9. [Consultas, corrección y borrado (w, x, u, b)](#9-consultas-corrección-y-borrado-w-x-u-b)
10. [Opciones agregadas (h, k, d)](#10-opciones-agregadas-h-k-d)
11. [Configuración: cómo cambiar los 80 caracteres y las 10 líneas](#11-configuración-cómo-cambiar-los-80-caracteres-y-las-10-líneas)
12. [Formato de los archivos de texto](#12-formato-de-los-archivos-de-texto)
13. [Problemas frecuentes](#13-problemas-frecuentes)
14. [Derechos de autor de las canciones de ejemplo](#derechos-de-autor-de-las-canciones-de-ejemplo)

---

## 1. Instalación y ejecución en Windows

### Opción A: ejecutable listo (recomendada)

No hace falta instalar Python ni nada más.

1. Descargue **`KaraokeInteligente-Windows.zip`**:
   - de la página *Releases* del repositorio, o
   - de la pestaña *Actions* → *Ejecutable de Windows* → la ejecución más reciente → *Artifacts*.
2. Haga clic derecho en el ZIP → **Extraer todo…** y elija una carpeta, por ejemplo `C:\KaraokeInteligente`.
3. Abra la carpeta y haga doble clic en **`KaraokeInteligente.exe`**.
   - Si Windows SmartScreen muestra "Windows protegió su PC", presione **Más información → Ejecutar de todas formas**. Aparece porque el programa no está firmado digitalmente.
4. Se abre una ventana de consola con el menú principal. Para verla mejor, maximícela y use **Windows Terminal**, que viene en Windows 10 y 11.

La carpeta contiene:

```
KaraokeInteligente\
├── KaraokeInteligente.exe    ← el programa
├── _internal\                ← bibliotecas del programa (no tocar)
├── modelo\                   ← modelos de voz (Vosk español, Vosk inglés, Whisper)
├── ejemplos\                 ← canciones y audios de prueba
├── canciones.txt             ← canciones de ejemplo para la opción (f) → (t)
├── docs\                     ← este manual y el manual técnico
├── karaoke.ini               ← configuración (se crea la primera vez)
└── CANCIONES.db              ← base de datos (se crea la primera vez)
```

Requisitos: Windows 10 u 11 de 64 bits, 4 GB de RAM y unos 700 MB de disco. El micrófono solo se necesita para el modo automático en vivo.

### Opción B: desde el código fuente (Python)

1. Instale **Python 3.11 o 3.12** desde <https://www.python.org/downloads/> y marque la casilla *Add Python to PATH*.
2. Abra **PowerShell** en la carpeta del proyecto y ejecute:

   ```powershell
   pip install -r requirements.txt
   pip install faster-whisper      # opcional: Whisper mejora el modo automático
   python main.py
   ```

3. La primera vez que use el modo automático, el programa ofrece descargar los modelos de voz de Vosk, que pesan unos 40 MB cada uno. Whisper descarga su modelo solo, la primera vez que se usa.

---

## 2. Instalación y ejecución en Android

La versión de Android es una **app con interfaz táctil**, no la consola. Tiene las mismas funciones y usa el mismo núcleo que la versión de Windows.

### Instalar la APK

1. Descargue **`KaraokeInteligente-Android.apk`** en el teléfono:
   - de *Releases* del repositorio, o
   - de *Actions → APK de Android → la ejecución más reciente → Artifacts* (GitHub la entrega dentro de un ZIP: extráigala).
2. Abra el archivo `.apk`. Si Android pregunta, permita **"Instalar aplicaciones de origen desconocido"** para el navegador o el administrador de archivos. Aparece porque la app no viene de Google Play.
3. Toque **Instalar** y luego **Abrir**.
4. La primera vez que use el **modo automático**, Android pedirá el permiso de **micrófono**. Es el único permiso de la app.

Requisitos: Android 7.0 o superior. Para el modo automático sin internet, el teléfono debe tener descargado el idioma en *Ajustes → Sistema → Idiomas → Reconocimiento de voz sin conexión*. El nombre exacto del menú cambia según la marca.

### Uso de la app

La app tiene cuatro pestañas abajo:

| Pestaña | Para qué | Equivale a |
|---|---|---|
| **Cantar** | Muestra la siguiente canción del programa y los dos modos: **Modo manual** y **Modo automático** | *m*, *a* |
| **Biblioteca** | Lista de canciones de 10 en 10 y búsqueda por nombre o código. Al tocar una canción se ve su letra de 10 en 10, con botones para **corregir** (lápiz) y **borrar** (bote rojo, con confirmación). El botón **+** abre *Agregar canciones* | *w*, *x*, *u*, *b*, *f* |
| **Programa** | Escribir o importar el programa del cantante, ver qué está pendiente o cantado, cantar una canción del programa y reiniciar el avance | *p* |
| **Más** | Historial y estadísticas, ajustes, acerca de (con los derechos de autor) y, al final, la **Papelera** | *h*, *k* |

**Agregar canciones** (Biblioteca → **+**):

| Opción | Cómo funciona | Equivale a |
|---|---|---|
| **Pegar o escribir la letra** | El nombre y toda la letra de una vez. Cada renglón es una línea; las etiquetas como `[Chorus]` se quitan solas y las líneas largas se dividen. Es lo más rápido para canciones nuevas | — |
| **Línea por línea** | Un campo para el nombre y otro para cada línea. **Enter** agrega la línea y una **línea vacía** termina | *e* |
| **Importar archivo de texto** | Elegir un `.txt` del teléfono | *t* |
| **Canciones de ejemplo** | Carga *Sound of You* y *Ghost of you* | — |
| **Aprendidas por el modo automático** | Corregirlas, ponerles nombre y guardarlas en la biblioteca | *v* |

**Pantalla del karaoke (Escenario):**
- La línea que toca cantar aparece **grande y centrada**, con la anterior arriba en tono tenue y las dos siguientes debajo.
- Arriba se ven la canción, "Línea X de Y", el estado y una barra de progreso.
- Para avanzar:
  - **Continuar** o **tocar la letra**: siguiente línea (*c*);
  - **deslizar a la izquierda**: avanzar;
  - **deslizar a la derecha**: regresar.
- Los botones de abajo son **Atrás** (*a*), **Igual** (*i*), **Repetir** (*r*) y **Pausa/Seguir** (*g*/*s*).
- La **X** termina la sesión y muestra el resumen de las canciones cantadas (*f*).

**Modo automático:**
- La app escucha con el **reconocedor de voz del teléfono**, reconoce la canción y la sigue sola.
- La barra inferior muestra lo que va escuchando, y el punto se ilumina cuando detecta voz.
- Los mismos botones corrigen lo que decida la IA.
- Para mostrarlo **sin cantar**, active *Más → Ajustes → Usar la demostración*: la app sigue *Sound of You* con un guion.

**Papelera:** *Más → Papelera* permite restaurar o eliminar definitivamente las canciones borradas. Está al final de la pantalla, a propósito, para que no estorbe.

---

## 3. Primer uso en cinco minutos

1. Abra el programa. Verá el mensaje **"Base de datos CANCIONES creada…"**: el programa detectó que no existía y creó todas las tablas. Las siguientes veces dirá **"Base de datos CANCIONES encontrada"**.
2. Presione **f**, luego **t** y después **Enter** dos veces. Así se cargan las canciones de ejemplo de `canciones.txt`.
3. Presione **r** para regresar y luego **w** para ver la lista de canciones.
4. Presione **m** (modo manual) y escriba `follow me everywhere`. El programa encuentra *Sound of You* en la línea 3. Presione **c** para avanzar.
5. Para probar el modo automático sin cantar, presione **a**, luego **a** (archivo) y después **Enter**. Escuchará *Sound of You* y verá cómo la letra avanza sola.

---

## 4. Menú principal

En cada menú se escribe la letra de la opción y se presiona **Enter**.

| Tecla | Opción | Descripción |
|---|---|---|
| **m** | Modo manual | Buscar la canción con palabras y avanzar con **c** |
| **a** | Modo automático | La IA escucha, identifica y avanza sola |
| **f** | Modo alimentación | Agregar canciones desde un archivo (t) o escribiéndolas (e) |
| **p** | Programa del cantante | Cargar la lista preplaneada de canciones (archivo PROGRAMA) |
| **w** | Ver canciones | Todos los códigos y nombres, de 10 en 10 |
| **x** | Ver una letra | Se ingresa el código y se despliega la letra de 10 en 10 |
| **u** | Corregir | Corregir la letra de una canción por nombre o código |
| **b** | Borrar | Borrar una canción y su letra, con confirmación |
| **h** | Historial *(agregada)* | Canciones más cantadas y últimas interpretaciones |
| **d** | Diagnóstico de audio *(agregada)* | Elegir el micrófono y probar la limpieza del sonido |
| **k** | Configuración *(agregada)* | Ver los valores actuales y dónde se cambian |
| **s** | Salir | Cerrar el programa |

Si hay canciones aprendidas por el modo automático pendientes de revisar, el menú lo avisa.

---

## 5. Modo manual (m)

Se usa cuando el cantante empieza a cantar de memoria.

### 5.1 Elegir la canción

En la pantalla de búsqueda se puede:

| Escribir | Resultado |
|---|---|
| **2 o 3 palabras** que se escuchan, por ejemplo `ojitos negros` | El programa busca en todas las letras, identifica la canción y **empieza en la línea que se está cantando**. Tolera errores de dedo (`folow me everiwere` también funciona). Si hay varias coincidencias, muestra una lista para elegir. |
| **Enter** (vacío) | Canta la **siguiente canción del PROGRAMA**, sin escribir palabras |
| **n** | Elegir otra canción del programa (romper el orden) |
| **x** | Dejar de seguir el programa en esta sesión |
| **r** | Repetir la última canción cantada |
| **#5** o **5** | Elegir la canción por su código |
| **g** | Ignorar: esperar sin hacer nada hasta presionar **s** |
| **f** | Finalizar la sesión y ver el resumen de las *n* canciones cantadas |

### 5.2 Durante la canción

La pantalla muestra en tono tenue la línea anterior. La línea que **toca cantar** aparece en **grande y amarilla, con ►**, y debajo se ven las siguientes. Aquí basta con presionar la tecla, **sin Enter**:

| Tecla | Acción |
|---|---|
| **c**, **Enter**, **→** | **Continuar** con la línea siguiente, cuando el cantante terminó o está por terminar la línea |
| **i** | **Igual**: el cantante repite la misma línea; la pantalla se queda en ella |
| **r** | **Repetir** la canción desde el inicio |
| **g** | **Ignorar**: suspende el avance si el cantante solo afina la voz o hace ejercicios. Puede usarse al inicio, en medio o al final |
| **s** | **Seguir** después de ignorar |
| **a**, **←** | **Atrás** *(agregada)*: regresa una línea si se avanzó por error |
| **b** | **Buscar otra** *(agregada)*: abandona la canción y vuelve a la búsqueda |
| **f** | **Finalizar** la sesión |

> **Nota sobre la letra *i*:** la especificación usaba la letra *i* para "igual" y también para "ignorar". Como una tecla no puede hacer dos cosas, se decidió: **i = igual**, **g = ignorar** (de "i**g**norar") y **s = seguir**.

Al terminar la última línea, la canción se registra como cantada, se marca en el programa y el programa vuelve a la búsqueda. Desde ahí, **Enter** pasa a la siguiente y **r** repite la misma. La sesión dura hasta presionar **f**, así que se pueden cantar todas las canciones que se quiera.

---

## 6. Modo automático (a)

1. Elija de dónde llega el sonido:
   - **m: micrófono**, para el karaoke en vivo. Antes, conviene elegir el micrófono en **d** (Diagnóstico).
   - **a: archivo de audio** MP3, WAV, FLAC u OGG, para probar el programa o acompañar una pista grabada. Se puede indicar desde qué segundo empezar y si se reproduce por las bocinas.
2. Al empezar, **guarde silencio 1 o 2 segundos**. El programa mide el ruido del lugar para poder limpiarlo.
3. Cante. El programa:
   - **identifica la canción** con lo que escucha, dando prioridad a la siguiente del PROGRAMA;
   - empieza a mostrar la letra **en la línea que se está cantando**, aunque sea a mitad de la canción;
   - **avanza línea por línea** al ritmo del cantante. Muestra la siguiente línea un poco antes de que se termine la actual, para que el público no se atrase;
   - detecta si se **repite una línea** o **la canción completa**;
   - se **pausa solo** si nadie canta durante 6 segundos y **sigue solo** cuando el cantante vuelve;
   - si se pierde el reconocimiento pero hay voz, **avanza según el tempo** que aprendió del cantante;
   - si la canción **no está en la base de datos**, la **aprende**: guarda la letra que escucha en tablas temporales y sugiere un nombre. Después se revisa en **f → v**;
   - al terminar una canción, espera la siguiente.

Abajo de la pantalla se ve lo último que escuchó, el nivel del sonido y si hay voz, el tempo del cantante y la siguiente canción del programa.

Las teclas del modo manual siguen funcionando **para corregir lo que haga la IA**, en cualquier momento:

| Tecla | Acción |
|---|---|
| **c** / **a** | Avanzar o regresar una línea |
| **i** | Igual (se queda en la línea) |
| **r** | Repetir la canción |
| **g** / **s** | Ignorar / seguir |
| **n** *(agregada)* | Cantar ya la siguiente canción del programa |
| **x** *(agregada)* | Abandonar la canción actual y esperar otra |
| **t** *(agregada)* | Terminar de aprender la canción nueva |
| **f** | Finalizar la sesión |

**Consejos para que funcione mejor:**

- Use un micrófono cercano al cantante y aléjelo de las bocinas.
- Revise el nivel en **d → n** antes de empezar: debe decir **VOZ** cuando alguien canta y **silencio** cuando no.
- Con Whisper instalado, que ya viene en el `.exe`, la identificación es mucho más precisa con música de fondo.

---

## 7. Modo alimentación (f)

| Tecla | Opción |
|---|---|
| **t** | **Leer un archivo de texto plano.** Se escribe la ruta (Enter = `canciones.txt` junto al programa). Se informa cuáles canciones se agregaron, cuáles se omitieron (por ejemplo, si ya existían) y cuántas líneas largas se ajustaron. |
| **e** | **Escribir en pantalla, campo por campo.** Primero aparece el campo del **nombre de la canción**, luego **Línea 1**, **Línea 2**, etc. **Dejar una línea vacía termina la canción.** |
| **v** | **Revisar las canciones aprendidas** por el modo automático: corregir su letra, ponerles nombre y pasarlas a la base de datos permanente, o descartarlas. |
| **r** | Regresar |

El **código** de cada canción **se genera automáticamente**: 1, 2, 3… y nunca se reutiliza, aunque se borre una canción.

---

## 8. Programa del cantante (p)

| Tecla | Opción |
|---|---|
| **c** | Cargar el archivo **`PROGRAMA.txt`** (también se acepta `PROGRAMA` sin extensión) |
| **e** | Escribir el programa en pantalla. También se guarda en `PROGRAMA.txt` |
| **v** | Ver el programa y su avance: **·** pendiente, **✓** cantada, **»** saltada |
| **l** | Volver a poner todas como pendientes |
| **r** | Regresar |

Al cargarlo, el programa busca cada nombre en la base de datos aunque tenga errores menores ("Prueva Dos" encuentra "Prueba Dos") y avisa cuáles no encontró.

**El orden no es estricto.** El programa siempre sugiere la primera canción pendiente, pero el cantante puede adelantarse a otra (esa se marca como cantada), saltarse canciones, repetir la misma *N* veces, dejar de seguir el programa (tecla **x** en el modo manual) o dejar de cantar.

---

## 9. Consultas, corrección y borrado (w, x, u, b)

- **w:** muestra la tabla de **códigos, nombres y número de líneas**, de 10 en 10. **Enter** o **s** muestra el siguiente grupo, **a** el anterior y **q** regresa.
- **x:** pide un **código**. Si existe, despliega la letra numerada de 10 en 10. Si no existe, lo indica claramente: **"NO EXISTE ninguna canción con el código…"**.
- **u:** pide el **nombre o el código**. Si hay varias coincidencias, deja elegir. En el editor:

  | Orden | Acción |
  |---|---|
  | `e 3` | editar la línea 3 |
  | `i 3` | insertar una línea antes de la 3 |
  | `d 3` | borrar la línea 3 |
  | `a` | agregar líneas al final |
  | `t` | reemplazar toda la letra |
  | `n` | cambiar el nombre |
  | `g` | **guardar** |
  | `c` | cancelar sin guardar |

- **b:** pide el **nombre o el código**, muestra la canción y pregunta **"¿Está SEGURO de borrar…? (s/n)"**. Solo con **s** se borra la canción **y toda su letra**.

### Papelera *(agregada)*

Borrar una canción **no la elimina de inmediato**: se mueve a la **papelera**, por si después se quiere recuperar.

- Para abrirla, en la opción **b** escriba **P** en lugar del nombre. Es un acceso discreto para que no se use por accidente.
- Elija la canción por su número:
  - **r** la **restaura** con su mismo código y su letra;
  - **e** la **elimina definitivamente**, después de una confirmación.
- **v** vacía toda la papelera, también con confirmación.
- Lo que lleva más de **30 días** en la papelera se elimina solo al abrir el programa. El plazo se cambia con `dias_papelera` en `karaoke.ini`; `0` = nunca.
- Mientras una canción está en la papelera no aparece en las búsquedas, en la lista (**w**) ni en el programa. Si se pide su código en **x**, el programa avisa que está en la papelera.
- En Android, la papelera está en **Más → Papelera**.

---

## 10. Opciones agregadas (h, k, d)

| Opción | Para qué sirve |
|---|---|
| **h: Historial y estadísticas** | Canciones más cantadas y las últimas interpretaciones, con su sesión, modo y si se completaron |
| **k: Configuración** | Muestra los archivos que usa el programa y los valores principales |
| **d: Diagnóstico de audio** | **l** lista los micrófonos; **e** elige uno y lo guarda en `karaoke.ini`; **n** mide en vivo el nivel del micrófono antes y después de la limpieza y si detecta voz; **o** hace lo mismo con un archivo de audio |

---

## 11. Configuración: cómo cambiar los 80 caracteres y las 10 líneas

La especificación supone canciones de **unas 10 líneas** con **líneas de unos 80 caracteres**. Estos valores **no están fijos en el código**: se leen del archivo **`karaoke.ini`**, que está junto al programa y se crea solo la primera vez. Para cambiarlos:

1. Cierre el programa.
2. Abra `karaoke.ini` con el **Bloc de notas**.
3. Cambie los valores de la sección `[letras]`:

```ini
[letras]
caracteres_por_linea = 80        ; longitud máxima de una línea
accion_linea_larga = dividir     ; dividir | truncar | conservar
lineas_promedio_cancion = 10     ; promedio de líneas por canción
lineas_maximas_cancion = 500     ; máximo aceptado por canción
elementos_por_pagina = 10        ; de cuántos en cuántos se muestra en (w) y (x)
dias_papelera = 30               ; días que una canción borrada se conserva en la papelera
```

4. Guarde y vuelva a abrir el programa.

Así se manejan las líneas **más largas**:

| Acción | Qué hace |
|---|---|
| `dividir` (por omisión) | Corta la línea en partes de máximo `caracteres_por_linea` letras, sin partir palabras |
| `truncar` | Recorta la línea |
| `conservar` | La guarda completa. La pantalla siempre la ajusta al ancho de la ventana |

Para letras con líneas **más cortas** no hay que hacer nada. Si las canciones tienen muchas más líneas, aumente `lineas_maximas_cancion`. La base de datos no tiene límite de longitud, porque SQLite guarda texto de cualquier tamaño.

Otros valores útiles:

| Sección | Clave | Para qué sirve |
|---|---|---|
| `[audio]` | `motor` | `hibrido` (Vosk + Whisper), `vosk`, `whisper` o `simulado` |
| `[audio]` | `dispositivo` | Micrófono |
| `[audio]` | `reduccion_ruido`, `filtro_pasa_altos_hz`, `filtro_pasa_bajos_hz` | Limpieza del sonido |
| `[automatico]` | `segundos_silencio_pausa` | Cuántos segundos sin voz para pausar |
| `[automatico]` | `avance_linea` | Qué tan antes se muestra la siguiente línea |
| `[busqueda]` | `semejanza_palabra`, `evidencia_minima` | Qué tan tolerante es la búsqueda |

El manual técnico explica cada clave.

---

## 12. Formato de los archivos de texto

### Archivo de canciones (opción f → t)

El nombre de la canción va en una línea y la letra en las siguientes, una línea por renglón. **Una línea en blanco separa una canción de otra**:

```
Sound of You
I heard the sound of you,
in every thing I do
...

Ghost of you
I wake up in the dead of night...
```

Si la letra tiene estrofas separadas por líneas en blanco, marque cada nombre con `#` o con `NOMBRE:`:

```
# Mi canción
Primera estrofa, línea 1
Primera estrofa, línea 2

Segunda estrofa, línea 1
```

- Se ignoran las etiquetas que no se cantan, como `[Verse 1]`, `Coro:`, `Chorus (x2)` o `(Fade out)`, y los comentarios que empiezan con `//`.
- Se aceptan archivos guardados en UTF-8 o en ANSI, como los del Bloc de notas antiguo, con tildes y ñ.

### Archivo PROGRAMA

Lleva un nombre de canción por renglón, en el orden en que se piensa cantar. Se aceptan numeraciones y viñetas:

```
1. Ghost of you
2. Sound of You
- Otra canción
```

---

## 13. Problemas frecuentes

| Problema | Solución |
|---|---|
| Windows SmartScreen bloquea el `.exe` | **Más información → Ejecutar de todas formas** |
| Se ven símbolos raros en lugar de tildes | Use **Windows Terminal**. En la consola clásica, elija la fuente *Consolas* |
| "No se pudo usar el audio del sistema" | Conecte o active el micrófono. Revise en Windows: *Configuración → Privacidad → Micrófono → Permitir que las aplicaciones de escritorio accedan* |
| El modo automático no identifica la canción | Verifique que la canción esté en la base (opción **w**). Revise el micrófono en **d → n**, acérquelo al cantante y cante algunas palabras más |
| La letra se adelanta o se atrasa | Use **a** / **c** para corregir. En `karaoke.ini`, `avance_linea` controla qué tan antes se muestra la siguiente línea |
| "Falta el modelo de voz" | Acepte la descarga, que necesita internet, o copie la carpeta `modelo` del ZIP junto al programa |

---

## Derechos de autor de las canciones de ejemplo

Las letras de las canciones **"Sound of You"** y **"Ghost of you"** son obra original de **Edgar Alessandro Chocon Oliva** (carné 202212978), igual que las grabaciones `ejemplos/Sound_of_You.mp3` y `ejemplos/Ghost_of_you_Remastered.mp3`, que el autor produjo con la herramienta Suno.

© 2026 Edgar Alessandro Chocon Oliva. **Todos los derechos reservados.**

Se incluyen en este proyecto **únicamente como material de ejemplo y de prueba** del Karaoke Inteligente. No se autoriza copiarlas, distribuirlas, interpretarlas públicamente ni usarlas con otro fin sin el permiso escrito del autor. La licencia del código del programa no se extiende a estas letras ni a estos audios.
