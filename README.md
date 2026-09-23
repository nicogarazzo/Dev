# AVI

Un solo cerebro que escucha la música y dirige, de forma autónoma, las luces
(MIDI → EMU → DMX) y los visuales (TouchDesigner / Resolume) con los mismos colores y el mismo pulso.

- Plan completo: [`docs/PLAN_MVP.md`](docs/PLAN_MVP.md)
- Prompts para tu LLM local: [`docs/prompts_llm_local/`](docs/prompts_llm_local/)

| Carpeta | Qué va ahí | Fase |
|---|---|---|
| `avi/audio` | Análisis de audio por bandas | F1 |
| `avi/brain` | Secciones, escenas, paleta → `ShowState` | F2 |
| `avi/outputs` | MIDI a la EMU, OSC a TouchDesigner y Resolume | F3 |
| `avi/control` | Controlador MIDI de entrada (overrides) | F4 |
| `touchdesigner/` | Script que construye la red de TD | F5 |
| `resolume/` | Notas de integración con Resolume | L5 |
| `puredata/` | Puente opcional para tu prototipo Pd | — |
| `config/` | Bandas, luces y escenas (YAML) | — |

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
