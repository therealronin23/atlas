# ADR-084 — Perfil de Garantías y Cumplimiento (Membrana y Ósmosis)

- **Estado**: aceptado (2026-08-03)
- **Fecha**: 2026-08-03
- **Contexto previo**: ADR-049 (organismo de conocimiento), ADR-041 (UniversalVerifier), ADR-054 (gateway), OSM-024 (Osmosis Filter), ADC-WO-105.

## Contexto y Problema

El programa P12 (ADC-WO-105) definía la necesidad de establecer el "enforcement profile" (perfil de cumplimiento) definitivo para la membrana de confianza y los filtros de procedencia (Osmosis). 
Hasta ahora, la membrana existía como una línea de investigación de primera clase, pero el filtro de cumplimiento no tenía definido formalmente si operaba como una puerta de enlace opcional (lo cual socava las garantías del producto) o de paso obligatorio (lo que puede generar bloqueos catastróficos en el sistema en escenarios de emergencia).

Era necesario decidir el modo de despliegue, el límite de confianza (trust boundary), y la semántica de "bypass" en caso de fallo crítico en las validaciones, manteniendo la transparencia inmutable de la cadena Merkle.

## Decisión

El **Osmosis Filter** se establece como una capa de cumplimiento **in-path, server-side y obligatoria** para la admisión de peticiones de los LLM y la absorción de conocimiento. 

1. **Mandatoriedad por defecto (Fail-closed)**: Ninguna instrucción de LLM externa ni ningún artefacto de conocimiento (OSM) será absorbido sin cruzar la Membrana de Confianza y someterse al UniversalVerifier.
2. **Bypass Criptográfico (Logueado)**: Se admite un modo `bypass_mode=audit_only` exclusivo para emergencias operativas. Si se activa, las transacciones que violen políticas no serán bloqueadas, sino etiquetadas y registradas inmutablemente en el ledger de transparencia Merkle como "Violación Permitida por Emergencia". 
3. **Límite de Confianza**: El filtro de proveniencia asume confianza cero (Zero Trust) sobre el output bruto de cualquier LLM, independientemente del proveedor. El límite de confianza queda situado *después* de la verificación de firmas unívocas (*device-bound certificates*) asociadas a cada request.
4. **Rollback**: Si el gateway produce bloqueos generalizados de peticiones válidas (falsos positivos), el operador puede revertir la decisión cambiando la política de "enforcement" a "audit-only" temporalmente sin desmontar la infraestructura criptográfica.

## Consecuencias y Próximos Pasos

- **Registro**: Se cierra el work order `ADC-WO-105` del registro de implementación marcándolo como `DONE`.
- **Evolución**: El mecanismo de membrana de `docs/membrana/OSM-000_membrana.md` pasa a regirse por este marco de garantías para evaluar nuevas capacidades (OSM-XXX).
- **Desarrollo**: Los filtros futuros (ej. OSM-028) se desarrollarán con la expectativa de que su ejecución es de ruta crítica y no-bypassable (excepto por la bandera explícita de emergencia registrada en cadena).
