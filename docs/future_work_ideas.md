# Ideas de la literatura para la siguiente fase (post-arXiv)

<!-- Doc interno (nombres internos OK; NO entregable). 2026-06-20. -->
<!-- Capturado tras verificar las referencias del paper vía WebFetch. NO construir
     antes de publicar el arXiv: son extensiones / future work, evitar scope-creep. -->

## Ya en el paper como "Future directions" (no construir aún)
1. **Interop COSE / SCITT** (de SCITT, `scitt-arch`, `scitt-refusal`). Codificar los
   registros co-firmados como COSE Signed Statements → interoperar con el ecosistema
   SCITT (Transparency Services + Receipts) en vez de formato propio. **Alto valor
   estratégico**: pasa de "citamos a SCITT" a "interoperamos". Dep real → ADR cuando toque.
2. **Completitud en cadenas de agentes** (de Sello / Notarized Agents, `sello2026`).
   Counter-firma del receptor: cada salto firma lo que recibió. Extiende la completitud
   del par sujeto↔operador a flujos multi-salto / agénticos. Encaja con nuestro gateway.
3. **Attestation en dispositivo de consumo** (de Aegon, `aegon2026`). Android StrongBox /
   secure elements para receipts atestados por hardware → hace real la Capa 2 (clave
   ligada a dispositivo / TPM seed) en móviles, no solo servidores.

## Apuntadas (no en el paper) — combustible para Atlas / fases siguientes
4. **Capa de enforcement en runtime** (de Aegis, `aegis2026`). Nosotros detectamos/
   atribuimos; Aegis impide en ejecución (enforcement kernel, policy layer, shutdown
   triggers). Narrativa: nuestra completitud verificable = cimiento de confianza DEBAJO
   de un motor de políticas. Complementario, no competidor.
5. **Taxonomía de auditabilidad + benchmark de overhead** (de Auditable Agents,
   `auditableagents2026`). Dimensiones detect/enforce/recover + metodología empírica
   (reportan ~8.3ms overhead). Útil para AFINAR cómo medimos y enmarcamos nuestra
   evaluación, y como punto de comparación de latencia.
6. **Honeypots LLM** (HoneyGPT, arXiv:2406.01882). Técnicas concretas para mejorar la
   capa shadow/honeypot (OSM-042 / ADR-054 deception) y citarla como prior art de ese
   ángulo. Periférico.
7. **Aislamiento microarquitectural / side-channels** (CCS 2024,
   doi:10.1145/3658644.3690183, "Principled Microarchitectural Isolation on Cloud CPUs").
   Endurecer la discusión del límite de timing/side-channels y el sandbox BwrapJail.
   Periférico.

## Regla
Nada de esto bloquea el arXiv. El paper está completo y verídico. Estas ideas son la
**siguiente etapa**: priorizar 1 (COSE/SCITT) y 4 (enforcement) por valor estratégico;
el resto bajo demanda. Verificar deps (regla 6) y ToS antes de cada una.
