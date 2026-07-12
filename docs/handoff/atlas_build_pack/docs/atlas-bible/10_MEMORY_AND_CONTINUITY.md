# 10 — Memory and Continuity

## Tesis

El mayor diferenciador de Atlas es la continuidad cognitiva.

Atlas convierte historial disperso en memoria operativa.

## Tipos de memoria

```text
Episodic Memory      = conversaciones, sesiones, eventos
Semantic Memory      = conocimiento estable, conceptos, relaciones
Procedural Memory    = workflows, patrones, skills aprobados
Failure Memory       = errores, malas decisiones, evitar repetir
Identity Memory      = preferencias, estilo, límites, proyectos vitales
Project Memory       = decisiones y contexto de cada proyecto
Tool Memory          = qué herramienta funcionó mejor para qué caso
```

## Connected Accounts / Imports

Atlas debe poder importar:

```text
- Exportaciones de ChatGPT
- Conversaciones Claude
- Historial Cursor
- Notas/manual pastes
- Repositorios Git
- Documentos locales
```

## Pipeline de importación

```text
Import source
↓
Parse conversations/files
↓
Normalize messages
↓
Detect projects
↓
Extract decisions
↓
Extract patterns
↓
Extract preferences
↓
Extract failures
↓
Create graph nodes
↓
Store provenance
↓
Generate insights
```

## Entidades extraídas

```text
Conversation
Message
ProjectReference
Decision
Preference
Pattern
Mistake
ToolUsage
ExternalAnswer
UserStyle
ReusablePrompt
```

## Regla

Atlas no debe copiar ciegamente respuestas externas. Debe analizar, clasificar, contrastar y convertirlas en memoria con procedencia y confianza.
