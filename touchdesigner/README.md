# TouchDesigner (F5 + L4)

Aquí irá `build_avi_network.py`: un script que pegas en el Textport de TouchDesigner
y que construye la red completa, en vez de versionar un `.toe` binario.

Red prevista:
1. `OSC In CHOP` en el puerto 9000 recibiendo `/avi/*` (contrato en `docs/PLAN_MVP.md` §6).
2. `Select` + `Lag` CHOPs por banda → exportados a parámetros de cada escena.
3. `/avi/color/1..3` → `Constant`/`Ramp` TOPs compartidos por todas las escenas.
4. 3 escenas (ambiente, subida, drop) → `Switch TOP` indexado por `/avi/scene`.
5. Reproductor de clips propios (`Movie File In TOP` por escena, controlado por `/avi/clip`): nuestro "mini Resolume".
6. Salida a pantalla.
