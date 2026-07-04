# Idea-candidata: Atlas como herramienta universal (visión microkernel)

- **Estado**: candidata (sin triar por el Cónclave)
- **Procedencia**: conversación Tomás ↔ Claude Fable 5 (Claude Code), 2026-07-02.
  Transcripción de la sesión de valoración global post-Capa-0. Palabras del autor,
  estructuradas — no inventadas.
- **Gotas a las que sirve**: Gota 1 (modelo de usuario), Gota 2 (intención ambiente),
  Gota 6 (adaptación continua) + un eje nuevo: **arquitectura microkernel**.

## La visión, en palabras del autor (fiel)

- Herramienta **universal** que cualquiera use de forma intuitiva "como macOS,
  robusta como Linux, segura como seL4, y que no sea kernel sino **microkernel**".
- **Adaptación por profesión**: si la usa un arquitecto, el conocimiento y contexto
  de su dominio "se vinculan y descargan". Si la usa un gestor de rentas, Atlas
  automatiza el trabajo tedioso **incluso antes de que el usuario piense que puede
  serlo**, y le ayuda a presentar declaraciones a Hacienda sabiendo de antemano si
  serán aptas.
- **Proactividad con puntero**: "si se me olvida X, Atlas saca un puntero y dice:
  oye, has pasado esto por alto".
- **Prevención de consecuencias**: "si tomo una decisión que en el futuro me condena,
  la IA, sabiéndolo, debería prever esa situación y ayudarme a prevenirla".
- **Más allá de la complacencia**: no solo picar código o armar una app completa;
  ir un paso más allá de lo que se le pide.
- **La vara de medir**: "que Atlas sea todo lo que la ola actual (el estado del arte)
  pretende ser y no alcanza a ser. Como el Excel cuando usaban papel y lápiz."
- **El dolor raíz**: "que me conozca mejor que yo mismo y sea proactivo — no tener
  que vigilar y medir mis palabras buscando en un chat la mejor versión de la IA,
  perdiendo todo el contexto entre un chat y otro. Aunque tengas memoria, no me
  conoces; por más que me abra a ti, jamás me recordarás más allá de tu ventana
  de contexto."

## Lectura arquitectónica (del asistente, para el triaje)

1. **El microkernel ya existe en embrión**: los invariantes no-negociables
   (decider determinista, Merkle, HITL sensitivity=high, reversibilidad) son el
   núcleo pequeño y verificado; TODO lo demás (modelos, tools, profesiones,
   catálogo 700+) es userland reemplazable que puede fallar sin comprometer el
   núcleo. La visión seL4 no pide construir algo nuevo: pide NOMBRAR y sellar esa
   frontera. Hoy la frontera existe pero no está declarada como tal.
2. **El primitivo universal (lección Excel)**: Excel ganó por UN primitivo (la
   rejilla) que cada profesión moldeó, no por N modos verticales. El candidato a
   primitivo de Atlas: el lazo **memoria-verificada → modelo-de-usuario →
   decisión-grabada → anticipación**. Los "packs de profesión" (arquitecto,
   gestor) serían CONTENIDO cargable sobre ese primitivo (vía catálogo/skills ya
   existentes), no arquitectura nueva.
3. **Lo que falta de verdad** (mapeado a líneas vivas): Gota 1/UserModel (el
   corpus del RecordingDecider ya graba; falta la capa que modela), Gota 2
   (captura ambiente = el "puntero proactivo"), routing determinista (Pieza 3),
   UI/UX (inexistente; el autor lo declara). La "prevención de consecuencias" es
   Gota 1 + simulación sobre el corpus de decisiones — no tiene línea aún.
4. **Riesgo señalado**: "universal e intuitivo para cualquiera" y "una persona
   sola sin presupuesto" están en tensión. El triaje debe decidir el orden:
   primero que conozca a UNA persona (Tomás) mejor que nadie; la universalidad
   es la generalización posterior del mismo primitivo.

## Siguiente acción

Triar con el Cónclave junto al resto de conversaciones dispersas cuando el
embudo de ideas tenga 3-5 candidatas. No convertir en Gate en caliente
(regla de oro del MASTERPLAN).
