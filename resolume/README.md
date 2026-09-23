# Resolume (opcional, L5)

- Video: Resolume recibe la salida de TouchDesigner por Spout (Windows) o Syphon (macOS) como fuente.
- Control: el cerebro manda `/composition/layers/1/clips/{n}/connect 1` por OSC (puerto 7000)
  al cambiar de escena, según `resolume_clip` en `config/show.example.yaml`.
- Direcciones exactas y puerto a confirmar en Resolume (Preferences → OSC, y Shortcuts → Edit OSC).
