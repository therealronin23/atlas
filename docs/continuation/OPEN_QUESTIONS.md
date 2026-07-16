# OPEN_QUESTIONS — Atlas OS

Decisiones que corresponden al OPERADOR o que requieren digest formal antes de
cerrarse. No bloquear el trabajo por ellas: cada una tiene default declarado.

1. **Tauri sí/no y cuándo.** Default: web-first (ADR-059). Re-evaluar con
   digest cuando haya shell estable y el operador quiera desktop.
2. **Librería de grafo para miles de nodos** (Kuzu real en UI): Sigma vs
   Cytoscape vs WebGL custom. Default: SVG+d3-force hasta que un fixture real
   supere ~300 nodos. Requiere digest formal (INVESTIGATE, D4).
3. **Ejecución real de intents desde la UI** (POST /intent → Orchestrator).
   Default: simulated pipeline. El paso a real exige decidir el transporte al
   singleton del service_runner (¿socket local? ¿cola en workspace?) y gates
   HITL visibles. NO instanciar Orchestrator en el bridge (ADR-058).
4. **Import de conversaciones externas (Claude/ChatGPT/Cursor)**: formato de
   export cambia por proveedor y ToS. Default Fase 8: parser de fixture propio
   + import manual de JSON exportado por el usuario. Digest antes de scraping.
5. **¿Exponer el bridge más allá de localhost algún día?** Default: NUNCA en
   v1 (bind 127.0.0.1). Si se quiere acceso remoto, pasa por el modelo HMAC de
   exec_api o mejor (decisión de seguridad con ADR propio).
6. **(Fase 15) ¿Cuál es el primer conector real a implementar?**
   Recomendación en `phase15/RECOMMENDED_PHASE_16.md`: Gmail read-only
   (menor riesgo, receta ya completa). Decisión de producto → operador.
7. **(Fase 15) ¿Converger PolicyEngine con `/permissions/evaluate` ahora o
   dejarlos coexistir más tiempo?** Default: coexisten (D14). Converger
   exige tocar tests ya verdes de Fase 4 — decisión de alcance antes de
   tocarlo (ver IMPROVEMENT_PROPOSALS.md #1).
8. **(Fase 15) ¿Vault de secretos propio o delegar en un gestor del SO
   (keyring/pass)?** Default: solo referencias `env:VAR`, ningún backend.
   Requiere digest formal antes de elegir (options: keyring del SO, HashiCorp
   Vault local, age-encrypted file).

## Resuelta el 2026-07-16

- **Node 22 + Vite 7.** El operador autorizó cerrar las mejoras pendientes.
  ADR-059 fija Node 22.22.2, el lock queda sin avisos npm y CI instala, audita
  y construye el shell. No implica aceptar Tauri.
