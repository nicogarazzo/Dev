# Prompts para tu LLM local

Cada archivo es un prompt listo para pegar. Todos terminan con un `git push` a una rama
`local/...`, para que el siguiente paso en cloud lo use sin que copies nada a mano.

| Prompt | Cuándo | Resultado |
|---|---|---|
| `L1_setup_entorno.md` | Ya | `config/local.yaml` (audio, puertos MIDI, versión de TD) |
| `L2_mapear_emu_y_luces.md` | Después de L1 | `config/fixtures.yaml` + `docs/hardware/emu_y_luces.md` |
| `L3` calibrar audio | Después de F1 | Se escribe cuando exista el analizador |
| `L4` TouchDesigner + prueba integrada | Después de F3 y F5 | Se escribe cuando existan las salidas y el script de TD |
| `L5` Resolume (opcional) | Después de L4 | Se escribe si decides usar Resolume |
