# OPEN_QUESTIONS — Atlas OS

Decisiones que corresponden al OPERADOR o que requieren digest formal antes de
cerrarse. No bloquear el trabajo por ellas: cada una tiene default declarado.

1. **Upgrade de node 18 → 20/22 LTS.** Default actual: pin Vite 5 (funciona).
   Con node 20+ se abre Vite 7 y tooling moderno. Decisión de sistema → operador.
2. **Tauri sí/no y cuándo.** Default: web-first (ADR-059). Re-evaluar con
   digest cuando haya shell estable y el operador quiera desktop.
3. **Librería de grafo para miles de nodos** (Kuzu real en UI): Sigma vs
   Cytoscape vs WebGL custom. Default: SVG+d3-force hasta que un fixture real
   supere ~300 nodos. Requiere digest formal (INVESTIGATE, D4).
4. **Ejecución real de intents desde la UI** (POST /intent → Orchestrator).
   Default: simulated pipeline. El paso a real exige decidir el transporte al
   singleton del service_runner (¿socket local? ¿cola en workspace?) y gates
   HITL visibles. NO instanciar Orchestrator en el bridge (ADR-058).
5. **Import de conversaciones externas (Claude/ChatGPT/Cursor)**: formato de
   export cambia por proveedor y ToS. Default Fase 8: parser de fixture propio
   + import manual de JSON exportado por el usuario. Digest antes de scraping.
6. **¿Exponer el bridge más allá de localhost algún día?** Default: NUNCA en
   v1 (bind 127.0.0.1). Si se quiere acceso remoto, pasa por el modelo HMAC de
   exec_api o mejor (decisión de seguridad con ADR propio).
