# EMU y luces: qué es la EMU y cómo la vamos a usar

Estado 2026-09-23: investigación hecha sin el hardware a la mano. Todo lo marcado
VERIFICAR se confirma en L2 con la interfaz conectada.

## Qué es la "EMU"

EMU es el **software** gratuito de ENTTEC para controlar luces DMX (macOS y Windows).
No es una interfaz MIDI a DMX en sí; la interfaz física es un dispositivo ENTTEC que
EMU maneja: DMX USB Pro (70304), DMX USB Pro Mk2 (70314), EMU Hardware Interface (70681,
con USB-C, MIDI y Ethernet) o un nodo Art-Net (ODE Mk2/Mk3). El **Open DMX USB no es
compatible con EMU**.

Fuentes: [EMU, free vs premium](https://support.enttec.com/dmx-software/emu/emu-free-to-download-premium-is-optional),
[manual EMU 70680 (abril 2026)](https://cdn.enttec.com/pdf/assets/70680/manual/70680_EMU_USER_MANUAL.pdf),
[EMU Hardware Interface](https://support.enttec.com/user-manuals/emu-hardware-interface),
[MIDI en EMU](https://support.enttec.com/dmx-software/emu/midi).

## Lo que cambia el plan

1. **El control por MIDI en EMU es de pago.** La versión gratuita da 1 universo, salida
   Art-Net, Sound Tracker, importación GDTF y editor de fixtures. "MIDI control y el
   plugin VST3" están en la lista premium (licencia perpetua: USD 100 o 12 cuotas de 10).
2. **Aunque se pagara, MIDI en EMU no mapea "nota = canal DMX".** Las notas disparan
   Programs y Banks (escenas guardadas) o se asignan por MIDI Learn a faders internos.
   El manual dice además que EMU duplica el valor 0-127 para llegar a 0-255, así que se
   pierde la mitad de la resolución.
3. **EMU acepta un solo puerto MIDI y un solo canal a la vez.**

Conclusión: AVI **no pasa por EMU**. Manda DMX directo al hardware ENTTEC desde Python:

| Hardware que resulte ser | Backend en `avi/outputs/dmx.py` | Cómo |
|---|---|---|
| DMX USB Pro / Pro Mk2 o clon "Pro compatible" | `enttec_pro` | puerto serie `/dev/tty.usbserial-EN*`, protocolo del widget (label 6), pyserial |
| Nodo Art-Net (ODE, EMU Hardware por Ethernet, nodos chinos) | `artnet` | UDP 6454, ArtDmx, universo 0 |
| EMU Hardware Interface por USB-C | VERIFICAR | el manual dice que exige el software EMU; probar si expone un puerto serie tipo Pro |

EMU queda como herramienta auxiliar gratuita: editor de fixtures, monitor de DMX y
Art-Net (ventana Input) y actualizador de firmware. Su Sound Tracker es un plan B si el
cerebro cae en vivo.

## Qué hacemos en L2 cuando aparezca el hardware

1. Conectar la interfaz por USB. En la Mac: `ls /dev/tty.usbserial*` o
   `python scripts/dmx_probe.py --list`. Si aparece `usbserial-EN…`, es la familia Pro.
   Si no aparece nada por serie pero tiene Ethernet, va por Art-Net.
2. Poner cada luz en su modo de más canales (idealmente 8ch RGBW) con direcciones
   1, 9, 17, 25 (ajustar si el modo tiene otro número de canales).
3. Barrido: `python scripts/dmx_probe.py --sweep 1 8 --hold 3`. Nicolás dice qué hace
   la luz 1 en cada canal (nada / dimmer / rojo / verde / azul / blanco / strobe / modo).
4. Escala: `--channel <dimmer> --value 64|128|192|255` para confirmar que el brillo es
   gradual.
5. Escribir `config/fixtures.yaml` con perfil, direcciones y grupos confirmados.

## Luces

Modelo, número de canales y función por canal: VERIFICAR (Nicolás está buscando las
luces). Las PAR LED chinas genéricas casi siempre traen un modo de 7 u 8 canales con
dimmer, R, G, B, (W), strobe, modo y velocidad, en ese orden; es el supuesto de
`config/fixtures.example.yaml`.

## Nota sobre `scripts/emu_probe.py`

Se mantiene por si el hardware resultara ser una interfaz MIDI a DMX de otra marca (hay
cajas chinas que sí mapean nota a canal). Para hardware ENTTEC usar `dmx_probe.py`.
