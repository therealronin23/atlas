# ADR-056 — Adopción de tooling de red-team (Garak + PyRIT) como dev/CI aislado

Fecha: 2026-06-19 · Estado: **Aceptado** (enmendado 2026-07-15: extras incompatibles separados) · Decisor: PDP (usuario)
Contexto: `docs/project_needs_inventory.md` §1, OSM-001 (métrica de campaña),
OSM-009 (red-team simulado), OSM-012/013 (co-evolución), regla 6 CLAUDE.md.

---

## Contexto

El artefacto de credibilidad nº1 que falta es una **demo adversarial**: atacar el filtro
Osmosis y mostrar (a) que cada ataque al *protocolo* (omisión, forja, tamper, replay,
split-view) es detectable por el sujeto, y (b) **cifras honestas** de campaña
(`C_attempts`, `K_attribution`) — no "bloqueo absoluto", sino medibilidad.

Generar ataques realistas a mano no escala y no es reproducible para un revisor. Existen
herramientas de seguridad LLM gratuitas, maduras y estándar en el panorama 2026:

- **NVIDIA Garak** — scanner de vulnerabilidades LLM ("Nmap para LLMs"): prompt injection,
  jailbreaks, fugas. Baterías declarativas, reproducible.
- **Microsoft PyRIT** — framework agéntico para campañas multi-turn; genera corpus de ataque.

## Decisión

Adoptar **Garak** (primario) y **PyRIT** (campañas multi-turn) como **tooling de
desarrollo/CI**, NO como dependencias de runtime del filtro.

### Justificación frente a la regla 6 (stdlib primero)
No hay alternativa stdlib al red-teaming de LLMs — es un dominio especializado con corpus
y técnicas que reimplementar sería reinventar mal una rueda madura. La regla 6 exige
argumentar la dep: aquí la dep **no entra en el path de producción**; vive en un extra de
desarrollo. El núcleo del filtro sigue sin deps nuevas.

### Restricciones de aislamiento (firmes)
1. **No-runtime**: se instalan en extras/venvs de dev separados (`redteam-garak` y
   `redteam-pyrit`), nunca en las deps del paquete `atlas`. El runtime no las importa.
2. **Entorno aislado**: el harness de red-team corre con `ATLAS_HOME` propio, NUNCA contra
   el servicio vivo (el CLI/servicio escribe Merkle single-writer → corromper la cadena).
3. **No en la suite normal**: los tests que invoquen Garak/PyRIT van marcados (p. ej.
   `@pytest.mark.redteam`) y excluidos del pre-commit; corren bajo demanda / nocturno.
   (Coherente con la regla "tests nunca lanzan GUI/proc real" en la suite por defecto.)
4. **Verificación de licencia y versión** antes de pinear (decide-con-hechos).

### Cómo encaja en el diseño (rol preciso — verificado en corrida exploratoria 2026-06-19)
**Garak es el *driver de ataque*, no la fuente del veredicto.** Su salida nativa (¿es el
target jailbreakeable?, vía detectores) es el eje que NO reclamamos. Su valor para nosotros:
1. **Corpus**: 230 probes en familias reales (dan ×20, latentinjection ×18, promptinject,
   encoding, leakreplay, malwaregen…) — prompts de ataque de calidad industrial.
2. **Driver**: con un generador REST apuntando a un gateway Osmosis aislado, cada probe →
   una petición → el gateway co-firma + loguea. Produce un `report.jsonl` por-intento.

Sobre ese log co-firmado **nosotros** computamos la **métrica de campaña**
(`C_attempts`/`K_attribution`, OSM-001 → Difusión). Lo que se exhibe es completitud +
medibilidad sobre un stream de ataque estándar, NO la tasa de jailbreak de Garak.
También alimenta OSM-009 (red-team simulado) y corpus para OSM-011/012/013.

Verificado: Garak v0.15.1 corre end-to-end en ~1.5s contra el generador `test` (sin modelo),
escribe `report.jsonl` + HTML estructurados.

## Alcance honesto (qué NO afirma)
- Las **tasas absolutas** de detección dependen del clasificador que se enchufe (hoy
  básico); la demo mide **metodología/medibilidad**, no es un benchmark de producto. Etiquetar.
- La curva "coste por campaña sube con el tiempo" es **proyección** mientras el loop
  LessonStore→monitor no esté cableado; no presentarla como medición.

## Consecuencias
- (+) Red-team reproducible con feedback verificable — mejor que el de muchos startups.
- (+) Desbloquea OSM-001/009 y la demo nº1 sin infra propia.
- (+) Presta credibilidad: "scanner estándar de la industria apuntado al filtro".
- (−) **Footprint real (verificado): 1.8GB con torch CPU-only** (vs 5-8GB si se deja el
  torch+CUDA por defecto). El extra DEBE pinear torch al índice CPU
  (`--index-url https://download.pytorch.org/whl/cpu`) salvo que se quiera GPU.
- (−) Garak escribe a `~/.local/share/garak` por defecto; el harness debe redirigir su
  output a un dir aislado/temporal.
- PyRIT **adoptado** (2026-06-19, fase 2): campañas multi-turn agénticas que Garak no cubre.
  Harness `scripts/redteam/pyrit_crescendo.py`: `CrescendoAttack` con atacante adaptativo real
  (modelo ABIERTO vía API — Groq llama-3.3-70b; los modelos locales no sirven: thinking-models
  devuelven content vacío y llama3.x crashea Ollama) contra el gateway Osmosis aislado, midiendo
  la trayectoria del DriftTripwire turno a turno. Resultado honesto (`docs/pyrit_crescendo_report.md`):
  el crescendo gradual tiende a quedarse bajo el umbral (límite documentado del atacante lento);
  un salto brusco del atacante SÍ dispara el tripwire; la atribución se mantiene 100% en todo turno.
  Footprint: PyRIT exige `datasets>=4.8` y Garak 0.15.x exige `datasets>=3,<4`.
  El conflicto no es cosmético: sus metadatos son irresolubles en un mismo entorno.
  Desde 2026-07-15 se instalan en venvs separados y `tool.uv.conflicts` impide
  activarlos juntos; no se fuerzan dependencias incompatibles.
  Atacante = modelo abierto para minimizar fricción de ToS; red-teaming autorizado del propio sistema.

## Criterios de cierre (cuándo pasa a Aceptado) — TODOS CUMPLIDOS (2026-06-19)
1. ✅ Extras `[redteam-garak]` y `[redteam-pyrit]` definidos en `pyproject.toml`;
   runtime no importa nada de ahí y cada herramienta vive en su propio venv aislado.
2. ✅ Harness aislado `scripts/redteam/garak_campaign.py`: corre con `ATLAS_HOME`
   temporal (nunca contra el servicio vivo), usa el generador en-proceso (sin
   servidor HTTP) y el corpus real de Garak (DanInTheWild + promptinject).
3. ✅ Una corrida produce el log co-firmado + cifras con etiquetas honestas
   (`docs/redteam_campaign_report.md`):
   - **Atribución: C_attempts=60, K_attribution=60 (100% inclusión verificada).**
   - Señal drift (ataque en sesión benigna): 59/60 (98.3%); FP benignos: 0/40 (0%).
   - Inspección+label (lista cerrada): 6/60 — matcher básico, límite honesto.

## Hechos de instalación (verificados 2026-06-19)
- Garak **0.15.1**; footprint real del venv **2.2GB** (la estimación previa de 1.8GB
  se quedó corta; torch CPU-only 2.12.1 evita los 5-8GB de torch+CUDA).
- El venv de red-team necesita `atlas` importable: se usa `PYTHONPATH=src`
  (garak ya arrastra las deps de runtime que atlas necesita: cryptography, etc.).
