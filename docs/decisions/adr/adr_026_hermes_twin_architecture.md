# ADR-026 — Arquitectura twin Atlas + Hermes-Agent

- **Estado:** Aceptado; revisado el 2026-07-16
- **Sustituye:** el supuesto de que Hermes es un ejecutor REST propio de Atlas
- **Relacionado:** ADR-027 (entrada firmada), ADR-028 (kanban saliente), ADR-029 (auditoría inversa)

## Contexto

Atlas había usado el nombre Hermes para dos cosas distintas: un stub REST
propio y el agente oficial de Nous Research. Esa ambigüedad produjo contratos,
scripts y afirmaciones operativas incompatibles. Una decisión arquitectónica
no puede servir como prueba de que un VPS, un proveedor o Telegram estén vivos.

## Decisión

Atlas y el Hermes-Agent oficial son pares separados con una autoridad
asimétrica:

- Atlas conserva gobierno, permisos, contención y registro Merkle.
- Hermes puede gestionar conversación, proveedor y Telegram como servicio
  externo no confiable.
- Hermes→Atlas usa la skill `atlas-twin` y `/api/exec/*`, firmados con HMAC,
  timestamp y nonce de un solo uso.
- Atlas→Hermes usa `HermesKanbanAdapter` con transporte `local` o SSH
  privado/Tailscale explícito.
- Configuración significa únicamente que existen parámetros válidos. Solo una
  prueba viva y actual permite hablar de conectividad, inferencia o entrega.

No existe un “tool gateway” ficticio ni se adapta el Hermes oficial al antiguo
REST stub. `HermesRestAdapter` queda como compatibilidad heredada, claramente
separada del camino nativo.

## Despliegue decidido

La ruta canónica es:

1. `scripts/deploy_hermes_vps_oneshot.sh` construye un bootstrap mínimo desde
   `.env`, lo transfiere como fichero `0600` mediante SSH con host key ya
   enrolada y llama al provisionador.
2. `scripts/install_hermes_agent_vps.sh` instala la versión `0.18.2`, tag
   `v2026.7.7.2`, commit
   `9de9c25f620ff7f1ce0fd5457d596052d5159596`, usando el lock upstream y un
   instalador `uv` fijado y verificado por hash.
3. El proceso corre como usuario `hermes` sin login, con unidad systemd
   endurecida. Estado mutable en `/var/lib/hermes`; código en
   `/opt/hermes-agent`; skill twin root-owned y de solo lectura para el
   servicio.
4. Proveedor, modelo, usuarios Telegram y origen Atlas son explícitos. No hay
   Ollama, fallback o autoaprobación implícitos.
5. `scripts/verify_twin_pairing.sh` comprueba commit, identidad de servicio,
   artefacto de skill y health firmado. Deliberadamente no gasta tokens ni
   envía Telegram.

Las antiguas rutas `install_hermes_vps.sh`, `reconfigure_hermes_vps.sh` y
`hermes_unlock_skills.sh` fallan cerradas con código 64.

## Invariantes

- Ningún secreto se imprime, se pasa en argv o se obtiene ejecutando `.env`.
- El SSH remoto y las URLs Atlas deben ser privados o Tailscale.
- Una clave HMAC tiene al menos 32 bytes.
- El usuario de login SSH puede provisionar, pero el runtime nunca corre como
  root.
- La adopción upstream está fijada a material inmutable y su configuración se
  valida con el código de esa misma versión.
- Toda acción que entra en Atlas pasa por sus permisos y auditoría; Hermes no
  amplía privilegios.

## Estado operativo

Este ADR describe el diseño y los artefactos. En la auditoría del 2026-07-16,
`atlas reality --json` informó `hermes.mode=mock`, sin proveedor externo
configurado en el entorno inspeccionado. Por tanto no se afirma que el VPS,
Hermes, Telegram o un proveedor estén vivos. Evidencias históricas de otros
días permanecen históricas.

## Consecuencias y límites

- La continuidad remota depende de Tailscale/SSH, del proveedor elegido y del
  servicio externo; Atlas debe degradar honestamente cuando fallen.
- El secreto es simétrico: su compromiso exige rotación coordinada.
- La verificación de transporte no sustituye una inferencia real ni una entrega
  Telegram real.
- Cambiar versión, dependencias o modelo requiere una nueva revisión; no se
  sigue automáticamente `latest`.
