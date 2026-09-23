# L2 — Descubrir cómo tu EMU convierte MIDI en DMX y qué canales usan tus luces

Requiere L1 hecho. Necesitas las luces conectadas por cable DMX a la EMU y encendidas.
Copia todo lo que está debajo de la línea y pégalo en tu LLM local.

---

Eres mi asistente en mi computador, con acceso a terminal y al repo `~/AVI`
(https://github.com/nicogarazzo/Dev). Hazlo tú todo; yo solo miro las luces y te digo
qué pasa. Háblame en español, con pasos numerados, "paso N de 5 hecho" al final de cada uno,
y hazme **una sola pregunta a la vez**, con respuestas cortas (sí/no o un número).

Objetivo: llenar `config/fixtures.yaml` (a partir de `config/fixtures.example.yaml`)
con datos confirmados. Tengo una interfaz MIDI→DMX marca EMU y luces LED chinas genéricas.
No conocemos cómo la EMU traduce MIDI a canales DMX.

Pasos:

1. **Identificar hardware.** Pídeme que te diga (o fotografíe) el modelo escrito en la EMU
   y en las luces, y cuántas luces tengo. Busca en internet sus manuales y dime:
   modos de canales de cada luz (3/4/7/8 canales) y qué hace cada canal; cómo la EMU
   mapea MIDI a DMX si el manual lo dice.
2. **Direcciones DMX.** Dime exactamente qué botones pulsar en cada luz para dejarla en
   el modo de más canales (idealmente 8ch RGBW) y con esta dirección de inicio:
   luz 1 = 1, luz 2 = 9, luz 3 = 17, luz 4 = 25 (sumar 8 por luz; ajusta si el modo
   tiene otro número de canales). Espera a que te confirme.
3. **Barrido de notas.** Escribe un script `scripts/emu_probe.py` con `mido` que abra el
   puerto de la EMU (nombre en `config/local.yaml`) y, uno por uno, envíe:
   note_on canal 1, nota N, velocity 127 durante 2 s y luego note_off, para N = 0..9.
   Antes de cada nota pregúntame qué cambió en la luz 1 (nada / se encendió / color rojo /
   verde / azul / blanco / strobe). Si nada responde con notas, repite con
   control_change (CC N = 127) y después prueba canal MIDI 2. Con esto deduce:
   modo (`note` o `cc`), qué nota corresponde al canal DMX 1 (`dmx_offset`) y cómo
   se pasa a canales > 128 (`midi_channel_base`).
4. **Escala de valor.** Envía al canal del dimmer velocity 32, 64, 96, 127 y pregúntame
   si el brillo cambia de forma gradual. Confirma que `value_scale: 2` tiene sentido.
5. **Guardar y subir.** Escribe `config/fixtures.yaml` con todo lo confirmado (quita las
   marcas VERIFICAR que ya confirmaste; deja las que no) y un resumen en
   `docs/hardware/emu_y_luces.md` (modelos, modos, direcciones, tabla nota→canal).
   Crea la rama `local/mapa-hardware`, haz commit de `config/fixtures.yaml`,
   `docs/hardware/emu_y_luces.md` y `scripts/emu_probe.py`, y `git push -u origin local/mapa-hardware`.
   Termina diciéndome: "L2 listo, rama local/mapa-hardware subida".
