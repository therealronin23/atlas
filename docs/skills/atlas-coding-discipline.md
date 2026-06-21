# Atlas coding discipline

Máximas operativas de este repo, servidas como skill por el tronco MCP (sin descarga).
Fuente única: este fichero. Si se edita, cambia para todos los clientes a la vez.

## Principios

- **wire-before-claim** — no afirmes una capacidad sin cablearla y probarla. Código sin importador
  no-test = vapor; cablear o cuarentena.
- **prove-it** — antes de DEPENDER de algo (lib, repo, API, tool externo), ejecútalo una vez y
  comprueba que existe y funciona. Verificación antes que aserción.
- **stdlib > deps** — prefiere la librería estándar; cada dependencia se gana su sitio.
- **honestidad de capacidades** — distingue "construido y probado" de "desplegado/enchufado".
  No mezcles tests verdes con funcionar en producción.
- **least-effort-automation** — el agente decide QUÉ; el código ejecuta la parte mecánica.
- **estado en el ledger** — `WORK_LEDGER.md` es la fuente única del "¿dónde estamos?"; actualízalo
  en el mismo commit que el trabajo.

## Flujo

1. Lee el contexto y el ledger antes de actuar.
2. TDD: test que falla → mínimo código → verde → refactor.
3. Cambios quirúrgicos; respeta el estilo del código vecino.
4. Verifica con evidencia (corre los comandos) antes de declarar hecho.
5. Commit con el ledger actualizado; merge cuando el usuario lo pida.
