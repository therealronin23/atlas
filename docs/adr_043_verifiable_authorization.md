# ADR-043 — Autorización verificable y artefacto de hallazgo de seguridad

Fecha: 2026-06-13 · **Estado: Propuesto** (sin código aún; registra el diseño
para revisión, siguiendo la convención del repo de que un ADR aceptado llega
con su implementación) · Contexto: `docs/roadmap_mythos_2026-06-13.md`,
ADR-041, ADR-042, ADR-040 (decider PDP).

## Problema

Atlas debe ser experto en seguridad ofensiva-defensiva: para custodiar datos
sensibles (bufetes, clínicas, gestorías) hay que saber cómo se entra. El
conocimiento es ilimitado; la **acción ofensiva activa** no puede serlo sin
gobierno, porque un Atlas que ataca cualquier target sin límite se convierte
en la mayor superficie de ataque del propio usuario (comprometerlo hereda la
capacidad apuntando a él y a sus clientes). Hace falta separar *saber* de
*disparar*, y que el "disparar" porte evidencia, no permiso ad-hoc.

## Decisión

Una capa de **autorización como artefacto verificable**, gemela del patrón
decider/PDP: el gate no es "un humano aprueba", es "no hay evidencia de
autorización que cubra (target, capacidad) → no se ejecuta".

### 1. `AuthorizationGrant`

Scope firmado y verificable. Campos mínimos:

- `target`: CIDR / dominio / hostname / repo / ruta (matcheable).
- `capabilities`: conjunto de clases — `RECON`, `FUZZING`, `EXPLOITATION`,
  `MUTATION`.
- `issued_at`, `expires_at`.
- `issuer`, `signature`.

### 2. `AuthorizationVerifier`

Gate sobre toda acción ofensiva *activa*. Dado `(target, capability)`,
deniega salvo que exista un grant válido, no expirado y con firma correcta que
lo cubra. Toda decisión (allow/deny) se loguea a Merkle. Acciones read-only
sobre código/targets propios (p. ej. `static_audit`) no requieren grant.

### 3. `SECURITY_FINDING` (nuevo `ArtifactKind`)

Hallazgo + reproducción. Su verificador **reproduce el PoC en
`LayeredIsolationSandbox`** contra un target controlado: reproducir es más
barato que descubrir (verificación asimétrica, capa 1, coste `SANDBOX`). Un
finding sin reproducción verde es `UNKNOWN`, nunca `PASS` — no se reporta una
vulnerabilidad que no se sabe reproducir.

## Tabla de decisiones

| # | Decisión | Elegida | Alternativa | Porqué |
|---|---|---|---|---|
| 1 | Naturaleza del límite | grant verificable (evidencia) | aprobación humana por acción | Mismo PDP del decider; el humano no debe ser el cuello de botella ni el único path |
| 2 | Qué se gobierna | la acción activa, no el conocimiento | restringir lectura de CVEs/papers | El saber es ilimitado por diseño; solo el disparo contra un target porta prueba |
| 3 | Firma | **stdlib `hmac`+`hashlib` (clave local) primero**; `cryptography`/ed25519 solo si hay grants multi-parte (consentimiento de cliente firmado por un tercero) | dep asimétrica desde el día 1 | Regla stdlib-first; para un sistema mono-usuario auto-autorizante, HMAC con clave local basta y es auditable. La dep se justifica en su propio ADR cuando aparezca el caso multi-parte |
| 4 | Verificador del finding | reproducción en sandbox existente | confiar en el reporte del modelo | Un finding no reproducible es ruido; la reproducción es la evidencia |
| 5 | Acciones read-only propias | sin grant | grant para todo | No friccionar el caso legítimo dominante (auditar lo propio) |
| 6 | Coste en `CostTier` | check de autorización `STATIC`/`FREE`; reproducción `SANDBOX` | — | Encaja en el eje ordinal existente |
| 7 | Frontera dura | nada de acción ofensiva activa contra targets sin grant, ni "detection evasion" para uso malicioso, ni mass-targeting | capacidad sin gobierno | La contención es la propiedad que hace a Atlas confiable para datos sensibles; quitarla lo hace secuestrable, no más fuerte |

## Alcance y límites explícitos

Esta capa habilita: pentesting autorizado, fuzzing, reproducción de exploits
en laboratorio, threat modeling, anticipación de vectores, investigación
defensiva, responsible disclosure. **No** habilita: ataque a sistemas sin
autorización declarada, evasión de detección para fines maliciosos,
targeting masivo. La diferencia es la presencia de un `AuthorizationGrant`
válido, verificable y auditado — no el juicio del modelo en el momento.

## Consumidores

- La cascada (capa 2) puede tener productores de seguridad cuyos artefactos
  son `SECURITY_FINDING`; suben solo con reproducción verde.
- El enjambre (capa 3) puede incluir workers de seguridad bajo envelope, con
  el grant como parte del envelope.
- LessonStore (capa 4) tipa cada finding reproducido como patrón de defensa.

## Pendiente antes de pasar a "Aceptado"

Implementación + tests (verificación de grant válido/expirado/fuera de scope,
reproducción de finding en sandbox, denegación auditada en Merkle, HMAC
stdlib), todo sin red ni subprocesos reales en los tests.
