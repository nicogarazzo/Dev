# AVI

Un solo cerebro que escucha la música y dirige, de forma autónoma, las luces
(DMX directo a tu interfaz ENTTEC) y los visuales (TouchDesigner) con los mismos colores y el mismo pulso.
Los filtros son adaptativos (cada instrumento se rastrea en el espectrograma) y el hardware se configura desde una UI web local.

- Plan completo: [`docs/PLAN_MVP.md`](docs/PLAN_MVP.md)
- Prompts para tu LLM local: [`docs/prompts_llm_local/`](docs/prompts_llm_local/)

| Carpeta | Qué va ahí | Fase |
|---|---|---|
| `avi/audio` | Análisis adaptativo por instrumento (hecho) | F1 |
| `avi/brain` | Secciones, escenas, paleta → `ShowState` | F2 |
| `avi/patch` | Perfiles, fixtures, grupos con delay, salidas DMX | F3 |
| `avi/outputs` | `dmx.py` (ENTTEC USB Pro / Art-Net, hecho); ShowState → patch (luces) y OSC (TouchDesigner) | F3 |
| `avi/ui` | UI web local: configurar, probar y monitorear hardware | F4 |
| `avi/control` | Controlador MIDI de entrada (overrides) | F5 |
| `touchdesigner/` | Script que construye la red de TD + reproductor de clips (mini Resolume) | F5 |
| `puredata/` | Puente opcional para tu prototipo Pd | — |
| `config/` | Rastreadores, luces y escenas (YAML); `local.yaml` = tu Mac | — |
| `scripts/` | `dmx_probe.py`, `audio_probe.py`: sondeo de hardware y audio | L2 |
| `docs/hardware/` | Qué es la EMU y cómo se mapea el hardware | L2 |

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest

avi synth out/toy.wav --seconds 30 --bpm 126   # cancion de juguete: calm -> build -> drop
avi analyze out/toy.wav --out out/timeline.json # un frame por espectro: niveles, golpes, BPM, rango de cada rastreador
avi live --device "VB-Cable"                    # lo mismo en vivo sobre el loopback (config/local.yaml)
```

Cada frame del analizador (`AnalysisFrame`) trae, por instrumento, `level` 0-1, `onset`, el rango `hz`
que el rastreador esta capturando ahora y su `confidence`, mas `bpm`, `beat`, `bar` y `phrase_pos`.
