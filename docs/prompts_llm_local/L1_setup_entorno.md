# L1 — Preparar el entorno local

Copia todo lo que está debajo de la línea y pégalo en tu LLM local (con acceso a terminal).

---

Eres mi asistente en mi computador. Tienes acceso a la terminal. Haz tú todos los pasos;
solo pídeme algo cuando sea físicamente imposible hacerlo sin mí (por ejemplo, aceptar
un instalador gráfico). Háblame en español, con pasos numerados, y dime al final de cada
paso "paso N de 6 hecho".

Contexto: estoy montando AVI, un programa en Python que escucha la música que suena en
mi computador, la analiza por bandas de frecuencia y controla luces DMX (a través de una
interfaz MIDI→DMX marca EMU) y visuales en TouchDesigner. El código vive en
https://github.com/nicogarazzo/Dev.

Pasos:

1. Detecta mi sistema operativo (Windows o macOS) y su versión. Usa eso para el resto.
2. Clona `https://github.com/nicogarazzo/Dev` en `~/AVI` (o haz `git pull` si ya existe),
   instala Python 3.11 o 3.12 si no está, crea un entorno virtual `.venv` dentro del repo
   y ejecuta `pip install -e ".[dev]"`. Corre `pytest` y muéstrame el resultado.
3. Audio de loopback (para que AVI "escuche" lo que suena en el computador):
   - Windows: instala **VB-Audio Virtual Cable** (VB-CABLE).
   - macOS: instala **BlackHole 2ch** (`brew install blackhole-2ch`) y crea un
     "Dispositivo de salida múltiple" (altavoces + BlackHole) en Configuración de Audio MIDI.
   Luego lista los dispositivos de entrada con
   `python -c "import sounddevice as sd; print(sd.query_devices())"` y dime cuál es el loopback.
4. Puertos MIDI virtuales `AVI Out` y `AVI In`:
   - Windows: instala **loopMIDI** y crea dos puertos con esos nombres exactos.
   - macOS: activa el **IAC Driver** en Configuración de Audio MIDI y crea dos buses
     con esos nombres.
   Verifica con `python -c "import mido; print(mido.get_output_names()); print(mido.get_input_names())"`.
   Conecta la interfaz EMU por USB y confirma que aparece en esa lista; copia su nombre exacto.
5. Instala **TouchDesigner** (versión gratuita, non-commercial) desde derivative.ca si no
   está. No hace falta abrir ningún proyecto todavía.
6. Crea el archivo `config/local.yaml` en el repo con:
   ```yaml
   os: <windows|macos> <versión>
   audio_input: "<nombre exacto del dispositivo loopback>"
   emu_midi_port: "<nombre exacto del puerto MIDI de la EMU>"
   midi_out_virtual: "AVI Out"
   midi_in_virtual: "AVI In"
   controller_midi_port: "<nombre de mi controlador MIDI si hay uno conectado, o null>"
   touchdesigner_version: "<versión instalada>"
   ```
   Luego crea la rama `local/setup-entorno`, haz commit de `config/local.yaml` y `git push -u origin local/setup-entorno`.
   Termina diciéndome: "L1 listo, rama local/setup-entorno subida".
