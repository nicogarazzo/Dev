"""F3 - Salidas: traduce el ShowState a intenciones para el patch (luces) y a OSC
(TouchDesigner, Resolume), con modo --dry-run.

dmx.py (hecho en PR #3): salida DMX directa a hardware ENTTEC (EnttecProBackend por
serie, ArtNetBackend por UDP, NullBackend para tests). "EMU" es software; no se usa.

Pendiente. Contrato de direcciones y puertos en docs/PLAN_MVP.md, seccion 7.
"""
