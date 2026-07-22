# Supply-chain admission scan (A1)

- Estado: A1 construido; A2 aporta `PluginManifest`/admisión staged opcional.
  **No hay activación runtime ni recibo Merkle todavía.**
- Autoridad de decisión: [ADR-072](../decisions/adr/adr_072_supply_chain_admission_scan.md).
- API: `atlas.security.supply_chain.SupplyChainScanner`.

## Propósito y frontera

`SupplyChainScanner.scan(root, catalog=...)` inspecciona un árbol local ya
materializado. Nunca instala, importa, ejecuta, resuelve paquetes ni hace red.
Devuelve siempre un `SupplyChainReport` terminal:

| Estado | Veredicto | Significado |
| --- | --- | --- |
| `complete` | `admit` / `review` / `block` | Se recorrió el alcance acotado. |
| `partial` | `block` | Un límite, una lectura o un manifest impidió evidencia completa. |
| `failed` | `block` | No había raíz local legible para observar. |

El resultado no concede ejecución. Un escaneo vale exclusivamente para los
bytes que hasheó; una mutación exige una nueva corrida.

## Qué observa A1

- Ficheros regulares bajo la raíz, con SHA-256 y tamaño; `.git`,
  `node_modules`, entornos virtuales y cachés conocidos se omiten.
- Enlaces simbólicos como hallazgo bloqueante, sin seguirlos.
- Paquetes y dependencias declaradas de npm, Python y Go. Los scripts de
  ciclo de vida npm se nombran como hallazgo, sin exponer ni ejecutar sus
  comandos.
- Indicadores pinneados por el consumidor: igualdad exacta tras normalización
  PEP 503 para Python y minúsculas para los demás ecosistemas. El digest del
  catálogo no depende del orden de sus entradas.
- Límites configurables de fichero, bytes y reloj. Un corte es visible en
  `diagnostics`, nunca una admisión incompleta.

El JSON Schema canónico es `schemas/supply_chain_report.schema.json`; el
modelo rechaza campos extra tanto en la raíz como anidados. `record_id` es
estable entre árboles con el mismo contenido; `scan_id`, raíz y tiempos son
identidad de corrida y no forman parte de ese registro.

## A2 — admisión declarativa construida

`PluginAdmissionGate` ya exige un hijo de staging explícito, `atlas-plugin.json`
estricto, revalidación de hashes y contribuciones Markdown sin ejecución.
`TrialGate` sólo usa esa admisión si recibe gate + resolver de raíz; de fábrica
omite plugins y otros artefactos remotos. Ver
`docs/design/plugin_manifest_v1.md` y ADR-073.

## A3 — obligatorio antes de instalar o activar

1. Materializar la fuente en staging nuevo y no ejecutable; fijar origen y
   revisión/contenido antes del escaneo.
2. Correr el escáner sobre ese staging y conservar el reporte completo.
3. Rechazar `block`; exigir decisión humana explícita para `review`; jamás
   convertir un `partial` en `admit` por reintento implícito.
4. Revalidar `PluginManifest` y la política de contribuciones después de cada
   mutación de staging; nunca reutilizar un `record_id` sobre bytes nuevos.
5. Antes de cualquier instalación, activación o efecto externo, crear el
   registro Merkle y pasar por el broker de aprobación aplicable. La ejecución
   posterior seguirá pasando por sandbox/AST Guard, no por este escáner.
6. Persistir procedencia, `record_id`, decisión humana y resultado de trial;
   permitir revocación y borrado del staging sin tocar el árbol principal.

## Verificación A1

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_supply_chain_scan.py \
  tests/test_supply_chain_report_schema.py \
  tests/test_os_event_schema.py -q
MYPYPATH=src .venv/bin/python -m mypy \
  src/atlas/security/supply_chain.py \
  src/atlas/security/supply_chain_models.py
```

La suite A1 cubre recorridos npm/Python/Go, hashes, identidad estable,
symlinks, los cuatro límites, scripts npm sin ejecución, indicadores exactos,
malformación fail-closed y paridad Schema/Pydantic.
