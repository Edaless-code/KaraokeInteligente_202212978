# Karaoke Inteligente · 202212978

**Autor:** Edgar Alessandro Chocon Oliva · Carné 202212978

Programa en **Python** que muestra la letra de las canciones **línea por línea, al ritmo del cantante**, para que el público pueda acompañarlo. La letra se guarda en una base de datos SQLite (`CANCIONES`).

- **Modo manual:** con 2 o 3 palabras que se escuchan, el programa identifica la canción y la línea, y se avanza con la tecla **c**.
- **Modo automático:** una IA gratuita y sin internet (**Vosk** + **Whisper**) escucha al cantante, limpia el sonido, identifica la canción, avanza la letra, se pausa sola y aprende canciones nuevas.

## Uso rápido

| Plataforma | Cómo |
|---|---|
| **Windows** | Descargue `KaraokeInteligente-Windows.zip` (*Releases* o *Actions → Ejecutable de Windows*), extráigalo y ejecute `KaraokeInteligente.exe` |
| **Código fuente** | `pip install -r requirements.txt` y luego `python main.py` |
| **Pruebas** | `python -m pytest` |

## Documentación

- [Manual de usuario](docs/MANUAL_USUARIO.md)
- [Manual técnico](docs/MANUAL_TECNICO.md)

## Derechos de autor

El código del programa es del autor. Las **letras y audios** de las canciones de ejemplo (*Sound of You* y *Ghost of you*) son obra original de **Edgar Alessandro Chocon Oliva**. © 2026, todos los derechos reservados. Ver [ejemplos/DERECHOS_DE_AUTOR.md](ejemplos/DERECHOS_DE_AUTOR.md).
