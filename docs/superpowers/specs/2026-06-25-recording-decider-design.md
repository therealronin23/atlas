# Diseño — RecordingDecider (slice 1 del arco copia-digital → reducir HITL)

Brainstorming 2026-06-25, **deliberado por el Cónclave full** (trío vivo 3/3: veredicto FAIL-como-completo
→ PASS con este diseño revisado). Puntos ciegos y resoluciones en memoria
`conclave-recordingdecider-blindspots`. NO construye el TwinDecider ni shadow-eval (slices posteriores):
slice 1 = **capturar fielmente** las decisiones, con esquema, tiempo, procedencia y seguridad.

## Principio rector — SUSTRATO UNIFICADO (decisión del usuario 2026-06-25)
**Atlas no es un modelo concreto: es el sustrato + las normas.** Claude, el trío del Cónclave, el
`AutonomousDecider` y el conocimiento ingerido son PARTICIPANTES que escriben/leen la MISMA memoria
verificable, bajo las MISMAS reglas (procedencia por-voz, bi-temporal, crypto-shred, tenant, honestidad/
Reality-First, firewall de sensibilidad). NO hay memoria privada del Cónclave ni del decisor: el
`DecisionSink`, el `SynthesisRecorder` del Cónclave y las lecciones de Atlas son **la misma operación** —
escribir una memoria tipada y con procedencia al sustrato común. Todo el arco (este slice incluido) gira en
torno a esto.

Dos invariantes que la unificación HACE OBLIGATORIOS (tests):
- **Firewall de sensibilidad (global):** ningún participante (Twin, Cónclave, loop) puede hacer que el
  corpus realimente qué cuenta como `sensitivity=high`. Eso vive solo en código revisado.
- **Anti-cámara-de-eco:** alimentar al trío con el sustrato debe ser HECHOS/CORRECCIONES, nunca "esto
  concluimos antes" — anclar el juicio del trío a su historia colapsa la diversidad de linajes (US/CN/EU)
  que es su único valor. La diversidad obligatoria del panel se mide ANTES de inyectar contexto histórico.

## Objetivo y NO-objetivo
- **SÍ:** grabar cada decisión (`Decider.decide`) a un sink, sin alterar el veredicto, con esquema apto para
  un futuro TwinDecider y para evaluación en shadow.
- **NO (registrado, no construido):** TwinDecider, shadow-eval, métrica de divergencia, detección de
  outliers, escrow de clave usuario. Son slices posteriores (wire-before-claim).

## Prior-art que se reutiliza (internal-prior-art-first)
- `Decider` Protocol + `DecisionAction` + `action_hash` (`core/decider/decider.py`), `make_decider`.
- Sustrato seguro `SqliteMemoryIndex` (`memory/memory_index.py`): Fernet por-ítem, crypto-shred
  (`secure_delete=ON` + keystore separado), merkle_leaf_hash, **bi-temporal** (valid_from/until),
  `ProvenanceWriteGate` (anti-envenenamiento).

## Correcciones del Cónclave incorporadas (A–D)
- **A. crypto-shred ⟂ corpus acumulable** → **split estructura/texto.** El registro separa:
  - *features estructuradas* (NO sensibles, persisten inmutables): action_hash, kind, descriptor,
    mutating, reversible, sensitivity, requires_approval, verdict, decider_name, decider_version, ts.
  - *rationale* (texto, potencialmente sensible): campo aparte, **crypto-shredeable por-entrada** sin
    destruir la fila estructural. El merkle-leaf hashea las features, no el plaintext del rationale.
- **B. corpus inservible** → esquema estricto (no solo texto) + **decider_version (code-hash del decisor)**
  por registro + **bi-temporalidad** (ts en ns; la deriva se mide después con valid_from/until). v1 NO
  afirma "entrenable"; afirma "capturado fielmente con esquema y tiempo".
- **C. shadow** → fuera de slice 1. Slice 1 SOLO garantiza capturar lo que shadow necesitará: el
  **veredicto humano real** + `decider_name` (humano vs autónomo) + features. Sin métrica aquí.
- **D. envenenamiento + firewall de sensibilidad** → el write pasa por `ProvenanceWriteGate` (procedencia
  por registro). **INVARIANTE (test):** el RecordingDecider es de SOLO-ESCRITURA del corpus; NUNCA lee el
  corpus para decidir, y NADA del corpus realimenta qué cuenta como `sensitivity=high` (eso vive en código
  revisado, AutonomousDecider). El firewall se hace cumplir por construcción: el wrapper no tiene método de
  lectura ni influye en la clasificación.

## Unidades
### Unidad 1 — modelo + Protocol (`core/decider/decision_record.py`)
- `@dataclass(frozen=True) DecisionRecord`: las features estructuradas + `rationale: str | None` +
  `decider_name: str` + `decider_version: str` + `timestamp_ns: int`.
- `record_id(rec) -> str` = `action_hash` (ya ata veredicto↔acción).
- `class DecisionSink(Protocol)`: `record(rec: DecisionRecord) -> None`.

### Unidad 2 — `RecordingDecider` (`core/decider/recording_decider.py`)
- `__init__(inner: Decider, sink: DecisionSink, *, decider_version: str, clock=time.monotonic_ns)`.
- `decide(action, sanctioned_intent, context) -> Verdict`:
  1. `verdict = self._inner.decide(...)` (sin tocar).
  2. construye `DecisionRecord` (verdict→str; `rationale` = `context.get("rationale")` si lo hay; en
     RequiresHuman resuelto, el rationale humano se inyecta por el call-site vía context).
  3. `self._sink.record(rec)` — **best-effort: si el sink falla, loggea y NO rompe la decisión** (grabar no
     debe degradar decidir). 4. `return verdict` intacto.
- NO expone lectura del corpus (firewall D por construcción).

### Unidad 3 — sinks
- `JsonlDecisionSink` (stub dev/test, `core/decider/decision_record.py`): append-only JSONL. Sin cifrado →
  SOLO para test/local.
- `MemoryDecisionSink` (producción, `core/decider/memory_decision_sink.py`): escribe al `SqliteMemoryIndex`
  con `ProvenanceWriteGate`; features → contenido estructurado con merkle_leaf_hash; rationale → ítem
  cifrado Fernet shredeable.

**Corte de alcance (decisivo):** slice **1** = Unidades 1 + 2 + `JsonlDecisionSink` + Unidad 4 (cableado
opt-in). El esquema YA implementa el split A (features vs rationale) y el firewall D por construcción, así
que la seguridad de DISEÑO está en slice 1. Slice **1b** (inmediato, mismo arco) = `MemoryDecisionSink`
(cifrado/shred/merkle/procedencia) — es el sink de PRODUCCIÓN; hasta entonces `JsonlDecisionSink` es
SOLO-TEST y `ATLAS_DECISION_LOG` no debe apuntarse a decisiones reales sensibles. Esto NO diluye lo que
exigió el Cónclave: el split y el firewall son de slice 1; el cifrado-en-reposo es 1b, no opcional.

### Unidad 4 — cableado opt-in en `make_decider`
- Con `ATLAS_DECISION_LOG=<path|memory:db>` envuelve el decisor elegido en `RecordingDecider`. Sin la env →
  cero cambio de comportamiento (default off). `decider_version` = hash corto del módulo decisor.

## Tests (verify-the-real-case)
- **Transparencia:** `RecordingDecider.decide` devuelve EXACTAMENTE el verdict del inner (Allow/Deny/
  RequiresHuman), para los tres tipos.
- **Un registro por decisión** con features correctas; `record_id == action_hash(action, intent)`.
- **Split A:** shred del rationale de una entrada NO destruye sus features estructuradas (fila sigue, merkle
  intacto). (test sobre MemoryDecisionSink; o, si se difiere, sobre el contrato del sink.)
- **Firewall D:** el RecordingDecider no tiene API de lectura del corpus; un test afirma que dos decisiones
  idénticas dan el MISMO verdict del inner sin importar lo ya grabado (el corpus no influye en decidir).
- **Best-effort:** si `sink.record` lanza, `decide` igualmente devuelve el verdict (no propaga).
- **Opt-in:** `make_decider` envuelve solo con la env puesta; sin ella, el decisor es el de hoy.
- **decider_version** presente y estable para el mismo código.

## Definition of done
Tests verdes + mypy strict + `WORK_LEDGER.md`/`docs/backlog.yaml` en el mismo commit. wire-before-claim: NO
se declara "copia digital" ni "corpus entrenable" — solo "decisiones capturadas fielmente, con esquema,
tiempo, procedencia, y rationale shredeable". Slices posteriores (registrados): MemoryDecisionSink pleno
(= el write tipado/provenanced al sustrato compartido que TAMBIÉN usan el SynthesisRecorder del Cónclave y
las lecciones de Atlas — una sola operación, principio de sustrato unificado), TwinDecider, shadow-eval +
métrica de divergencia + outliers, Cónclave que se nutre del sustrato (con el invariante anti-cámara-de-eco).
