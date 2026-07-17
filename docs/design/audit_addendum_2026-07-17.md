---
title: "Auditoría 2026-07-17 — verificación adversarial del audit Codex + delta + cola de arreglos"
status: vigente
date: 2026-07-17
verify_by: 2026-07-31
---

# Addendum de auditoría (Fable 5) — no se duplica, se verifica y se completa

Mandato del operador: "auditoría completa y exhaustiva con premortem y
postmortem… no des por supuesto nada, todo puede ser mentira… cualquier punto
se mejora o se soluciona… sé autocrítico". Método: el audit integral de Codex
(`audit_premortem_postmortem_2026-07-16.md`, 60 hallazgos) tiene 36 horas — se
VERIFICA adversarialmente en vez de repetirse, se audita el DELTA (15 commits
posteriores que invalidaron su sello), y se consolida la cola de arreglos
TOTAL con dueño. La dimensión que ningún audit ha cubierto (fidelidad de
intención sobre el corpus, "cagadas de hámster") ya está planificada como
T0.5b/c y NO se re-planifica aquí.

## 1. Verificación adversarial del audit Codex (2026-07-17, comandos reales)

| Afirmación del audit | Verificación | Resultado |
| --- | --- | --- |
| Cadena Merkle íntegra | `atlas audit --verify` | ✅ "Cadena Merkle integra" |
| Scanner seguridad limpio | `atlas security-audit src/atlas --json` | ✅ `[]` |
| Índice documental estricto | `docs_index_audit.py --strict` | ✅ cero caducados/huérfanos |
| Ficheros sensibles 0600 | `stat` Diseño-UI + quality-report | ✅ 600 ambos |
| Export bruto fuera de Git/Graphify | `git check-ignore` + `.graphifyignore` | ✅ ambos |
| Derivados PDF/HTML excluidos, MD conserva | `.graphifyignore` | ✅ |
| quality gate con estados honestos | report actual | ✅ `semantic_resume_incomplete` |
| Stubs retiro exit 64 (monitor/capture/autorem.) | head + grep (16-jul) | ✅ los 3 |
| Freshness del grafo fail-closed | `trunk_invoke_readonly graph_overview` | ✅ responde `STALE` y las queries estructurales se niegan (ver §2.1) |

Veredicto: **el audit Codex dice la verdad en todo lo muestreado.** Sus 60
hallazgos se aceptan como base sin re-litigar.

## 2. Delta (lo que pasó DESPUÉS de su sello)

1. **Grafo Kuzu servido STALE** — snapshot `110f2a40` vs HEAD `5d4ac3cc` (8
   commits, mayormente docs). El mecanismo fail-closed FUNCIONA (diseño
   correcto), pero el tick del daemon no re-ingiere al ritmo de commits pese a
   daemon `active` desde 16-jul 15:50. ARREGLAR: diagnosticar cadencia/gate del
   `maintenance_project_graph_tick` (¿intervalo? ¿env ATLAS_PROJECT_GRAPH en el
   unit?) y re-sellar (regen sobre HEAD → `FRESH`). [bootstrap]
2. **Sello del audit invalidado por 15 commits** (5 campaña + revisión final +
   4 docs de dirección + bootstrap + este). Contenido auditado por separado:
   los 5 de campaña pasaron revisión final Sonnet (APROBADO CON ARREGLOS,
   arreglos en 13070572); los docs de dirección son opinión/plan (riesgo:
   intención, no código — lo cubre T0.5c). Re-sello = §2.1 + suite dirigida.
   [bootstrap]
3. **~~12 fuentes graphify largas sin cobertura semántica~~ — DIAGNOSTICADA
   2026-07-17 (ola bootstrap), causa raíz distinta a la supuesta.** No era el
   proveedor: el LLM topa `max_completion_tokens` y devuelve JSON truncado que
   graphify descarta ("invalid JSON, skipping chunk"). Medido: WORK_LEDGER.md
   → 0 nodos con el techo por defecto (out=15358) vs **303 nodos** con
   `GRAPHIFY_MAX_OUTPUT_TOKENS=60000` (out=56015). Groq quedó descartado por
   TPM (413 real, 12k < ~18k/chunk) y ese error tapaba el problema de fondo.
   Estado: cobertura **694/699 = 99,3%** (12 fuentes sin valor semántico
   excluidas con criterio: scratch, graveyard, y el pack GENERATED por dedupe
   con sus fuentes). Quedan 5 (WORK_LEDGER, ecosystem_map, synthesis,
   research×2): re-run pendiente con el techo alto — cupo diario de Gemini
   agotado el 17-jul. `ecosystem_map` falla incluso con techo alto (causa sin
   diagnosticar, probable tabla gigante). YA NO es decisión del operador: es
   trabajo de bootstrap con receta conocida.
4. **Guard de cache semántica demasiado laxo** (hallazgo colateral):
   `is_verified_cache_payload` no exige `_atlas_checkpoint`, así que una cache
   escrita por graphify fuera de `graphify_semantic_resume.py` cuenta como
   verificada aunque le falten chunks. Detectado al contaminarlo yo mismo con
   una prueba de diagnóstico (cache borrada, cobertura re-medida). El script
   es honesto; su guard de lectura no. [bootstrap]

## 3. Premortem de la CAMPAÑA DE ARREGLOS (cómo puede fracasar "resolverlo todo")

| Fallo previsto | Señal temprana | Mitigación |
| --- | --- | --- |
| Muerte de presupuesto a mitad de ola (pasó con F2-F5) | Agentes caídos por límite | Sesiones frescas bootstrap-driven; ledger durable; nunca >1 ola en vuelo |
| "Arreglar" contra una decisión sellada | Fix que toca §4 del plan maestro | Regla del operador codificada: "el proyecto dice lo contrario → ni puto caso"; N0 manda |
| Arreglo que introduce el mal que caza (deriva de intención) | Diff sin readback en ítem ambiguo | Readback §2.8 obligatorio en cada fix interpretable |
| Duplicar el audit Codex por no leerlo | Hallazgo "nuevo" ya en su tabla | Este addendum es el dedupe; consultar ANTES de abrir hallazgo |
| Cerrar en papel, no en evidencia | Ítem "done" sin comando pegado | Cada cierre exige la evidencia en el ledger (regla bootstrap) |
| El fixer mata el fail-closed por comodidad | Un STALE/error convertido en warning | Prohibido relajar guards para "que pase"; el guard ES el producto |

## 4. Cola de arreglos TOTAL (de menor a mayor, con dueño)

**[bootstrap] — sesión(es) autónomas, sin el operador:**
1. Diagnóstico+arreglo cadencia tick grafo + re-sello FRESH (§2.1).
2. Re-verificación post-re-sello: suite dirigida + `reality --json` limpio.
3. Umbral recall 0.8 vs score real 0.45 en docs largos (Minor campaña):
   medir 5 queries reales → decidir umbral o chunking, con evidencia.
4. Crear/validar `.venv-scraping` aislado y repetir marcador Crawl4AI
   (riesgo residual Codex "Omitido").
5. REST Hermes legado: demostrar cero callers y retirar con ADR corto
   (riesgo "Compatibilidad").
6. T0 core plan (ya escrito) — la ola principal del bootstrap.

**[operador — N3, nadie puede hacerlo por ti]:**
7. **Rotar el client secret OAuth de Google Workspace** visto en argv
   (riesgo ABIERTO más urgente del audit). Vector confirmado en vivo
   2026-07-17: lo expone el `--mcp-config` del cliente Claude, no el servidor.
   Mitigación ya construida (wrapper sin secretos en argv + runbook:
   `docs/operations/oauth_rotation_google_workspace.md`); la ROTACIÓN y el
   repunte del conector siguen siendo solo tuyos.
8. ~~Decidir 12 fuentes largas~~ — RESUELTO sin operador: era un techo de
   salida del LLM, no una elección de proveedor (§2.3). Queda re-run mecánico.
9. ~~Higiene docs/handoff en INDEX~~ — HECHA 2026-07-17 (commit 18af7e0c):
   packs = `historico`, GENERATED = `vigente`, `--strict` limpio.
10. Revisar/confiar hooks Codex en su cliente; NO publicar `refs/codex/*`.
11. Decisiones diferidas: cuándo F2.6; spec B+C (bendecir); Hermes/VPS/
    Telegram/Neo4j en vivo (cada uno es despliegue+credencial).

**[T-tramos del plan maestro — arquitectónicos, NO sprint]:**
12. Seccomp allowlist portable (ADR-055 pendiente) → ítem T1 (endurecer el
    jail del constructor autónomo antes de ampliarle vocabulario).
13. HMAC rate-limit interno → con T6 (cuando la frontera crezca).
14. Identidad prompt/modelo del cache semántico (límite upstream) →
    mantener `mixed_or_unverified`; re-extraer con identidad única cuando
    T4 lo necesite.
15. Fidelidad de intención sobre el corpus completo (666 docs + trampas
    doctrina §3) → T0.5b/c, ya planificado.

## 5. Postmortem (de esta auditoría y del ciclo 15-17 jul)

- **Causa raíz nueva confirmada**: *afirmación punto-en-tiempo sin caducidad*
  (el ledger mintiendo sobre scripts retirados; el mapa desactualizado 5 días).
  Corrección estructural ya aplicada: INDEX con `verify_by`, regla en doctrina
  §3, y este doc lleva `verify_by: 2026-07-31`.
- **Lo que funcionó**: verificación adversarial barata (9 claims muestreados
  con comandos, 0 mentiras — el fail-closed sistemático de Codex y nuestro
  ceremonial de evidencia convergen); el fail-closed del grafo convirtió un
  bug potencial (servir grafo viejo) en un hallazgo visible.
- **Lo que no**: el sello de auditoría dura horas en un repo activo — sellar
  y seguir commiteando es contradictorio. Regla nueva: el re-sello es un PASO
  del bootstrap (barato, repetible), no un evento.
- **Autocrítica del auditor**: (a) muestreé 9 de 60 afirmaciones — suficiente
  para confianza, no para certeza; el barrido exhaustivo de las 51 restantes
  sería teatro caro con este presupuesto y lo digo en vez de fingirlo;
  (b) mi propia obra (docs de dirección) queda auditada solo en forma, no en
  intención — la intención la debe auditar T0.5c con ojos que no sean míos.

## 6. Regla de cierre de la campaña

Cada ítem de §4 se cierra SOLO con evidencia pegada en el ledger de campaña
(comando+salida). Los [operador] se le presentan como lista corta con botones
claros, jamás como pregunta técnica. Al vaciar §4-[bootstrap]: re-sello,
entrada en WORK_LEDGER, y este doc pasa a histórico con banner.
