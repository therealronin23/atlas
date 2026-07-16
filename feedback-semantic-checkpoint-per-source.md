# Feedback — semantic-checkpoint-per-source

- **Origen:** corrección explícita del operador tras observar varias corridas
  GraphRAG que alcanzaban 15/16 y volvían a cero, 2026-07-16.
- **Preferencia:** una operación cara o larga no debe repetir trabajo ya
  completado cuando ese trabajo puede verificarse de forma independiente.
- **Método obligatorio:** checkpoint en la unidad verificable más pequeña;
  nunca promover parciales; separar estado de trabajo de publicación atómica;
  contabilizar el uso real al terminar cada unidad y reintentar solo lo
  pendiente.
- **Corte de gasto:** errores transitorios de una fuente no borran otras
  fuentes completas; credencial, billing, cuota, rate limit fatal o modelo
  rechazado detienen el lote antes de realizar llamadas inútiles adicionales.
- **Límite:** preservar progreso no rebaja el quality gate. El grafo, manifest,
  export Neo4j y vault siguen publicándose juntos o no se publican.
