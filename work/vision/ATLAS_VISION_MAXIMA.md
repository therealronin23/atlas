# ATLAS — visión máxima defendible

Fecha de corte: 2026-08-12. Estado: **hipótesis estratégica no normativa**.
Este documento nunca se autoaplica, no modifica el canon y no autoriza roadmap,
dependencias, proveedores, instalaciones ni efectos. Toda divergencia exige ADR,
experimento falsable, rollback y decisión humana.

## Tesis

El mejor Atlas defendible no es “un aparato de auditoría con un runtime dentro”.
Es un **runtime local soberano tratado como no confiable, colocado detrás de un
plano de control y evidencia que el runtime no puede omitir ni reescribir por sí
solo**.

Eso conserva la identidad útil de Atlas —coordinación local de herramientas,
modelos, memoria, aprobación y mejora— pero rebaja cualquier claim que dependa
de autoatestación. La evidencia se usa para limitar autoridad y decidir; no como
decoración posterior.

Base de evidencia y límites:
`work/research/OVERSIGHT_TRANSPARENCY_MCP_VETTING_2026-08-12.md`.

## Arquitectura objetivo

```text
operador / cliente autenticado
            |
            v
plano de control fuera del runtime
  identidad · idempotencia · expected_version · Policy/HITL
            |
            v
runtime Atlas no confiable -> sandbox/AST Guard -> efecto acotado
            |                                  |
            +-------------- resultado --------+
                               |
                               v
plano de evidencia append-only
  issuer · policy · statement · receipt · outcome
                               |
                               v
checkpoints cosignados por witnesses independientes + monitores
```

### 1. Control antes del efecto

- Toda mutación cruza un contrato único de command/effect: identidad propagada,
  idempotency key, precondición de versión, Policy/HITL, timeout, retry explícito,
  resultado ambiguo y reconciliación.
- `sensitivity="high"` y los efectos irreversibles usan control síncrono. Los
  monitores asíncronos sirven para analytics, detección y defensa en profundidad,
  no como sustituto de admisión. AISI midió precisamente esa diferencia en su
  [evaluación adversarial](https://www.aisi.gov.uk/blog/stress-testing-asynchronous-monitoring-of-ai-coding-agents).
- El bridge 7341 no crece mientras ADC-WO-107 esté `CONTRADICTED`. Las dos salidas
  documentadas —restaurar proyección o aprobar un contrato mutante supersesor—
  son incompatibles y requieren decisión del operador.

### 2. Evidencia que reconoce lo que no sabe

- Merkle conserva integridad de lo anexado; no se etiqueta como completitud.
- Statements de admisión, decisión, ejecución y outcome quedan separados. El
  receipt fija inclusión y política aplicada; no certifica que el statement sea
  verdadero. Éste es el límite explícito de
  [SCITT/RFC 9943](https://www.rfc-editor.org/rfc/rfc9943.html).
- Inclusion/consistency proofs locales son una primera capa. Claims de
  non-equivocation requieren witnesses con estado, quorum y claves/dominios de
  fallo independientes, siguiendo el patrón
  [C2SP](https://c2sp.org/tlog-cosignature@v1.0.1).
- `logging.merkle_logger` y `transparency.log` no se declaran un sistema único
  hasta definir autoridad, migración, compatibilidad y una prueba estructural de
  que cada efecto gobernado llega al plano de evidencia.

### 3. Admisión MCP como supply-chain, no como catálogo

- Registry/namespace es procedencia, no confianza. La admisión fija bytes y
  origen, compara SBOM publicado con inventario de staging, verifica identidad y
  digest de firma, valida in-toto/SLSA, ejecuta trial aislado y emite receipts.
- Static scan, Security Council, sentinel y plugin admission convergen en una
  sola decisión antes de instalar o activar, o se documenta formalmente por qué
  existen gates distintos y qué bypasses quedan posibles.
- Revocación es primera clase: nueva CVE, cambio de digest, provenance inválida,
  divergencia SBOM/inventario o pérdida de witness quorum retiran admisión sin
  tocar el árbol principal.
- Ningún tercero se clona para “investigar”; cualquier instalación/ejecución
  sigue siendo consentida, fail-closed y reversible.

### 4. AI Control medido sobre Atlas real

- Un benchmark Atlas especifica adversario, tools, concurrencia, latencia,
  presupuesto humano y efectos. Red team ataca router, monitor, logs, subagentes,
  aprobación y recuperación, no sólo prompts.
- El scorecard conserva safety y utility por separado: attack success, FPR/FNR,
  utilidad, latencia, coste, recuperación y efectos ambiguos. Ctrl-Z demuestra
  que ese trade-off se puede medir, pero sus cifras no son targets Atlas:
  [Bhatt et al.](https://arxiv.org/abs/2504.10374).
- Ningún “6/6” sustituye evidencia de efectos: un grader debe derivar cada punto
  de eventos observados y receipts, como mostró el fallo honesto de F2.6.
- El caso de seguridad declara su techo de atacante. AISI considera insuficientes
  los métodos actuales para su ACL-5; Atlas no afirma cubrirlo:
  [marco ACL](https://www.aisi.gov.uk/blog/how-to-evaluate-control-measures-for-ai-agents).

### 5. Memoria y trabajo durables sin autoridad duplicada

- La memoria conserva propietarios especializados; un promotor gobernado sólo
  se activa tras A/B temporal/privacidad/abstención con retirada demostrada.
- El trabajo durable registra selectivamente Mission, Task, comando, aprobación,
  efecto y receipt. No se convierte cada mutación interna en event sourcing.
- La reconstrucción debe sobrevivir kills en admisión y efecto ambiguo, en otro
  proceso, sin leer dueños legacy mutables. Hasta entonces ADR-069 sigue siendo
  diseño provisional, no capacidad por analogía con snapshots de Task.

### 6. Producto: host intercambiable por contratos medidos

- Code OSS/VSCodium permanece incumbent provisional porque existe un spike Atlas
  pequeño y limpio; Theia es challenger medido porque ofrece una superficie
  oficial diferente con gaps declarados. Tamaño de repositorio y código ya
  escrito son proxies/sunk cost, no TCO.
- Cuando Cut 2 sea autorizado, ambos se comparan con el mismo experimento:
  build/start, paridad de contratos, delta host, una actualización upstream,
  packaging, memoria/CPU/latencia y rollback. No se decide el host por narrativa.
- Android y Native siguen proyecciones separadas. Wave 5 no se abre sin sus gates
  constitucionales y autorización explícita.

### 7. Canon compilable, no sólo inventariado

- El canon válido conserva `scripts/check_canon.py` como gate de consistencia.
  La palabra “compiler” se reserva para un comando determinista input→canon con
  inputs fijados, normalización declarada y reproducción byte-for-byte o
  equivalencia canónica verificada.
- Los 13 ZIP y sus conflictos sirven como evidencia histórica trazable; aumentar
  su número sin reducir ambigüedad o reproducir outputs sólo aumenta superficie
  que verificar.

## Divergencias deliberadas respecto del plan actual

1. La frontera primaria deja de ser “runtime con auditoría” y pasa a ser
   “runtime detrás de control/evidencia externamente impuestos”. Esto exige
   evidencia de independencia, no sólo nuevas clases dentro del mismo proceso.
2. La transparencia fuerte no se da por cerrada con RFC 9162 ni con witness
   in-process. Requiere protocolo y operación multi-actor.
3. Supply-chain MCP no termina en scan estático o firma válida: incluye
   provenance, trial, receipts, revalidación y revocación.
4. Roadmap y hosts pierden prioridad frente a falsificadores: no se construye la
   capa siguiente para obtener evidencia que debía precederla.
5. Un ledger de coste local sigue siendo telemetría parcial; no se presenta como
   billing ni cuota de cuenta.

## Pruebas que podrían promover esta visión

- Un effect gateway aislado bloquea bypasses directos y reconcilia retries/kills
  con receipts correlacionados.
- Un monitor externo demuestra que todos los efectos gobernados están presentes;
  ataques off-path quedan detectados o fail-closed.
- Dos o más witnesses independientes rechazan árboles inconsistentes en una
  prueba de partición; clientes exigen quorum antes de confiar.
- Un bundle MCP completo detecta digest, SBOM, signer/provenance y CVE adversos,
  y el trial no recibe credenciales ni capacidad de efecto.
- El benchmark de control se reproduce con intervalos y muestra safety/utility
  bajo ataques iterativos, multi-instancia y al router.
- El journal selectivo reconstruye estado y efectos ambiguos tras kill.
- Los spikes isomorfos permiten decidir host con coste de actualización medido.
- El compiler de canon reproduce registros desde inputs fijados.

Hasta que cada prueba exista, su afirmación correspondiente permanece **NO
VERIFICABLE**. Ningún apartado anterior es permiso para implementarla.
