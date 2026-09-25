"""F4 - UI web local (http://localhost:8080).

Hoy: el Monitor con estetica TRON (`avi ui`): espectro con los rangos que cada
rastreador esta siguiendo, niveles y golpes por instrumento, vista previa de las
luces (PAR + canales DMX) y de los visuales, sincronizado a la musica.
Modos: demo (cancion de prueba), --file y --live (SSE). `--export` deja un HTML
autocontenido.

Pendiente (pestanas marcadas F4): dispositivos, perfiles (Open Fixture Library),
patch y probar/identificar. Ver docs/PLAN_MVP.md, seccion 5.
"""
from .server import export_html, serve

__all__ = ["export_html", "serve"]
