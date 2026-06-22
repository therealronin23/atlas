# MCP trunk + ecosistema de extensión — mapa del sistema

Índice de "qué hay y cómo se usa". Estado vivo en `WORK_LEDGER.md`; diseño/porqué en
`mcp_trunk_portable.md` + `mcp_sector_architecture_audit.md`. Aquí solo el MAPA.

## Idea en una frase

Una sola conexión (`atlas-trunk`) que frontea TODO el trabajo y el ecosistema,
clasificado por **dominio humano** y por **línea (kind)**, navegable sin manual,
seguro (lo externo se conecta/instala solo tras prove-it + veto + consentimiento).

## Las 2 capas

```
TRONCO (atlas-trunk, 1 conexión MCP, lazy)
 ├─ navegación por DOMINIO:  trunk_sectors → trunk_subsectors → trunk_tools
 ├─ navegación por LÍNEA:    trunk_kinds → trunk_catalog(kind|sector)
 ├─ salto directo:           trunk_find("seguridad"|"figma"|…)  (alias, madurez-first)
 ├─ ejecutar:                trunk_invoke(tool, args)   → McpRegistry (Merkle+SentinelGate)
 └─ saber:                   get_skill / list_skills    (servido, sin descarga)
RAÍCES nativas (hijas del tronco, vía catálogo): atlas-memory · atlas-operating · atlas-knowledge
```

## Las 11 LÍNEAS (kinds) y su `mode`

| Línea | mode | Cómo entra | Módulo/seeder |
|---|---|---|---|
| mcp | connected | el tronco lo spawnea | `registry_seed` (registro oficial) |
| skill | served/installed | `get_skill` o `npx skills add` | `skills_seed` (GitHub) |
| api | served | envuelta en knowledge-src | `line_seed.ApisGuruSource` |
| tool | installed | gestor de paquetes | `line_seed` (manual/awesome) |
| prompt·command | served | plantilla / slash-command | `line_seed.GithubLineSource` |
| hook·subagent·plugin·rule·workflow | installed | config del cliente | `line_seed.GithubLineSource` |

## Catálogos (datos)

- `mcp_catalog.yaml` — CURADO: taxonomía (9 dominios × subsectores + alias) + lo nuestro
  (instalado) + lo verificado (`everything`, `vercel-react-best-practices`).
- `mcp_catalog.md` — narrativa humana.
- `mcp_catalog_seeded.yaml` (100 mcp) · `mcp_catalog_skills_seeded.yaml` (9) ·
  `seeded/*.yaml` (615 de 9 líneas) — MÁQUINA-GENERADO, candidato/uncategorized + procedencia.
- `mcp_catalog_classified.yaml` — los 724 sembrados auto-clasificados a dominio (browse poblado).

## Cadena de suministro por línea (el flujo)

```
DESCUBRIR (seeder)  →  SEMBRAR (candidato + procedencia)  →  CLASIFICAR (classify, por alias)
   →  prove-it  →  VERIFICAR (status=verificado, veto SentinelGate)  →  CONSENTIR (externo)
   →  CONECTAR/INSTALAR/SERVIR (por mode)  →  VIVO en su sector
```
Scripts: `mcp_seed_registry.py` · `mcp_seed_skills.py` · `mcp_classify_seeded.py` · `mcp_install.py`.

## Modelo de seguridad (invariante)

- Los **candidatos solo se navegan** (browse). Nunca se conectan/instalan.
- Conectar/instalar exige: `status=verificado` (prove-it) + veto `SentinelGate` (metachars/IOC) +
  **consentimiento explícito** para código de terceros. Auditoría Merkle en cada call.
- "Verificable" = procedencia + grounding, NO prueba de verdad.

## Cómo añadir algo nuevo (receta)

1. ¿Ya sembrado? mira `seeded/`/`classified`. Si no: corre el seeder de su línea.
2. prove-it (ejecútalo/léelo una vez). 3. Márcalo `verificado` (+ `install`, sector) en `mcp_catalog.yaml`.
4. Si es externo: consentimiento. 5. El tronco lo absorbe en su sector automáticamente.
