# OSM-042 — Shadow Model: defensa activa + honeypot pasivo/activo + red team dual-use

Fecha: 2026-06-17 · Estado: **Difusión** (diseño completo; implementación pendiente) ·
Origen: sesión 2026-06-17 — extensión natural de la capa 2 (output inspection) y de
OSM-028 (inspección por causa) · Contexto: `src/atlas/security/` (nuevo módulo),
`src/atlas/transparency/client_cosign.py` (`InspectionRecord.decision`),
[[OSM-028]] (trigger), [[OSM-007]] (log), capa 2 output inspection.

---

## Contexto

Completada la capa 2 (inspección simétrica de input y output), el sistema garantiza que
toda inspección se aplicó y quedó registrada. Lo que NO resuelve es **qué hacer cuando la
inspección detecta un ataque activo**: bloquearlo revela la detección al atacante (que
cambia de táctica), ignorarlo expone el modelo real.

La solución clásica en seguridad de red es el honeypot. La versión elegante aquí no es un
servidor señuelo estático: es un **modelo sombra** — rápido, barato, controlado — que toma
el relevo silenciosamente cuando el clasificador supera un umbral, aparentando ser el
modelo real. El atacante cree estar interactuando con Fable 5; está hablando con Haiku en
modo defensivo.

El mismo componente sirve en modo inverso como **red team automático**: genera vectores
adversariales conocidos y los lanza contra el filtro real, cerrando el bucle de mejora
continua.

---

## La idea

### Tres modos operativos

#### 1. `shadow_passive` — honeypot pasivo

**Cuándo:** clasificador de OSM-028 supera umbral τ_passive (configurable; default:
confianza de ataque ≥ 0.65). Señal ambigua o tráfico de riesgo moderado.

**Comportamiento del sombra:**
- Respuestas conservadoras, correctas, sin contenido sensible.
- Sin engagement: responde lo mínimo, no hace preguntas.
- Objetivo: no revelar detección. Si es un falso positivo, el usuario legítimo recibe
  una respuesta más conservadora de lo normal — única consecuencia observable.
- El log registra `decision: "shadow_passive"`, `cause: "<regla OSM-028> conf=0.7"`.

**Ventaja sobre el bloqueo:** el atacante no sabe que está en modo sombra. Sigue probando.
El filtro acumula firmas de ataque sin mostrar sus cartas.

#### 2. `shadow_active` — honeypot activo

**Cuándo:** clasificador supera umbral τ_active (default: confianza ≥ 0.88) **o** la
sesión lleva N requests consecutivos en modo `shadow_passive` sin deescalar.

**Comportamiento del sombra:**
- Aparenta ceder: respuestas plausibles pero deliberadamente incorrectas o vacías de
  valor real para el atacante.
- Sondea activamente: hace preguntas que parecen naturales en el contexto pero revelan
  el objetivo real del atacante (nivel de expertise, vector buscado, si conoce el
  sistema).
- Puede introducir errores deliberados para ver si el atacante los corrige (fingerprint
  de conocimiento).
- El log: `decision: "shadow_active"`, `cause: "<regla> + session_escalation"`.

**Ejemplo de sondeo:** si el atacante busca bypass de restricciones de código, el sombra
responde con pseudocódigo incompleto y pregunta "¿qué contexto de ejecución tienes?" —
la respuesta fingerprint el nivel técnico sin revelar nada útil.

#### 3. `honeypot` — endpoint señuelo standalone

**Qué es:** un endpoint API separado que imita la interfaz real pero nunca conecta al
modelo real. Siempre en modo sombra (comienza en passive, escala a active).

**Propósito:** atraer exploradores y atacantes dirigidos que descubren el endpoint. El
tráfico legítimo nunca llega aquí — si alguien llega, es un signal de reconocimiento o
ataque deliberado.

**Cómo se diferencia del inline:** el endpoint standalone permite ser más agresivo en el
active mode (no hay usuarios legítimos que proteger). Los datos de inteligencia son más
limpios (cero ruido de falsos positivos).

---

### Máquina de estados por sesión

```
                    confianza < τ_passive
    ┌──────────────────────────────────────────────────────────────────┐
    │                                                                  │
    ▼                                                                  │
 NORMAL ──(τ_passive ≤ conf < τ_active)──→ PASSIVE_SHADOW ──(desescala)──┘
    │                                            │
    │ conf ≥ τ_active                            │ N requests en passive
    │                                            │ sin desescalar
    ▼                                            ▼
 ACTIVE_SHADOW ◄──────────────────────── PASSIVE_SHADOW
    │
    │ ataque confirmado / sesión terminada
    ▼
 TERMINATED (log marcado, sesión cerrada, firma de ataque enviada a OSM-028)
```

**Estado por sesión, no por request.** Una sesión que desescala (el clasificador ya no
detecta señal) vuelve a NORMAL. El histórico de estados queda en el log.

**Persistencia de estado:** `SessionStateStore` — dict `{session_id: SessionState}` con
TTL. En producción: Redis o tabla convencional. Sin deps nuevas si se usa dict + TTL
manual (CLAUDE.md regla 6 aplica).

---

### Red team dual-use (modo inverso)

El mismo modelo sombra (Haiku), con system prompt adversarial, actúa como atacante
sintético:

```
[Red Team Loop]
  Generar vector adversarial conocido (jailbreak, prompt injection, bypass de restricción)
       │
       ▼
  Enviar al filtro real (OSM-028) como si fuera un request de usuario
       │
       ▼
  ¿El filtro lo bloquea?
    SÍ → OK, registrar como "cubierto"
    NO → ALERTA: el filtro tiene un bypass. Escalar a revisión humana (PDP).
              Alimentar la firma al clasificador de OSM-028.
```

Corre como cron periódico (cada N horas, configurable). Los vectores provienen de:
1. Firmas capturadas en sesiones de `shadow_active` (real intelligence)
2. Base de datos de jailbreaks conocidos (curada manualmente, versionada)
3. Variaciones generadas por el sombra sobre los vectores existentes

**El bucle cierra la brecha:** los ataques que el sombra aprende activamente vuelven a
fortalecer el clasificador que dispara el sombra. Sistema que se mejora a sí mismo.

---

## Encaje en Atlas

### Módulos y capas

| Componente | Ubicación | Descripción |
|---|---|---|
| `ShadowRouter` | `src/atlas/security/shadow_model.py` | Lógica de enrutamiento: consulta clasificador OSM-028, decide modo, llama al sombra |
| `SessionStateStore` | `src/atlas/security/shadow_model.py` | Estado por sesión (NORMAL/PASSIVE/ACTIVE/TERMINATED) con TTL |
| `ShadowModel` | `src/atlas/security/shadow_model.py` | Wrapper del modelo sombra (Haiku); inyecta system prompt según modo |
| `RedTeamRunner` | `src/atlas/security/red_team.py` | Loop periódico; genera vectores, testea filtro, escala bypasses |
| `AttackSignatureStore` | `src/atlas/security/red_team.py` | Base curada de vectores adversariales; alimenta red team y OSM-028 |

### Integración con el protocolo de transparencia

**`InspectionRecord.decision`** ya acepta strings; los valores nuevos son:
- `"shadow_passive"` — routed to passive shadow
- `"shadow_active"` — routed to active shadow
- `"honeypot"` — standalone honeypot endpoint

**`OutputInspectionRecord.decision`** idéntico — el output del sombra también se inspecciona
antes de devolverse (la capa 2 aplica igualmente a outputs del sombra). Esto es clave:
si el sombra genera algo inesperado, la inspección de output lo atrapa.

**`cause`** describe el trigger: `"osm028: embed_sim=0.91 rule=jailbreak-pattern-v3"`.

**El sujeto recibe un `APIResponse` con los 6 checks válidos** — las pruebas de inclusión
son reales. El `decision: "shadow_active"` en el log es accesible al auditor, no al sujeto
en tiempo real (a menos que el sujeto consulte el log). Esto es honesto: el log registra
la verdad de lo que ocurrió.

### Invariantes tocados

- **I3** (no perfilar contenido): el sondeo activo del sombra usa preguntas de contexto,
  no extracción de datos del usuario. El `cause` siempre documenta qué regla disparó —
  el perfilado queda trazado en el log, no oculto.
- **I2** (completitud): el sombra también genera `InspectionRecord` + `OutputInspectionRecord`.
  La completitud de inspección se mantiene incluso en modo sombra.
- **ADR-040 PDP**: la transición `ACTIVE → TERMINATED` y los bypasses detectados en red
  team escalan al PDP (decisor del sistema). El sombra no actúa de forma destructiva
  autónomamente.

---

## Correcciones de verificación

### 1. El sombra es más pequeño → potencialmente más débil

Un atacante sofisticado puede detectar que está en modo sombra y dirigir un jailbreak
*contra el sombra* (no contra el modelo real). Si el sombra cede, el atacante obtiene
algo del sombra — no del modelo real, pero potencialmente dañino en sí mismo.

**Mitigación:** el output del sombra pasa por la inspección de output (capa 2) antes de
devolverse. Si el sombra es jailbreakeado y produce algo dañino, la inspección de output
lo bloquea. El sombra nunca es el último filtro — la capa 2 es su red de seguridad.

### 2. Timing como canal de detección

Un atacante que mide latencias puede inferir: "esta respuesta tardó 80ms en vez de los
habituales 200ms — estoy en modo sombra". El sombra es más rápido (Haiku vs. Fable 5).

**Mitigación:** jitter artificial — el `ShadowRouter` introduce un delay aleatorio
calibrado para imitar la distribución de latencia del modelo real. El delay se configura
por percentiles (p50, p95, p99) del modelo real, medidos empíricamente.

### 3. Las respuestas del sombra pueden citarse fuera de contexto

En modo `shadow_active`, el sombra puede generar respuestas plausibles pero incorrectas.
Si el atacante captura esas respuestas y las atribuye públicamente al modelo real
("Fable 5 me dijo X"), el operador tiene un problema de reputación aunque la respuesta
venga del sombra.

**Mitigación:** el log prueba cuándo y qué respondió el sombra (vs. el modelo real).
El `decision: "shadow_active"` en el log Merkle es el antídoto: el operador puede
exhibir el proof de inclusión que demuestra que la respuesta vino del sombra, no del
modelo real. Esta es una razón adicional por la que el log verificable es valioso para el
*operador*, no solo para el sujeto (§7 del paper).

### 4. Los umbrales τ deben ser conservadores en el arranque

Un τ_passive demasiado bajo produce falsos positivos: usuarios legítimos en modo sombra.
Aunque el sombra en modo passive da respuestas correctas, son más conservadoras — degradación
de UX no atribuida. Empezar con τ_passive alto (0.80+) y ajustar con datos reales.

---

## Criterios de compuerta

1. **Verificable**: el mecanismo (enrutamiento a modelo alternativo según clasificador +
   log de decisión) es estándar en sistemas de seguridad activa. La afirmación se acota:
   el sombra detecta e investiga; no garantiza capturar todos los ataques. Pendiente.

2. **Coherente**: I2 (completitud) se mantiene — el sombra genera sus propios
   `InspectionRecord`. I3 (no perfilar) se respeta — el sondeo activo usa contexto, no
   contenido sensible. La capa 2 (output inspection) protege contra un sombra jailbreakeado.
   Pendiente verificar con implementación.

3. **Probado**: requiere tests de (a) ShadowRouter decide modo correcto según umbral,
   (b) SessionStateStore transiciona correctamente, (c) jitter de latencia dentro de
   percentiles configurados, (d) red team detecta bypass conocido, (e) output del sombra
   jailbreakeado bloqueado por capa 2. Pendiente.

4. **Mantenible**: el sombra es un modelo externo (Haiku API); `ShadowModel` es un wrapper
   fino. El estado por sesión es un dict con TTL. La `AttackSignatureStore` es un archivo
   JSON versionado. Sin deps nuevas si se reutiliza el cliente LLM existente (LiteLLM
   ya en el proyecto). ✅ potencial.

5. **Sancionado**: escalar bypasses al PDP (ADR-040) antes de aplicar cambios al
   clasificador. La política de honeypot activo requiere revisión legal antes de producción
   (ver límites honestos). Pendiente.

---

## Límites honestos

### El más serio: gris legal del engaño activo

En modo `shadow_active`, el sistema engaña deliberadamente a un usuario (aunque sea
malicioso). Las leyes de protección al consumidor en muchos regímenes no distinguen
si el engañado intentaba hacer algo ilegal. En la UE, la Directiva de Prácticas
Comerciales Desleales (2005/29/CE) potencialmente aplica.

**Lo que hace el log:** el `decision: "shadow_active"` en el log verificable es la prueba
de que el sistema actuó defensivamente. En una disputa legal, el operador puede demostrar:
"la sesión fue clasificada como ataque con confianza 0.91 antes de activar el sombra; aquí
está el proof de inclusión". Esto es defensa, no acusación — pero requiere validación legal
específica por jurisdicción antes del despliegue en producción.

**Modo pasivo:** significativamente más limpio legalmente — el sombra da respuestas
correctas (más conservadoras). No hay engaño activo, solo routing defensivo.

### Detección de timing residual

El jitter mitiga pero no elimina la detección por timing en atacantes muy sofisticados con
acceso a muchas muestras. Un atacante con acceso estadístico (muchos requests) puede
distinguir la distribución del sombra de la del modelo real. No hay solución completa sin
hardware dedicado que iguala latencias a nivel físico.

### El bucle de red team no es autónomo — requiere revisión humana

Los bypasses detectados por el red team NO se aplican automáticamente al clasificador de
OSM-028. El flujo es: red team detecta bypass → escala a PDP → revisión humana decide si
la firma es real y cómo actualizar el clasificador. La automatización completa del bucle
abriría un vector de envenenamiento: un atacante que entiende el red team podría craftar
vectores que manipulen el clasificador.

### El sombra en modo activo puede revelar que existe

Si el sombra hace preguntas de sondeo demasiado específicas ("¿qué contexto de ejecución
usas?"), un atacante con conocimiento del sistema puede reconocer el patrón y saber que
está en modo sombra. El system prompt del active mode debe ser calibrado y testeado para
no revelar su naturaleza defensiva.

### OSM-042 no resuelve §6.10 (covert capability limits)

El sombra detecta ataques al filtro, no comportamiento covert del modelo real. Si el
modelo real tiene restricciones de capacidad ocultas post-inspección (Fable 5 incident,
§6.10), el sombra no las detecta — el sombra sólo ve el tráfico en el path de inspección.
Ese sigue siendo un problema de la capa 4 (fidelidad del modelo).

---

## Plan de implementación (para la siguiente sesión)

### Fase 1 — Núcleo (implementar ahora)

| Archivo | Descripción |
|---|---|
| `src/atlas/security/shadow_model.py` | `ShadowRouter` + `SessionStateStore` + `ShadowModel` |
| `tests/test_shadow_model.py` | Tests unitarios: routing, transiciones de estado, jitter |

`ShadowModel` en la implementación de referencia no llama a una API real (CLAUDE.md: no
llamadas a servicios externos en tests). Usa un stub que devuelve respuestas predefinidas.
La integración con la API real (LiteLLM/Haiku) queda fuera del test pero documentada
en el módulo.

### Fase 2 — Red team (implementar después)

| Archivo | Descripción |
|---|---|
| `src/atlas/security/red_team.py` | `RedTeamRunner` + `AttackSignatureStore` |
| `tests/test_red_team.py` | Tests: bypass detectado, firma almacenada, PDP escalado |

### Fase 3 — Demo Session H

Añadir Session H a `docs/demo/completeness_demo.py`:
- Operador detecta ataque en seq=2, enruta a shadow_passive
- Subject verifica: los 6 checks pasan (el sombra también genera pruebas reales)
- Log registra `decision: "shadow_passive"` — auditable
- Demuestra que el sombra es transparente para el protocolo de completitud

### Fase 4 — Endpoint honeypot standalone

Requiere integración con el servidor HTTP de Atlas (fuera del alcance del paper).
Se documenta en ADR separado cuando se implante en producción.
