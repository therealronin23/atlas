# ADR-053 — Modelo de confianza y completitud del Compliance Gateway

Fecha: 2026-06-15 · Estado: **Aceptado (núcleo)** — núcleo invariante implementado
y verificado (97 tests del paquete; suite completa 1679 passed; mypy strict:
deferred to core layers (immunity submodule has known typing gaps; OSM-053 code
proper is clean); RFC 9162 verificado con fuzz por el auditor). Diferido:
attestation de hardware real (TDX/SEV-SNP) y red de witnesses distribuida. ·
Resuelve B1+B2 de la auditoría
`audit_adr051_052_premortem_2026-06-15.md`) · Contexto: ADR-051 (Compliance
Gateway), MerkleLogger (Gate F), ADR-029 (reverse-audit), ADR-040 (Decider).

> Este ADR existe porque la auditoría demostró que ADR-051 tenía la viga maestra
> rota: **Merkle prueba integridad, no completitud** (B1), y **no había operador
> neutral creíble** (B2). Aquí se cierran ambos con estándares de industria,
> no con invención propia.

---

## Hechos de partida (estándares, verificados 2026-06-15)

- **RFC 9162 — Certificate Transparency v2.** Log append-only sobre Merkle;
  *consistency proofs* prueban que un estado posterior contiene íntegro al
  anterior (no se reescribió historia); *inclusion proofs* prueban que una
  entrada está; la violación del append-only se detecta por **gossip de Signed
  Tree Heads (STH) entre witnesses**, contra el ataque de **vista partida**
  (mostrar logs distintos a partes distintas).
- **RFC 9334 — RATS (Remote Attestation).** Un *Attester* en enclave (Intel TDX
  → *TD Quote* firmado; AMD SEV-SNP → *attestation report* vía VCEK/VLEK)
  produce evidencia criptográfica de la medición del binario en ejecución; un
  *Verifier* la appraisa contra la medición esperada (build publicado).
  Topologías Background-Check y Passport.

---

## Decisión: tres capas, cada una atada a su estándar

### Capa 1 — Enrollment (la "firma única al aceptar")

Al darse de alta, el cliente del usuario genera un par de claves y **registra la
pública firmando el contrato** (sección 7 de ADR-051) una sola vez. Esto ata una
identidad a una clave de firma. Análogo al modelo *Passport* de RFC 9334.

> **Corrección al planteamiento inicial:** la firma única basta para *binding*,
> NO para *completitud*. Si el cliente no sigue co-firmando, la omisión de
> interacciones sueltas es indetectable. El enrollment habilita la co-firma
> continua de la Capa 2; no la sustituye.

### L2 — Co-firma continua + transparency log (resuelve B1)

- Cada interacción y **cada evento de inspección de contenido** se anexa a un log
  **append-only estilo RFC 9162** (se reutiliza y extiende el MerkleLogger
  existente, no se inventa uno nuevo).
- El cliente co-firma cada request con un **número de secuencia monótono**. Una
  laguna en su propia secuencia es detectable **por el propio usuario** → el
  operador no puede inspeccionar y "no apuntarlo", porque el registro va atado a
  un request co-firmado cuya secuencia el cliente vigila.
- **Consistency proofs** impiden reescribir historia. **Witnesses que cotillean
  STH** impiden la vista partida: usuario y regulador verifican contra el mismo
  STH atestiguado, así que el log no puede mentirle a uno sin que el otro lo
  detecte. **Esto es lo que hace verdadera la frase de venta de ADR-051.**
- L2 desdobla en **L2** (co-firma monótona + salting causal) y **L2b** (inspección de contenido bajo causa).

### L3 — Attestation del enclave + gossip + evasion detection (resuelve B2)

- **L3a — Enclave.** El inspector corre en VM confidencial (TDX/SEV-SNP) y emite
  un quote firmado que ata la medición a un **build reproducible y publicado**.
  Verifiers = **usuario Y regulador** appraisan el quote contra la medición
  publicada (RFC 9334, Background-Check).
- **L3b — Gossip de STH.** Witnesses independientes intercambian Signed Tree Heads
  para detectar vista partida. El usuario verifica que su STH es consistente con
  el STH que regulador ve.
- **L3c — Detección de evasión + behavioral drift.** Monitoreo continuo de cambios
  en las heurísticas de rechazo del modelo. Si la tasa de aceptación de cierta
  categoría desvía sin justificación operacional, escala a revisión (Decider). El
  log registra cada cambio de comportamiento, permitiendo análisis causal posterior
  y memoria inmune (ADR-049/054).

---

## Alcance honesto: qué se construye ahora y qué no

| Pieza | Estándar | Construible en solitario hoy | Plan |
|---|---|---|---|
| Log append-only + inclusion/consistency proofs | RFC 9162 | **Sí** (software puro, testeable) | **Build ahora** sobre MerkleLogger |
| Co-firma del cliente + secuencia monótona | — | **Sí** | **Build ahora** |
| Detector de omisión + vista partida (verify de STH) | RFC 9162 | **Sí** (con witness mínimo in-process para probar el mecanismo) | **Build ahora** |
| Attestation real TDX/SEV-SNP | RFC 9334 | **No** (depende de hardware/cloud) | Interfaz `AttestationProvider` + impl software ahora; real diferido |
| Red de witnesses distribuida + gossip | RFC 9162 | **No** (varios actores) | Estructura + verify ahora; despliegue = ecosistema |

> No prometo un CT log de producción ni un enclave atestiguado en un autobuild de
> 3 iteraciones: sería deshonesto. Se construye el **núcleo invariante** que prueba
> que B1 es resoluble en código; lo dependiente de hardware/varios-actores va tras
> interfaz, con su impl software para tests.

---

## Criterios de aceptación del núcleo (lo que validará el build)

1. Append-only verificable: dado un log L1 ⊆ L2, `verify_consistency(L1, L2)` pasa;
   ante reescritura de historia, falla.
2. Inclusión: `verify_inclusion(entry, STH)` pasa para entradas presentes, falla
   para ausentes.
3. **Detección de omisión:** si el operador inspecciona y NO registra, el cliente
   detecta la laguna en su secuencia co-firmada. Test que lo demuestra.
4. **Detección de vista partida:** dos STH inconsistentes para el mismo índice →
   el verificador de witness lo detecta. Test que lo demuestra.
5. `AttestationProvider` tras interfaz, con impl software que un test puede
   ejercitar; el inspector la consulta antes de operar.

## Consecuencias

- ADR-051 deja de flotar: su eje ("verifícalo, no confíes") pasa a ser
  demostrable con código y tests, no una promesa.
- Quedan abiertos (ecosistema, no código en solitario): operar witnesses reales,
  hardware confidential, certificación de terceros, modelo económico.
