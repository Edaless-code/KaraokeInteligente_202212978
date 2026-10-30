# 🎤 Karaoke Inteligente

**Autor:** Edgar Alessandro Chocon Oliva · **Carné:** 202212978

Muestra la letra de las canciones **línea por línea, al ritmo del cantante**, para que el público pueda acompañarlo aunque no se sepa la letra.

- **Modo manual:** escribes 2 o 3 palabras que escuchas; el programa identifica la canción y la línea, y avanzas con un toque o con la tecla **c**.
- **Modo automático:** una inteligencia artificial escucha al cantante, reconoce la canción y avanza la letra sola. Se pausa cuando nadie canta y aprende canciones nuevas.

---

## ⬇️ Descargar

Todo está en la página de **[Releases](https://github.com/Edaless-code/KaraokeInteligente_202212978/releases)**. Abre la versión más reciente y, en **Assets**, descarga:

| Plataforma | Archivo |
|---|---|
| 🪟 **Windows** | `KaraokeInteligente-Windows.zip` |
| 🤖 **Android** | `KaraokeInteligente-Android.apk` |

---

## 🪟 Ejecutar en Windows (.exe)

No hace falta instalar Python ni nada más.

1. Descarga **`KaraokeInteligente-Windows.zip`** desde [Releases](https://github.com/Edaless-code/KaraokeInteligente_202212978/releases).
2. Clic derecho sobre el ZIP → **Extraer todo…** (por ejemplo, en `C:\KaraokeInteligente`).
3. Abre la carpeta y haz doble clic en **`KaraokeInteligente.exe`**.
   - Si aparece *"Windows protegió su PC"*: **Más información → Ejecutar de todas formas**. Aparece porque el programa no está firmado digitalmente.
4. En el menú:
   - **`f` → `t` → Enter → Enter** carga las canciones de ejemplo.
   - **`m`** abre el modo manual y **`a`** el automático.

Requisitos: Windows 10 u 11 de 64 bits, unos 700 MB libres y un micrófono para el modo automático en vivo. Los modelos de voz ya vienen incluidos, así que funciona **sin internet**.

> **Probar el modo automático sin cantar:** `a` → `a` (archivo) → Enter → Enter → `s`. Reproduce *Sound of You* por las bocinas mientras la letra avanza sola.

## 🤖 Ejecutar en Android (APK)

1. En el teléfono, descarga **`KaraokeInteligente-Android.apk`** desde [Releases](https://github.com/Edaless-code/KaraokeInteligente_202212978/releases).
2. Ábrelo. Si Android lo pide, permite **"Instalar apps de origen desconocido"** para el navegador o el administrador de archivos.
3. Toca **Instalar** y luego **Abrir**.
4. Para tener canciones: **Biblioteca → + → Canciones de ejemplo**, o agrega las tuyas con **Pegar o escribir la letra**.
5. Para cantar: pestaña **Cantar → Modo manual** o **Modo automático**. La primera vez, el modo automático pide permiso de micrófono.

Requisitos: Android 7.0 o superior. Para el modo automático sin internet, conviene descargar el idioma en *Ajustes → Sistema → Idiomas → Reconocimiento de voz sin conexión* (el nombre exacto del menú cambia según la marca).

> **Probar el modo automático sin cantar:** *Más → Ajustes → Usar la demostración*.

---

## 💻 Ejecutar desde el código fuente (opcional)

```bash
git clone https://github.com/Edaless-code/KaraokeInteligente_202212978.git
cd KaraokeInteligente_202212978
pip install -r requirements.txt
pip install faster-whisper     # opcional: mejora el modo automático
python main.py                 # versión de consola (Windows/Linux/macOS)
python -m pytest               # 147 pruebas automáticas
```

App móvil en la computadora: `pip install kivy plyer` y luego `python movil/main.py`.

## 📚 Documentación

- [Manual de usuario](docs/MANUAL_USUARIO.md): instalación, cada opción y tecla, formato de los archivos, configuración y problemas frecuentes.
- [Manual técnico](docs/MANUAL_TECNICO.md): módulos, base de datos, cómo se resolvió el modo automático, pruebas, seguridad, escalabilidad y suposiciones.

## ©️ Derechos de autor

Las **letras y audios** de las canciones de ejemplo (*Sound of You* y *Ghost of you*) son obra original de **Edgar Alessandro Chocon Oliva**. © 2026, todos los derechos reservados. Ver [ejemplos/DERECHOS_DE_AUTOR.md](ejemplos/DERECHOS_DE_AUTOR.md).
