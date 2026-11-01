@echo off
rem Abre la version web del Karaoke Inteligente en el navegador.
cd /d "%~dp0"
where py >nul 2>nul && (py servir.py & goto :eof)
where python >nul 2>nul && (python servir.py & goto :eof)
echo No se encontro Python. Instalelo desde https://www.python.org/downloads/ y vuelva a intentarlo.
pause
