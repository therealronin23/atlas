## 🚀 RESUMEN HOY — 25 de Mayo, 2026

### ✅ ACCIONES COMPLETADAS (Fase 1 de QUICK_START_3DAYS.md)

#### 1. Instalación de Prometheus
- **Estado:** Pendiente entrada de contraseña en terminal
- **Archivos creados:**
  - `/tmp/atlas-prometheus/prometheus.yml` — Config Prometheus (scrape targets Atlas)
  - `/tmp/atlas-prometheus/atlas_alerts.yml` — 10+ alert rules (memory, thermal, task failure, etc.)
  - `/tmp/atlas-prometheus/alertmanager.yml` — Config AlertManager

#### 2. Configuración de Atlas (.env)
- ✅ `ATLAS_PROMETHEUS=1` — Habilita Prometheus exporter
- ✅ `ATLAS_PROMETHEUS_PORT=9091` — Puerto del exporter
- ✅ `ATLAS_SERVE_DASHBOARD=1` — Habilita dashboard en puerto 7331
- ✅ `ATLAS_THERMAL_MONITOR=1` — Habilita watchdog de temperatura

#### 3. Scripts de Automatización
- ✅ `start_prometheus.sh` — Script todo-en-uno para iniciar Prometheus + AlertManager + Atlas
- ✅ `verify_prometheus.sh` — Script para verificar que todo está scrapeando correctamente

---

### 📋 PRÓXIMOS PASOS (EN ORDEN)

#### PASO 1: INSTALAR PROMETHEUS (1min)
**Acción:** Introduce tu contraseña de sudo en la terminal que ves en pantalla

Terminal muestra:
```
[sudo] contraseña para ronin:
```

👉 **Escribe tu contraseña y presiona Enter**

El sistema ejecutará:
```bash
sudo apt-get update && sudo apt-get install -y prometheus prometheus-alertmanager
```

#### PASO 2: VERIFICAR INSTALACIÓN (2min)
```bash
cd /home/ronin/proyectos/atlas-core
source .venv/bin/activate
set -a && source .env && set +a

# Verificar que Prometheus está instalado
prometheus --version
alertmanager --version
```

**Esperado:**
```
Prometheus, version 2.x.x
Alertmanager, version 0.x.x
```

#### PASO 3: INICIAR PROMETHEUS (3min)
```bash
# Terminal 1: Iniciar Prometheus + AlertManager + Atlas
cd /home/ronin/proyectos/atlas-core
./start_prometheus.sh
```

**Lo que hace:**
1. Inicia AlertManager en puerto 9093
2. Inicia Prometheus en puerto 9090
3. Inicia Atlas Core (Dashboard en 7331, Exporter en 9091)

**Esperado en logs:**
```
✅ Prometheus activo
✅ AlertManager activo
✅ Atlas Prometheus Exporter activo
🚀 Iniciando Atlas Core con ATLAS_PROMETHEUS=1
```

#### PASO 4: VERIFICAR EN NUEVA TERMINAL (2min)
```bash
# Terminal 2: Nueva terminal
cd /home/ronin/proyectos/atlas-core
./verify_prometheus.sh
```

**Esperado:**
```
✅ Prometheus activo en http://localhost:9090
✅ AlertManager activo en http://localhost:9093
✅ Atlas Dashboard activo en http://localhost:7331
✅ Atlas Prometheus Exporter activo en http://localhost:9091/metrics
✅ Prometheus targets activos: atlas [UP]
✅ Atlas está exportando métricas:
   atlas_task_count 0
   atlas_memory_usage_bytes 123456789
   ...
```

---

### 🌐 URLS PARA MONITOREO (DESPUÉS DE INICIAR)

| Servicio | URL | Propósito |
|----------|-----|----------|
| **Atlas Dashboard** | http://localhost:7331 | Status, tareas, memoria, auditoría |
| **Prometheus Web UI** | http://localhost:9090 | Métricas, targets, alertas |
| **Prometheus Targets** | http://localhost:9090/targets | Ver estado de scrape de Atlas |
| **AlertManager** | http://localhost:9093 | Alertas activas, routing |
| **Métricas Raw** | http://localhost:9091/metrics | Formato texto Prometheus |

---

### 📊 MÉTRICAS QUE PROMETHEUS SCRAPEARÁ

Atlas exporta en tiempo real:

**Tareas:**
- `atlas_task_count` — Total de tareas ejecutadas
- `atlas_task_failed_total` — Tareas fallidas

**Memoria:**
- `atlas_memory_usage_bytes` — Uso actual
- `atlas_memory_peak_bytes` — Pico histórico

**Thermal:**
- `atlas_thermal_temperature_celsius` — Temperatura actual
- `atlas_thermal_operational_mode` — NORMAL (0) / DEGRADED (1) / OMEGA (2)

**Seguridad:**
- `atlas_security_merkle_verify_failed_total` — Fallos de verificación Merkle
- `atlas_security_pending_approval_oldest_timestamp` — Timestamp de aprobación más antigua

**Inferencia:**
- `atlas_inference_provider_availability` — Disponibilidad del proveedor LLM
- `atlas_inference_latency_milliseconds` — Latencia de inferencia

**Caché:**
- `atlas_cache_ghost_replay_hits_total` — Hits en cache topológico
- `atlas_cache_ghost_replay_evictions_total` — Evictions por presión de memoria

---

### 🔔 ALERTAS CONFIGURADAS

Atlas_alerts.yml tiene 10+ reglas:

| Alerta | Condición | Severidad | Acción |
|--------|-----------|-----------|--------|
| `AtlasMemoryUsageHigh` | >1GB × 5min | WARNING | 1h repetition |
| `AtlasMemoryUsageCritical` | >2GB × 2min | CRITICAL | 5m repetition |
| `AtlasTemperatureWarning` | >70°C × 5min | WARNING | 1h repetition |
| `AtlasTemperatureCritical` | >80°C × 2min | CRITICAL | 5m repetition |
| `AtlasTaskFailureRateHigh` | >10% × 5min | WARNING | 1h repetition |
| `AtlasMerkleVerifyFailure` | Cualquier fallo × 1min | CRITICAL | Audit required |
| `AtlasInferenceProviderDown` | Provider == 0 × 5min | WARNING | 1h repetition |
| `AtlasHermesUnreachable` | Hermes == 0 × 2min | WARNING | Fallback active |
| `AtlasGhostReplayEvicted` | >100 evicts/5min | INFO | Memory pressure |
| `AtlasKuzuVectorStoreLoadHigh` | >80% capacity × 10min | WARNING | 1h repetition |
| `AtlasPendingApprovalsStale` | >24h old × 30min | INFO | Manual review |

---

### 💾 ARCHIVOS MODIFICADOS/CREADOS

```
/home/ronin/proyectos/atlas-core/
├── .env (ACTUALIZADO)
│   ├── ATLAS_PROMETHEUS=1
│   ├── ATLAS_SERVE_DASHBOARD=1
│   └── Rutas de config Prometheus/AlertManager
├── start_prometheus.sh (NUEVO)
│   └── Script todo-en-uno: AlertManager + Prometheus + Atlas
├── verify_prometheus.sh (NUEVO)
│   └── Script de verificación: targets, métricas, alertas
└── /tmp/atlas-prometheus/ (NUEVO)
    ├── prometheus.yml — Prometheus config
    ├── atlas_alerts.yml — Alert rules
    └── alertmanager.yml — AlertManager config
```

---

### 🎯 CHECKLIST EJECUCIÓN

- [ ] **PASO 1:** Instalar Prometheus (introduce contraseña sudo)
- [ ] **PASO 2:** Verificar instalación (`prometheus --version`)
- [ ] **PASO 3:** Iniciar `./start_prometheus.sh`
- [ ] **PASO 4:** En nueva terminal, ejecutar `./verify_prometheus.sh`
- [ ] **PASO 5:** Verificar 5/5 servicios ✅
- [ ] **PASO 6:** Acceder a http://localhost:9090/targets → Atlas [UP]
- [ ] **PASO 7:** Acceder a http://localhost:9091/metrics → Métricas visibles
- [ ] **PASO 8:** Documentar: anotar URLs, tokens, configuraciones críticas

---

### ⚠️ TROUBLESHOOTING RÁPIDO

**P: "Prometheus: Connection refused"**
→ Verificar: `curl http://localhost:9090/-/healthy`

**P: "Atlas Exporter no exporta métricas"**
→ Revisar: `curl http://localhost:9091/metrics` | head -20

**P: "Alertas no se disparan"**
→ Revisar: http://localhost:9093 → ¿AlertManager está arriba?

**P: "Error 'prometheus: command not found'"**
→ Instalación incompleta. Reintentar PASO 1.

---

### 📚 REFERENCIAS

- **Prometheus Setup Completo:** `docs/prometheus_setup.md`
- **Quick Start 3 días:** `docs/QUICK_START_3DAYS.md`
- **Roadmap 30 días:** `docs/ROADMAP_30DAYS_ITEMS_1_2_3.md`
- **Implementación Items 2-3:** `docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md`

---

### 🏁 RESUMEN FINAL

✅ **HOY (25 mayo) está 80% listo:**
- ✅ Prometheus + AlertManager + Atlas configurados
- ✅ Scripts de automatización listos
- ⏳ Falta: Introducir contraseña sudo + ejecutar scripts

**Tiempo total HOY: 8 minutos de ejecución manual**

**PRÓXIMO:** Mañana (26 mayo) — diseño review Hermes webhook

---
