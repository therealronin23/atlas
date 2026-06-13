# ADR-047 — Verificación adversarial, grounding de dominio y asistencia al verificador (propuesto)

Fecha: 2026-06-13 · Estado: **propuesto** (diseño, sin código) · Contexto:
sesión estratégica Tomás+Claude; principios transversales de
`docs/direction_2026-06-12_construir_hacia_arriba.md`; ADR-041..046.

## Problema

A escala real, la mayoría de las acciones de Atlas **no tienen rollback** (un
mensaje enviado, un anuncio publicado, una oferta hecha). El modelo
"verificación asimétrica" de la capa 1 asume artefactos con un verificador más
barato; un *acto irreversible hacia fuera* no es un artefacto verificable por un
test. Y el verificador humano (ADR-040) es falible: puede no saber verificar, o
partir de premisas erróneas.

## Decisión (propuesta)

Tres piezas horizontales (sirven a todo dominio, no a uno):

### 1. Panel adversarial para acciones irreversibles

Un `ArtifactKind.IRREVERSIBLE_ACTION` cuyo verificador no es un test sino un
**panel de disenso**: N modelos (la cascada ya enruta a varios) con prompts
deliberadamente hostiles —"encuentra por qué esto es un error", "qué asume el
plan que podría ser falso", "qué se rompe en el peor caso"—. Consenso →
procede con la evidencia del disenso adjunta; sin consenso → escala al humano.
Es la generalización del gate de corroboración de *afirmaciones* a *acciones*:
cuando no puedes deshacer, pagas más caro por verificar antes.

### 2. Base de conocimiento de dominio (grounding)

Antes de empezar un proyecto, Atlas genera una **carpeta de conocimiento
verificada** (normativa, mercado, errores típicos, trampas) que ancla toda
generación posterior. Es la capa 4 (LessonStore) generalizada + un scout de
dominio que pasa por el gate de corroboración: la ley de entrada (sin Evidence,
no entra) es el antídoto contra alimentarse de basura. "Muleta y potenciador" =
grounding.

### 3. Asistencia al verificador humano

El humano conserva el criterio (ADR-040), pero Atlas debe **hacerlo mejor
verificador**: disenso calibrado apuntado a los planteamientos del propio
usuario. No "¿apruebas? [sí/no]", sino "esto asume tu plan y podría ser falso;
este es el contra-caso; este es mi grado de confianza; esto es lo que
probablemente no estás viendo". No es Atlas decidiendo por el humano; es Atlas
equipándolo para decidir bien.

## Límites explícitos (no son problemas de verificación)

- El panel adversarial **sube el suelo, no elimina el techo legal**: ninguna
  cantidad de verificación da una licencia regulada, ni cumple GDPR de datos de
  terceros, ni KYC anti-blanqueo. Confundir verificación con cobertura legal da
  falsa seguridad.
- **Evasión de baneos / derrota de CAPTCHAs queda fuera de alcance** como
  cimiento: carrera armamentística de upside limitado y downside ilimitado, y
  un CAPTCHA es el sistema marcando "no autorizado". Robustez de automatización
  *autorizada* (sesión, recuperación, horizonte largo) sí; derrotar anti-bot de
  terceros, no. Conecta con ADR-043 (autorización verificable).

## Consecuencias

- Las tres piezas son horizontales: se construyen una vez y sirven a cualquier
  vertical (mantenimiento, seguridad, inmobiliaria, research).
- Orden sugerido: panel adversarial primero (protege todo lo demás y es el más
  reusable), luego base de conocimiento.
- Pendiente de promover a aceptado cuando se diseñe el ADR de implementación.
