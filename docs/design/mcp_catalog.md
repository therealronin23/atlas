# Catálogo de skills / tools / MCP servers (candidatos)

<!-- Extraído del volcado Grok (docs/archive/_graveyard/2026-06-21/scratch/mcp grok.md), 2026-06-21.
     Insumo para el instalador automático del MCP trunk (docs/design/mcp_trunk_portable.md). -->

**AVISO HONESTO:** todo lo de aquí es **UNVERIFICADO** — son nombres de un transcript de Grok con
fuentes de blog/Reddit/Medium. Grok hizo búsqueda real, pero antes de **depender** de cualquiera se
verifica que el repo/skill existe y funciona (prove-it). **NO se instala todo** (kitchen-sink): el
instalador resuelve+instala **bajo demanda** lo que se gana su sitio (`wire-before-claim`). Estado por
defecto: `candidato`. Pasa a `verificado` cuando se comprueba el repo, y a `instalado` cuando entra.

## Claude — skills

| Skill | Para qué | Relevancia para nosotros | Estado |
|---|---|---|---|
| Document skills (PDF/DOCX/PPTX/XLSX, oficiales) | leer/generar ofimática | media (paper, reportes) | candidato |
| Skill-Creator (meta) | crear skills | alta (auto-evolución) | candidato |
| MCP Builder (meta) | crear servers MCP | **alta** (construir el tronco/raíces) | candidato |
| Andrej Karpathy's Guidelines | reglas de coding (piensa antes, simplicidad, cambios quirúrgicos) | media (ya las tenemos como manías) | candidato |
| Code Reviewer / TDD / Simplify | review, TDD, simplificación | media (ya hay skills en `.claude/skills/`) | candidato |
| Superpowers | orquestación multi-agente | ya instalado (plugin) | instalado |
| Frontend Design / Senior Frontend / UI-UX Pro Max | UI production-grade | alta (UI/UX, lo pediste) | candidato |
| Figma Implement Design | Figma→código | media | candidato |
| Vercel React/Web Design Guidelines | best practices React/UX | media | candidato |
| Frontend Slides / Impeccable | slides HTML | baja | candidato |
| Voice DNA / Writing Style | escribir con tu tono | baja | candidato |
| Planning-with-files | todo.md/plan.md persistente | media (tenemos WORK_LEDGER) | candidato |
| WebApp Testing / Playwright | tests E2E browser | media | candidato |
| Trail of Bits Security | vulnerabilidades | media | candidato |
| Claude Scientific Skills | LaTeX/papers/visualizaciones | media (paper) | candidato |
| Find-Skills | buscador de skills | baja | candidato |
| Browser Use / Agent-Browser | navegación/scraping | baja (knowledge-src lo sustituye mejor) | candidato |
| Team Eng Standards, UX Heuristics, Prompt Generator | varios | baja | candidato |

## Codex — skills/tools

| Tool | Para qué | Estado |
|---|---|---|
| WarpGrep | búsqueda ultrarrápida en repos | candidato |
| Create-Plan / Write-Plan | planificación antes de ejecutar | candidato |
| gh-fix-ci | arregla CI fallido en background | candidato |
| Firecrawl | búsqueda web/scraping/contexto vivo | candidato |
| Grill-Me | stress-test socrático de planes | candidato (alta — alinea con plan-then-execute) |
| Handoff / Yeet | comprimir sesión + commits/PRs auto | candidato |
| Remotion / Code Review | video / review | baja |
| Valyu | research | candidato |
| CLI-Creator | crear CLIs | baja |

## MCP servers — commodity (off-the-shelf, no reinventar)

Filesystem · Desktop Commander (archivos+terminal) · GitHub · Playwright/Browser · Postgres/Supabase ·
Figma · Context7 / Brave Search (docs en vivo) · Linear / Slack · Sequential Thinking.

## MCP servers — memoria / knowledge-graph

| Server | Nota | Estado |
|---|---|---|
| Knowledge Graph Memory (oficial Anthropic) | entidades+relaciones+observaciones | candidato |
| Graphiti MCP | shared memory Claude↔Cursor | candidato |
| Memory Keeper | historia/decisiones sin perder contexto | candidato |
| mcp-memory-graph (gregorydickson) | authority weighting, conflict resolution | candidato |
| Forgetful | Zettelkasten, vector+grafo, multi-dispositivo | candidato |
| CA-MCP | memoria compartida (experimento arXiv 2601.11595) | candidato |

**DECISIÓN nuestra:** la raíz de memoria NO es ninguno de estos — es **nuestro sustrato verificable**
(`SqliteMemoryIndex` + procedencia Merkle). Estos son commodity sin procedencia verificable; sirven
de referencia/benchmark, no de raíz.

## MCP aggregators / hubs (candidatos a "tronco")

| Hub | Nota | Estado |
|---|---|---|
| magg (meta-MCP) | descubre/instala/orquesta servers autónomamente | candidato (revisar primero) |
| 1mcp/agent | agrega múltiples servers en uno | candidato |
| universal-mcp-toolkit | agregación | candidato |
| mcgravity | proxy/load-balancer de servers | candidato |
| StormMCP | compone varios en endpoint unificado | candidato |

(Si alguno cubre el 80% del tronco, lo usamos en vez de construir desde cero — pero el contenido
—nuestras raíces— sigue siendo nuestro.)

## Repos / registries (dónde buscar)

`ComposioHQ/awesome-claude-skills` · `travisvn/awesome-claude-skills` · `alirezarezvani/claude-skills`
· `punkpeye/awesome-mcp-servers` · `modelcontextprotocol/servers` · `modelcontextprotocol/rust-sdk`
(rmcp) · `awesomeskills.dev` · `mcp-get`.

## SDKs / frameworks por lenguaje

- **Python:** FastMCP (estándar mayoritario; reutiliza nuestro código directo). Instalar con `uv`.
- **Node/TS:** SDK MCP + Zod.
- **Rust:** `modelcontextprotocol/rust-sdk` (rmcp, rmcp-macros, Tokio); `fastmcp_rust`, `prism-mcp-rs`,
  `rs-fast-mcp`. Para raíces calientes, después (políglota por-raíz).

## Métodos de instalación (para el automatizador)

- Skills: copiar carpeta a `~/.claude/skills/` (global) o `.claude/skills/` (proyecto).
- MCP servers: `claude mcp add ...` o editar `claude_desktop_config.json` / `.mcp.json`.
- Runtimes: `npx` (Node), `uv run` / venv (Python), `cargo` (Rust). `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

## Automatización de instalación (ley del mínimo esfuerzo) — diseño

Un **script instalador** (no el agente a mano) que: (1) lee este catálogo (estado `verificado`),
(2) resuelve cada item a su repo/comando, (3) **verifica que existe** (repo resuelve / comando
disponible) antes de instalar, (4) instala en el destino correcto (skills dir / mcp config), (5)
reporta. El **agente decide QUÉ** (marca `verificado` lo que se gana su sitio) y **verifica**; el
**script ejecuta** la descarga/instalación mecánica (`feedback-least-effort-automation`). NO instala
todo el catálogo — solo lo marcado. Encaja como fase del MCP trunk. NO construido aún.
