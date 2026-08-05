<!-- GENERADO por atlas handoff 2026-08-05T21:00:39.065124+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-05 (cierre) — el lazo de autoconstrucción llevaba 24 días parado
  por TRES capas encadenadas; cada una tapaba a la siguiente.**
  **Capa 1 — gate CVE (24 días)**: 171 `preflight_blocked`, todos por 4 CVEs
  (aiohttp ×3, cryptography ×1). Bloqueo mutuo: el gate apaga el lazo → el
  lazo propone los bumps → los bumps piden aprobación humana → sin aprobación
  los CVEs siguen abiertos. La prueba estaba en el árbol: el bump
  `click>=8.4.2` llevaba días sin commitear, con su `.rej` al lado. Cerrado
  (`7c443c6`): `preflight_blocked` 171 → 0. Trampa que casi me engaña: el
  suelo `cryptography>=49.0.0` YA permitía 50.0.0 — el CVE seguía abierto
  porque nadie subió la versión INSTALADA. Mirar `pip list`, no sólo
  `pyproject.toml`.
  **Capa 2 — el gate de presupuesto, arreglado por la mañana pero inerte**:
  al analizar los 48 fallos del lazo, 15 (31%) eran `unknown provider:
  openrouter_mistral_large` — el bug de `17da201`. El daemon llevaba
  corriendo desde el 4-ago con el módulo viejo en memoria. Reiniciado a las
  17:39; el primer worktree nuevo apareció sobre el commit del día.
  **Capa 3 — crédito L2, que NO es código**: el primer item tras el reinicio
  falló con `402: requested 4096 tokens, can only afford 3767`.
  **Corrección de un diagnóstico mío**: dije "confirmado, un 402 tumba toda
  la petición". FALSO — mi prueba mezclaba un proveedor L1 en una petición
  L2, así que nunca fue candidato. Repetida bien: el fallback SÍ funciona.
  **NVIDIA degradado** (`5d694fd`): el smoke los mata con `TimeoutError tras
  30s`, no con 404 — el discovery los ve LISTADOS. Es el patrón NIM que su
  propio docstring advierte. Criterio de retirada cumplido (el que fijó
  `provider_smoke.py` el 23-jul): `nvidia_glm` último día vivo 08-02,
  `nvidia_mistral_medium` 08-01. DOWN, no borrados: parpadean. El Cónclave
  baja a 4 asientos y eso lo ARREGLA — ese asiento colgaba la deliberación
  30-120s por ronda para devolver `reachable=False`.
  **OpenRouter a la cuenta 2, con un hallazgo que lo invalida en la
  práctica**: `account_pool` coge la primera variable que EXISTA, sin rotar
  ante fallo, así que invertir el orden es todo el cambio. Hecho y probado.
  PERO al verificarlo contra `/api/v1/key`: **las dos claves son la MISMA**
  — mismo label `sk-or-v1-a87...405`, mismo consumo `0.02355418`. El
  mecanismo queda listo; hace falta que el operador ponga ahí la clave de
  otra cuenta real.
  **Dos defectos de la SUITE encontrados de paso**: (1) el fixture autouse
  reponía `status=OK` a todos los proveedores, borrando un DOWN *declarado*
  — confundía estado de runtime con declaración de catálogo; (2) el
  scrubbing de claves no cubría las NUMERADAS del `account_pool`
  (`OPENROUTER_API_KEY_2`, `NVIDIA_API_KEY_2..8`), así que un test que
  llegara al camino del pool podía usar una clave REAL del `.env` y hacer una
  llamada REAL. Los dos arreglados.
  **Worktrees**: 4 fugados del 3-ago. Barridos los 2 limpios; los 2 con
  cambios NO se tocan — contienen trabajo del lazo que nunca aterrizó,
  incluido `tests/test_browser_action.py`, que no existe en ningún otro sitio.
  **Decisiones que quedan y son del operador**: invariante CVE-HITL
  (¿auto-aplicar bumps que sólo cierran un CVE?), crédito/cuenta real de
  OpenRouter, y transporte MCP remoto.
