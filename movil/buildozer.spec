[app]
title = Karaoke Inteligente
package.name = karaokeinteligente
package.domain = gt.edu.usac.edgarchocon
source.dir = .
source.include_exts = py,png,jpg,kv,ttf,txt,md
source.exclude_dirs = bin,.buildozer,__pycache__,karaoke/audio,karaoke/ui
source.exclude_patterns = karaoke/simulacion.py,karaoke/app.py,karaoke/__main__.py
version = 1.0.0
# Solo dependencias livianas: el núcleo del karaoke no necesita NumPy en Android
# (la voz la reconoce el propio teléfono).
# charset-normalizer fijo en 3.4.0: las versiones nuevas publican ruedas solo
# para Android que python-for-android no logra instalar (la 3.4.0 es Python puro).
requirements = python3,kivy==2.3.1,plyer==2.1.0,pyjnius,charset-normalizer==3.4.0
icon.filename = %(source.dir)s/recursos/icono.png
presplash.filename = %(source.dir)s/recursos/presplash.png
android.presplash_color = #0B1220
orientation = portrait
fullscreen = 0

# Único permiso: el micrófono (modo automático).
android.permissions = RECORD_AUDIO
# Android 11+ exige declarar que la app consulta el servicio de reconocimiento de voz.
android.extra_manifest_xml = ./recursos/consultas_voz.xml
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
android.release_artifact = apk
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 0
