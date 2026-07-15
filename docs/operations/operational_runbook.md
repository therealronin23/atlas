# Runbook operativo — Atlas Core

**Revisado:** 2026-07-16
**Alcance:** separar salud local, contrato aislado y evidencia externa viva.

## 1. Preflight factual

Desde la raíz del repositorio:

```bash
source .venv/bin/activate
PYTHONPATH=src atlas reality --json
```

No cargar `.env` con `source`: los scripts operativos vigentes usan
`scripts/safe_dotenv.py`, que lo interpreta como datos, exige fichero regular
privado y no expande shell.

Interpretación de Hermes:

- `mock` / `degraded`: no hay canal configurado y no es un fallo del core.
- `configured`: la forma de la configuración es válida; no prueba alcance.
- `live_verified=false`: resultado esperado del recolector estático. Solo un
  smoke explícito puede aportar evidencia viva.

## 2. Salud local

```bash
PYTHONPATH=src atlas audit --verify
PYTHONPATH=src atlas doctor
PYTHONPATH=src atlas health
PYTHONPATH=src atlas reality --run-checks --json
```

`--run-checks` ejecuta suite core y mypy en el checkout actual. El navegador se
incluye solo con `--include-browser`; una instalación de Chromium no demuestra
que una navegación concreta funcione.

No ejecutar el CLI contra el workspace vivo mientras otro proceso escribe la
misma cadena Merkle. La auditoría autónoma usa deliberadamente
`.atlas-audit-home` aislado.

## 3. Canal Hermes→Atlas en aislamiento

```bash
PYTHONPATH=src python scripts/twin_e2e_smoke.py
```

Esta prueba crea un repo y workspace temporales, firma un intent con nonce,
comprueba grounding contra commits sembrados y verifica la entrada Merkle.
Conclusión permitida: el contrato funciona en aislamiento. No concluye nada
sobre VPS, proveedor o Telegram.

## 4. Despliegue Hermes oficial

El despliegue es un efecto externo y solo se ejecuta cuando esté decidido por
el operador. Preparar `.env` desde `.env.example`, mantenerlo `0600` y usar un
host SSH ya enrolado:

```bash
chmod 600 .env
VPS_HOST=<tailscale-ip-o-nombre-completo.ts.net> \
  scripts/deploy_hermes_vps_oneshot.sh
```

El wrapper rechaza IP pública, hostname arbitrario, host key nueva, sintaxis
dotenv ambigua, secreto corto, proveedor/modelo implícitos y usuarios Telegram
no numéricos. El provisionador instala el commit fijado y corre como usuario
`hermes`; no instala Ollama ni habilita hooks automáticamente.

## 5. Verificación del pairing

```bash
VPS_HOST=<tailscale-ip-o-nombre-completo.ts.net> \
  scripts/verify_twin_pairing.sh
```

Un resultado verde demuestra, en esa ejecución:

- servicio activo con usuario dedicado y no-new-privileges;
- checkout igual al commit auditado;
- skill remota igual al artefacto local y root-owned;
- health firmado Hermes→Atlas con gobierno/Merkle sanos.

No demuestra una inferencia del proveedor ni entrega Telegram. Para promover
Hermes a `ACTIVO`, ejecutar además una solicitud real desde un usuario Telegram
permitido, observar respuesta del modelo y conservar hora/resultado sin copiar
tokens o secretos al repo. Si una de las dos capas falla, informar cuál; no
resumir el conjunto como “Hermes vivo”.

## 6. Canal Atlas→Hermes

Configuración SSH:

```text
HERMES_KANBAN_TRANSPORT=ssh
HERMES_SSH_HOST=root@<tailscale-ip-o-nombre-completo.ts.net>
```

Después reiniciar Atlas con el entorno actualizado y realizar una delegación
intencional de bajo riesgo. Verificar el resultado kanban y la entrada Merkle.
El login SSH puede provisionar como root, pero `KanbanBridge` ejecuta el binario
como usuario `hermes`. No hay destino por defecto ni fallback a IP pública.

## 7. Telegram propio de Atlas

Es distinto del Telegram gestionado por Hermes. Atlas usa
`TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`/`TELEGRAM_CHAT_IDS`, además de su
perfil de permisos. Probar `/status`, `/pending` y un rechazo/aprobación de bajo
riesgo desde un chat autorizado. No poner passphrases, tokens ni payloads
sensibles en la evidencia.

## 8. Troubleshooting

| Síntoma | Comprobación segura |
| --- | --- |
| `safe_dotenv` rechaza `.env` | Confirmar fichero regular, dueño actual, modo `0600`, claves únicas y sintaxis literal `KEY=value`. |
| Pairing no alcanza VPS | `tailscale status`; confirmar nombre `.ts.net`/IP privada y host key SSH pre-enrolada. |
| Servicio Hermes caído | `ssh -o StrictHostKeyChecking=yes root@<tailscale-host> 'systemctl status hermes-agent.service --no-pager'`. |
| Pairing verde, Telegram falla | Revisar `TELEGRAM_ALLOWED_USERS`, token y logs de la unidad; no culpar al canal Atlas firmado. |
| Pairing verde, modelo falla | Validar proveedor/modelo y cuota con una inferencia real; configuración no equivale a disponibilidad. |
| Pending no carga | Verificar `ATLAS_PENDING_HMAC_KEY`; los envelopes legacy sin MAC se rechazan. |

No usar las antiguas instrucciones Docker, puertos REST `8443`, IP pública o
`/root/.hermes`: son del stub histórico. `scripts/hermes_smoke.py` y
`scripts/operational_smoke.py` validan compatibilidad REST, no el Hermes-Agent
nativo.

## 9. Plantilla de evidencia

```text
Fecha UTC:
Commit Atlas:
atlas reality: estado + límites
Merkle verify: PASS/FAIL
Suite core/mypy: PASS/FAIL
Twin aislado: PASS/FAIL/SKIP
Pairing vivo: PASS/FAIL/SKIP
Inferencia Hermes real: PASS/FAIL/SKIP
Entrega Telegram real: PASS/FAIL/SKIP
Motivo de cada SKIP:
```
