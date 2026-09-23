"""F3 - Patch de hardware: perfiles de luces, fixtures, grupos con delay y salidas DMX.

El cerebro habla de intenciones (dimmer, color, strobe) sobre grupos; esta capa las
traduce a canales DMX segun config/fixtures.yaml y las envia por un DmxOutput
(avi/outputs/dmx.py: ENTTEC DMX USB Pro por serie, Art-Net por UDP, Null para tests).

Pendiente. Ver docs/PLAN_MVP.md, seccion 5.
"""
