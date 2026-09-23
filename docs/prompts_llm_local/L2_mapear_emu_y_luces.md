# L2 — Identificar tu interfaz ENTTEC y mapear los canales de tus luces

> Nota v3: "EMU" es el software gratuito de ENTTEC, no una caja MIDI → DMX. AVI manda
> DMX directo al hardware ENTTEC (ver `docs/hardware/emu_y_luces.md`). Este paso lo hace
> Claude en tu Mac por Remote Control; el prompt queda de respaldo para tu LLM local.

Requiere L1 hecho, la interfaz conectada por USB (o por red si es un nodo Art-Net) y las
luces encendidas y enlazadas por cable DMX. Copia lo de abajo y pégalo en tu LLM local.

---

Eres mi asistente en mi Mac, con acceso a terminal y al repo `~/dev/AVI`
(https://github.com/nicogarazzo/Dev). Hazlo tú todo; yo solo miro las luces y te digo
qué pasa. Háblame en español, con pasos numerados, "paso N de 5 hecho" al final de cada uno,
y hazme **una sola pregunta a la vez**, con respuestas cortas (sí/no o un número).

Objetivo: llenar `config/fixtures.yaml` (a partir de `config/fixtures.example.yaml`) y el
bloque `dmx:` de `config/local.yaml` con datos confirmados.

Pasos:

1. **Identificar la interfaz.** Pídeme el modelo impreso en la interfaz ENTTEC. Corre
   `python scripts/dmx_probe.py --list`. Si aparece `/dev/tty.usbserial-EN…`, el backend
   es `enttec_pro` y ese es el `serial_port`. Si no aparece nada por serie pero la
   interfaz tiene Ethernet, el backend es `artnet` (pídeme la IP o usa broadcast).
   Escribe eso en `config/local.yaml → dmx:`.
2. **Direcciones DMX.** Pídeme el modelo de las luces y cuántas tengo. Dime qué botones
   pulsar en cada luz para dejarla en el modo de más canales (idealmente 8ch RGBW) y con
   dirección de inicio: luz 1 = 1, luz 2 = 9, luz 3 = 17, luz 4 = 25 (sumar el número
   de canales del modo por luz). Espera a que te confirme.
3. **Barrido de canales.** Corre `python scripts/dmx_probe.py --sweep 1 8 --hold 3` y,
   canal por canal, pregúntame qué hizo la luz 1 (nada / dimmer / rojo / verde / azul /
   blanco / strobe / modo). Con eso arma el perfil (`profiles:`) en `config/fixtures.yaml`.
4. **Escala y verificación.** Corre `--channel <dimmer> --value 64`, `128`, `192`, `255`
   y pregúntame si el brillo sube de forma gradual. Luego manda rojo puro a la luz 2 y
   confirma que la dirección 9 es correcta. Termina con `--blackout`.
5. **Guardar y subir.** Escribe `config/fixtures.yaml` (perfiles, fixtures con dirección y
   output, grupos `all`, `front`, `back`) y completa `docs/hardware/emu_y_luces.md` con
   modelos y tabla de canales. Crea la rama `local/mapa-hardware`, haz commit y
   `git push -u origin local/mapa-hardware`.
   Termina diciéndome: "L2 listo, rama local/mapa-hardware subida".
