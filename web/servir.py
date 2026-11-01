"""Abre la versión web del Karaoke Inteligente en el navegador.

Uso:  python servir.py        (o doble clic en abrir.bat en Windows)

Sirve esta carpeta en http://localhost:8000 con soporte para "Range", que el
navegador necesita para adelantar o regresar la canción (el servidor simple
``python -m http.server`` no lo tiene y la pista siempre volvería al inicio).
Para detenerlo: Ctrl+C o cerrar la ventana.
"""

from __future__ import annotations

import http.server
import io
import os
import re
import socket
import sys
import webbrowser
from pathlib import Path

CARPETA = Path(__file__).resolve().parent


class Servidor(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mp3": "audio/mpeg",
                      ".webmanifest": "application/manifest+json"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(CARPETA), **kwargs)

    def send_head(self):
        rango = self.headers.get("Range")
        ruta = self.translate_path(self.path)
        if not rango or not os.path.isfile(ruta):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", rango)
        tamano = os.path.getsize(ruta)
        if not m or (not m.group(1) and not m.group(2)):
            return super().send_head()
        if m.group(1):
            inicio = int(m.group(1))
            fin = min(int(m.group(2)), tamano - 1) if m.group(2) else tamano - 1
        else:  # bytes=-N: los últimos N bytes
            inicio, fin = max(0, tamano - int(m.group(2))), tamano - 1
        if inicio >= tamano:
            self.send_error(416)
            return None
        with open(ruta, "rb") as archivo:
            archivo.seek(inicio)
            datos = archivo.read(fin - inicio + 1)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(ruta))
        self.send_header("Content-Range", f"bytes {inicio}-{fin}/{tamano}")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return io.BytesIO(datos)

    def log_message(self, *_):
        pass  # sin mensajes por cada archivo


def puerto_libre(preferido: int = 8000) -> int:
    for puerto in range(preferido, preferido + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", puerto)) != 0:
                return puerto
    return 0


def main() -> None:
    puerto = puerto_libre()
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), Servidor)
    direccion = f"http://localhost:{servidor.server_address[1]}"
    print(f"Karaoke Inteligente (web) en {direccion}")
    print("Para el modo automático use Chrome o Edge y permita el micrófono.")
    print("Para detenerlo: Ctrl+C o cierre esta ventana.")
    if "--sin-navegador" not in sys.argv:
        webbrowser.open(direccion)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
