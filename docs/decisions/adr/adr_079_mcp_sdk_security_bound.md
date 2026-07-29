# ADR-079 — Acotar el SDK `mcp` a `>=1.28.1,<2` por advisories con exposición cero

- **Estado:** aceptado por el operador
- **Fecha:** 2026-07-29
- **Programas:** P07, P09
- **Refina:** invariante 6 (`AGENTS.md`) — cambio de restricción de dependencia

## Contexto

La revalidación del 2026-07-29 encontró que `pip-audit` sale con exit 1 sobre
el entorno: **3 advisories conocidas en `mcp` 1.23.3**, el SDK del que depende
todo el tronco MCP.

| Advisory | Fix | Requiere para ser explotable |
|---|---|---|
| PYSEC-2026-3481 | 1.27.2 | `server.experimental.enable_tasks()` |
| PYSEC-2026-3482 | 1.27.2 | SSE o Streamable HTTP **con** autenticación |
| PYSEC-2026-3483 | 1.28.1 | `mcp.server.websocket.websocket_server` |

**Exposición verificada: CERO.** Comprobada contra el código, no asumida:

- `enable_tasks` — sin usos en `src/` ni `tests/`.
- `websocket_server` / `mcp.server.websocket` — sin usos.
- SSE / Streamable HTTP — sin usos. El tronco es **stdio only**
  (`src/atlas/mcp/trunk_server.py:503` documenta la entrada stdio;
  `FastMCP.run()` sin transporte es stdio).

Por tanto no hay urgencia operativa. La razón para actuar es defensa en
profundidad: el SDK es la frontera con código de terceros, justo la superficie
que ADR-072/075/077 tratan como no confiable, y una futura entrada por HTTP
haría explotable lo que hoy no lo es.

`pyproject.toml` declaraba `mcp>=1.2`. Esa restricción es el problema real:
hoy resuelve a **2.0.0**, versión mayor en la que el transporte WebSocket
**se eliminó por completo**. Un `uv lock --upgrade` desprevenido habría metido
un cambio de ruptura sin decisión.

Se registra además un hecho durable del entorno: **`pip-audit --strict` no
puede pasar en este checkout aunque haya cero vulnerabilidades**, porque trata
"no auditable" como fallo y `atlas-core` (local, 0.12.0) no está en PyPI.
Cualquier documento que afirme `pip-audit --strict | PASS` es sospechoso por
construcción.

## Decisión

1. Acotar la restricción a **`mcp>=1.28.1,<2`**. El suelo cierra las tres
   advisories; el techo impide que una resolución silenciosa cruce a la v2 y su
   ruptura de transportes.
2. Refrescar el lock sólo de ese paquete (`uv lock --upgrade-package mcp`), sin
   arrastrar el resto del árbol de dependencias.
3. Cruzar a `mcp>=2` es una decisión **separada**, con su propio ADR, porque
   cambia el contrato de transportes.
4. El invariante 6 queda satisfecho por este ADR: no es dependencia nueva, pero
   sí cambio de restricción, y se decide explícitamente.

## Hallazgo no previsto: `semgrep` pinnea `mcp==1.23.3`

Al instalar, `pip` avisó: `semgrep 1.171.0 requires mcp==1.23.3, but you have
mcp 1.29.0`. Se verificó en vez de asumir:

- `semgrep` **no está** en `pyproject.toml` ni en `uv.lock` — se instaló al
  margen del gestor, así que `uv` no lo ve al resolver.
- Atlas lo invoca como **binario en subproceso**
  (`src/atlas/mcp/candidate_static_scan.py:27`, `_semgrep_binary()`), nunca
  como import de Python.
- Probado con `mcp` 1.29.0 ya instalado: `semgrep --version` → exit 0, y un
  escaneo real `--config p/python --json` → exit 0 con JSON válido.

Conclusión: el conflicto es de **metadatos declarados**, no funcional. semgrep
sólo necesita `mcp` para su propio servidor MCP, que Atlas no usa. Queda
registrado porque un `pip check` futuro volverá a sacarlo y no debe
reinvestigarse desde cero. Deuda declarada: semgrep es tooling fuera del
gestor de dependencias; si algún día se mete en `pyproject`, este pin exacto
entrará en conflicto de verdad con el suelo de este ADR.

## Consecuencias

- `pip-audit` (sin `--strict`) pasa a 0 vulnerabilidades.
- La superficie de transporte no cambia: Atlas sigue stdio-only. La subida no
  activa ninguna protección por sí sola en los transportes HTTP, porque no se
  usan.
- Si algún día se expone un servidor MCP propio por SSE o Streamable HTTP,
  **esta subida es requisito previo, no opcional**, y habrá que poblar
  `AccessToken.subject` en el verificador de tokens (ver PYSEC-2026-3482).
- El techo `<2` habrá que revisarlo cuando la v2 se evalúe de verdad; queda
  como deuda declarada, no como olvido.

## Verificación exigida

Suite completa, mypy, `atlas reality --run-checks --include-browser` y
`pip-audit` tras el refresco. Si algo se rompe: revertir el lock y no parchear
código de producto para que pase.
