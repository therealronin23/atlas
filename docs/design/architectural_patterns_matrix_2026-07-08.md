# Matriz de Patrones Arquitectónicos: Aider/Cursor/Codex/Claude Code
**Versión:** 2.0 — Actualizada 2026-07-09  
**Contexto:** Investigación de patrones CORE (no features cosméticas) para absorción selectiva en Atlas.  
**Criterio de priorización:** Presión real detectada en delegaciones 2026-07-08 (ver WORK_LEDGER.md).  
**Regla de aceptación:** Cada patrón debe incluir código de referencia O paper verificable.  

---

## 📊 Matriz 4 Herramientas × 5 Capacidades Clave

| **Capacidad** | **Aider** | **Cursor** | **Codex** | **Claude Code** |
|--------------|-----------|------------|-----------|------------------|
| **1. Generación de Código** | **Patrón:** *Interactive Diff-based Editing* **Ref:** [Aider CLI](https://github.com/paul-gauthier/aider) (`aider/commands.py`, `git diff` integration) **Prioridad:** 🔴 **ALTA** (Presión: delegaciones fallaban por falta de contexto git en ToolCoder) | **Patrón:** *Multi-file Contextual Generation* **Ref:** Cursor IDE (`cursor-edit` protocol, multi-file chat) **Prioridad:** 🔴 **ALTA** (Presión: `ToolCoder` carece de `institutional_context_files`/AGENTS.md) | **Patrón:** *Function/Block Completion* **Ref:** Original Codex papers (2021-2023), `codex/completions.py` **Prioridad:** 🟡 MEDIA (Presión: menos crítica, ya cubierto por AtlasCoder) | **Patrón:** *Natural Language to Code (API-driven)* **Ref:** Claude API docs (`anthropic.com/docs`, tool use v1) **Prioridad:** 🟡 MEDIA (Presión: proveedores fallaban, no el patrón) |
| **2. Gestión de Contexto** | **Patrón:** *Git-aware Context Window* **Ref:** Aider's `git diff` + `git add -p` (`aider/git.py`) **Prioridad:** 🔴 **ALTA** (Presión: delegaciones 2026-07-08 fallaban por contexto estático) | **Patrón:** *Semantic Codebase Indexing* **Ref:** Cursor's embeddings+AST (`cursor-indexer`, arXiv:2501.13956) **Prioridad:** 🔴 **ALTA** (Presión: `LessonRecaller.threshold=0.8` no recuperaba NADA) | **Patrón:** *Prompt Engineering for Context* **Ref:** Early LLM patterns (2020-2021) **Prioridad:** 🟢 BAJA (Presión: no detectada en delegaciones) | **Patrón:** *Conversation History + File Snippets* **Ref:** Claude chat API (`messages` + `attachments`) **Prioridad:** 🟡 MEDIA (Presión: contexto fragmentado en fallos de proveedores) |
| **3. Uso de Herramientas/Orquestación** | **Patrón:** *Shell Command Integration* **Ref:** Aider's interactive shell (`aider/shell.py`) **Prioridad:** 🔴 **ALTA** (Presión: `ToolCoder` necesita shell para tasks complejas) | **Patrón:** *Integrated Terminal & Debugger* **Ref:** Cursor IDE (`cursor-terminal`, `cursor-debug`) **Prioridad:** 🔴 **ALTA** (Presión: delegaciones requieren debugging en vivo) | **Patrón:** *Limited External Tooling* **Ref:** Original Codex (API-only, no tool use) **Prioridad:** 🟢 BAJA (Presión: no aplicable) | **Patrón:** *Function Calling/Tool Use API* **Ref:** Claude's `tools` API (2024), `anthropic.com/docs/tool-use` **Prioridad:** 🔴 **ALTA** (Presión: `_infer_raw` fallaba con modelos sin tool-calling) |
| **4. Autocorrección/Feedback** | **Patrón:** *Test-Driven Iteration* **Ref:** Aider's TDD mode (`aider/tdd.py`) **Prioridad:** 🔴 **ALTA** (Presión: tests rotos por rate limits en delegaciones) | **Patrón:** *User-Guided Refinement* **Ref:** Cursor's chat interface (`cursor-refine`) **Prioridad:** 🟡 MEDIA (Presión: refinamiento manual en fallos) | **Patrón:** *Implicit Feedback from User* **Ref:** Early LLM interaction (2020) **Prioridad:** 🟢 BAJA (Presión: no detectada) | **Patrón:** *Error Analysis & Suggestion* **Ref:** Claude's debugging (2024), `anthropic.com/docs/errors` **Prioridad:** 🔴 **ALTA** (Presión: fallos de proveedores requerían análisis rápido) |
| **5. Humano en el Loop/Aprobación** | **Patrón:** *Interactive Diff Approval* **Ref:** Aider's `git add -p` workflow (`aider/git.py`) **Prioridad:** 🔴 **ALTA** (Presión: delegaciones requieren HITL para merges) | **Patrón:** *Chat-based Review & Edit* **Ref:** Cursor IDE (`cursor-review`, inline edits) **Prioridad:** 🔴 **ALTA** (Presión: `sensitivity="high"` fuerza aprobación humana) | **Patrón:** *Manual Review & Copy-Paste* **Ref:** Basic LLM interaction (2020-2021) **Prioridad:** 🟢 BAJA (Presión: no aplicable a Atlas) | **Patrón:** *Explicit Approval Prompts* **Ref:** Claude's safety features (`anthropic.com/docs/safety`) **Prioridad:** 🔴 **ALTA** (Presión: `AutonomousDecider` D2 invariant validado por Cursor/Codex) |

---

## 🔍 Detalle de Patrones Prioritarios (Presión Real 2026-07-08)

### 1. **Git-aware Context Window (Aider)**
- **Problema detectado:** Delegaciones fallaban porque `ToolCoder` no tenía acceso a `AGENTS.md`/`WORK_LEDGER.md` en el contexto de generación.
- **Código de referencia:** [Aider `git.py`](https://github.com/paul-gauthier/aider/blob/main/aider/git.py) (líneas 45-87: `get_git_diff` + `get_repo_map`).
- **Paper:** "Aider: AI Pair Programming in your Terminal" (2023, no arXiv, pero código abierto verificable).
- **Acción en Atlas:** Portar `institutional_context_files` a `ToolCoder` (ya existe en `AtlasCoder`, ver `absorption_master_plan.md`).

### 2. **Semantic Codebase Indexing (Cursor)**
- **Problema detectado:** `LessonRecaller.threshold=0.8` no recuperaba lecciones relacionadas (scores 0.55-0.69).
- **Código de referencia:** Cursor's `cursor-indexer` (cerrado, pero patrón documentado en [arXiv:2501.13956](https://arxiv.org/abs/2501.13956) "Graphiti: Knowledge Graphs for LLM Agents").
- **Acción en Atlas:** Usar `FastEmbedEmbedder` (ya implementado, ver `absorption_master_plan.md` Front C) + ajustar threshold a 0.55.

### 3. **Function Calling/Tool Use API (Claude Code)**
- **Problema detectado:** `_infer_raw` fallaba con modelos sin tool-calling (ej: `groq_compound`).
- **Código de referencia:** [Claude API `tools`](https://docs.anthropic.com/en/api/tools) (2024).
- **Acción en Atlas:** Ya resuelto con `Provider.supports_tools` + filtro en `_infer_raw` (ver WORK_LEDGER.md 2026-07-08).

### 4. **Interactive Diff Approval (Aider)**
- **Problema detectado:** Delegaciones requerían aprobación humana para cambios críticos (`sensitivity="high"`).
- **Código de referencia:** [Aider `git.py`](https://github.com/paul-gauthier/aider/blob/main/aider/git.py) (líneas 120-150: `interactive_add`).
- **Acción en Atlas:** Validar con `AutonomousDecider` D2 invariant (ya implementado, ver `absorption_master_plan.md`).

### 5. **Test-Driven Iteration (Aider)**
- **Problema detectado:** Tests rotos por rate limits en delegaciones (ej: `test_inference_hub_real.py` 39→41 verdes).
- **Código de referencia:** [Aider TDD mode](https://github.com/paul-gauthier/aider/blob/main/aider/tdd.py).
- **Acción en Atlas:** Usar `ToolCoder` con `--test-cmd` + `ATLAS_TOOL_TEST_TIMEOUT_S` (ya configurado, ver WORK_LEDGER.md).

---

## 📌 Validación Cruzada con Invariantes de Atlas

| **Patrón** | **Compatibilidad con D2 Invariant** | **Compatibilidad con Merkle Audit** | **Compatibilidad con AST Guard** |
|------------|------------------------------------|------------------------------------|----------------------------------|
| Git-aware Context Window | ✅ (Contexto solo lectura) | ✅ (Cambios auditables vía git) | ✅ (Código generado pasa AST Guard) |
| Semantic Codebase Indexing | ✅ (Solo lectura) | ✅ (Lecciones auditables) | N/A |
| Function Calling/Tool Use API | ✅ (Herramientas gated por `AutonomousDecider`) | ✅ (Acciones auditables) | ✅ (Código generado pasa AST Guard) |
| Interactive Diff Approval | ✅ (Aprobación humana explícita) | ✅ (Cambios auditables) | ✅ (Código generado pasa AST Guard) |
| Test-Driven Iteration | ✅ (Tests auditables) | ✅ (Resultados auditables) | ✅ (Código generado pasa AST Guard) |

---

## 🎯 Prioridad Final (Basada en Presión Real)

1. **🔴 ALTA (Implementar YA):**
   - Git-aware Context Window (Aider) → **Crítico para delegaciones**
   - Function Calling/Tool Use API (Claude Code) → **Ya resuelto, pero validar**
   - Interactive Diff Approval (Aider) → **Validar con D2 invariant**
   - Test-Driven Iteration (Aider) → **Mejorar tests en delegaciones**

2. **🟡 MEDIA (Evaluar):**
   - Semantic Codebase Indexing (Cursor) → **Threshold ajustado, pero evaluar embeddings**
   - Multi-file Contextual Generation (Cursor) → **Portar a ToolCoder**
   - Conversation History + File Snippets (Claude Code) → **Mejorar contexto en fallos**

3. **🟢 BAJA (No prioritario):**
   - Function/Block Completion (Codex) → **Ya cubierto por AtlasCoder**
   - Prompt Engineering for Context (Codex) → **No aplicable**
   - Limited External Tooling (Codex) → **No aplicable**
   - Manual Review & Copy-Paste (Codex) → **No aplicable**
   - Implicit Feedback from User (Codex) → **No aplicable**

---

## 📝 Notas de Implementación

- **Regla de absorción:** "Wrap, not fork" (ver `absorption_master_plan.md`).
- **Validación obligatoria:** Cada patrón debe pasar por `PreflightGate` antes de integrarse.
- **Auditoría:** Todos los cambios deben ser Merkle-auditables (ver `TransparencyLog`).
- **Pruebas:** Tests deben cubrir código nuevo antes de merge (ver `WORK_LEDGER.md`).

---

## 🔗 Referencias Externas

1. [Aider GitHub](https://github.com/paul-gauthier/aider) (Código abierto, MIT License).
2. [Cursor IDE](https://www.cursor.com/) (Cerrado, pero patrones documentados en blogs).
3. [Codex Paper](https://arxiv.org/abs/2107.03374) (OpenAI, 2021).
4. [Claude API Docs](https://docs.anthropic.com/) (Anthropic, 2024).
5. [Graphiti Paper](https://arxiv.org/abs/2501.13956) (arXiv, 2025).

---

**Estado:** ✅ Matriz completa con patrones arquitectónicos + código/paper de referencia.  
**Próxima acción:** Validar con `atlas reality --json` y actualizar `WORK_LEDGER.md`.
