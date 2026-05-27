# QUICK START — 3 Días (25-27 mayo)

**¿QUÉ HACER AHORA MISMO?**

---

## HOY (25 mayo) — 2 HORAS

### ✅ Prometheus Deployment (50 min)

```bash
# 1. Instalar Prometheus (macOS)
brew install prometheus

# 2. Crear config
mkdir -p /tmp/atlas-prometheus
cat > /tmp/atlas-prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'atlas'
    static_configs:
      - targets: ['localhost:7331']
    metrics_path: '/metrics'
EOF

# 3. Instalar AlertManager
brew install alertmanager

# 4. Crear alertas
cat > /tmp/atlas-prometheus/atlas_alerts.yml << 'EOF'
groups:
  - name: atlas_core
    interval: 30s
    rules:
      - alert: AtlasMemoryUsageHigh
        expr: atlas_memory_usage_bytes > 1000000000
        for: 5m
        annotations:
          summary: "Atlas memory >1GB"
EOF

# 5. Iniciar Prometheus
prometheus --config.file=/tmp/atlas-prometheus/prometheus.yml &

# 6. Verificar en browser
# http://localhost:9090
```

### ✅ Actualizar .env

```bash
# ~/proyectos/atlas-core/.env

ATLAS_PROMETHEUS=1
PROMETHEUS_CONFIG_PATH=/tmp/atlas-prometheus/prometheus.yml
ALERTMANAGER_URL=http://localhost:9093
```

### ✅ Iniciar Atlas con Prometheus

```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate
set -a && source .env && set +a

# Inicia Atlas
ATLAS_PROMETHEUS=1 atlas serve
# → Escucha en :7331
# → /metrics activo para Prometheus
```

### ✅ Verificar

```bash
# En otra terminal:
curl http://localhost:7331/metrics | head -20
# Deberías ver:
# atlas_task_count{status="completed"} 0
# atlas_memory_usage_bytes 524288000
# ...
```

**Tiempo:** 50 min ✅

### 📚 Documentación (10 min)

- Lee: `docs/prometheus_setup.md` (secciones 1-3)
- Entiende: Alertas, Grafana, troubleshooting

**DONE:** Prometheus deployado y documentado. ✅

---

## MAÑANA (26 mayo) — 2 HORAS

### 📋 Hermes Webhook Design Review (1h)

**¿Qué es el problema?**
- OfflineMonitor polls Hermes cada 60s → latencia, CPU waste
- Solución: Hermes pushes event a Atlas via webhook

**Qué leer:**
- `docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md` sección 2 (Hermes Webhook)
- Entiende: Architecture (webhook → handler → event bus → subscriptores)

**Checklist:**
- [ ] Entiendo por qué webhook es mejor que polling
- [ ] Entiendo HMAC-SHA256 signature validation
- [ ] Sé qué cambios hacer en orchestrator.py
- [ ] Sé qué cambios hacer en Hermes-VPS (Docker)

**Tiempo:** 1h

### 📋 Crear GitHub Issues (1h)

```bash
cd ~/proyectos/atlas-core

# Issue 1: Prometheus deployment (docs only)
gh issue create \
  --title "✅ Prometheus Setup — ADR-024 Operacional" \
  --body "See docs/prometheus_setup.md. DONE by 25 May." \
  --label "done,documentation"

# Issue 2: Hermes webhook (implementation)
gh issue create \
  --title "Hermes Webhook: Replace polling with event-driven" \
  --body "
## What
Replace OfflineMonitor polling (60s interval) with event-driven webhook from Hermes-VPS.

## Design
See docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md section 2

## Changes
- Create src/atlas/interfaces/hermes_webhook.py
- Update orchestrator.py (remove OfflineMonitor.start)
- Update Hermes-VPS Docker image
- Add tests

## Effort
12 hours

## Success
- Webhook POST received <1s
- HMAC verified
- Event bus publishes correctly
- Offline detection latency <1s (vs 60s)
" \
  --label "enhancement,priority:high,status:ready" \
  --assignee @yourself

# Issue 3: ColdUpdate auto-patch (planning)
gh issue create \
  --title "ColdUpdate Auto-patch: Auto-generate patches from SelfAuditLoop" \
  --body "
## What
Wire SelfAuditLoop → PatchGenerator → ColdUpdateProposal to auto-generate patches.

## Design
See docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md section 3

## Phases
1. PatchGenerator (8h): docstring, test stub, lint fixes
2. Wire into SelfAuditLoop (8h): generate on audit
3. Integration (8h): CLI, Telegram, tests

## Success
- Auto-patches for low-risk categories
- Full workflow: audit → patch → propose → approve → apply
- Tests: 100% integration test coverage
" \
  --label "enhancement,priority:high,status:design" \
  --assignee @yourself
```

**DONE:** Issues created + team notified ✅

---

## VIERNES (27 mayo) — 1 HORA

### ✅ Prometheus Verification

```bash
# 1. Check Prometheus scraping Atlas
curl http://localhost:9090/api/v1/targets
# Look for: "atlas" job with status "UP"

# 2. Check metrics
curl http://localhost:7331/metrics | wc -l
# Should be >50 metrics

# 3. Check Prometheus dashboard
# http://localhost:9090
# Should show: Time series, Graph query, Targets page
```

### 📋 Hermes Webhook Quick Demo (Design)

**Si tienes acceso a Hermes-VPS:**

```bash
# Current behavior (polling)
ps aux | grep OfflineMonitor
# Should see: polling thread active

# Future (webhook)
# Hermes sends: POST http://atlas:7331/api/hermes/webhook
# Payload: {"event_type": "offline", "signature": "hmac..."}
# Atlas receives → publishes event → notifies
```

### 📝 Update README.md

```markdown
## Status (25 May 2026)

### Item 1: Prometheus Setup ✅
- **Status:** Deployable
- **Docs:** `docs/prometheus_setup.md`
- **Next:** Monitor metrics in production

### Item 2: Hermes Webhook 📋
- **Status:** Design complete, ready for implementation
- **Docs:** `docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md`
- **Timeline:** Week 1 (26-31 May)
- **Impact:** -60s latency, -CPU polling overhead

### Item 3: ColdUpdate Auto-patch 📋
- **Status:** Design complete, ready for implementation
- **Docs:** `docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md`
- **Timeline:** Week 2-3 (1-14 June)
- **Impact:** Close self-audit loop, auto-repair

See `docs/ROADMAP_30DAYS_ITEMS_1_2_3.md` for detailed timeline.
```

---

## ✨ SUMMARY (3 DAYS)

| Day | Task | Time | Status | Impact |
|-----|------|------|--------|--------|
| **25 May** | Prometheus deploy + setup | 2h | ✅ LIVE | ADR-024 operacional |
| **26 May** | Hermes webhook design review | 1.5h | ✅ READY | Entiendes architecture |
| **27 May** | GitHub issues + verification | 1.5h | ✅ TRACKED | Team informed |
| **TOTAL** | | **5h** | ✅ DONE | 3 items en pipeline |

---

## 🎯 NEXT (Monday 26 May — Week 1)

**START:** Hermes webhook implementation (12 hours)

```bash
# Create branch
git checkout -b feature/hermes-webhook

# Create file
touch src/atlas/interfaces/hermes_webhook.py

# Implement HermesWebhookHandler class
# (See docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md section 2.3A)

# Write tests
touch tests/test_hermes_webhook.py

# Submit PR
git push origin feature/hermes-webhook
gh pr create --fill
```

---

## 💾 Files to Save/Review

```
docs/prometheus_setup.md                          # ← Read now
docs/IMPLEMENTATION_PLAN_ITEMS_2_3.md             # ← Read tomorrow
docs/ROADMAP_30DAYS_ITEMS_1_2_3.md                # ← Reference for timeline
docs/AUDIT_COMPLETO_2026-05-25.md                 # ← Full context
```

---

## ❓ FAQ

**Q: ¿Está lista Prometheus ahora?**  
A: ✅ Sí. Docs + deployment guide listo. Deplega hoy.

**Q: ¿Cuándo empiezo Hermes webhook?**  
A: 📋 Monday 26 May (mañana). Diseño listo en docs.

**Q: ¿Es obligatorio hacer los 3 items?**  
A: 🎯 Item 1 (Prometheus) es quick win. Items 2-3 cierran self-audit loop — high value pero pueden ser secuenciales.

**Q: ¿Qué si encuentro bugs en Prometheus?**  
A: 🔧 Ver troubleshooting en `docs/prometheus_setup.md` sección 10.

---

**Created:** 25 May 2026  
**Type:** Actionable guide (not design doc)  
**Next review:** Friday 31 May (end of Week 1)

👉 **START NOW:** `docs/prometheus_setup.md` section 1 (Quick Start)
