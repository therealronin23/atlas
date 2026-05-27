# Prometheus Setup para Atlas Core (ADR-024 Operacional)

**Fecha:** 25 de mayo de 2026  
**Status:** ADR-024 MVP → Producción  
**Scope:** Configurar Prometheus + Grafana para monitoring 24/7  

---

## 1. Quick Start (5 min)

### 1.1 Iniciar Atlas con Prometheus

```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate
set -a && source .env && set +a

# Inicia atlas serve con Prometheus enabled
ATLAS_PROMETHEUS=1 atlas serve
# → Escucha en localhost:7331
# → /api/health (JSON)
# → /metrics (Prometheus text format)
```

### 1.2 Verificar métricas

```bash
curl http://localhost:7331/metrics
```

Deberías ver output tipo:

```
# HELP atlas_task_count Total tasks processed
# TYPE atlas_task_count counter
atlas_task_count{status="completed"} 42
atlas_task_count{status="failed"} 3
atlas_task_count{status="approved"} 15

# HELP atlas_memory_usage_bytes Memory used by Atlas process
# TYPE atlas_memory_usage_bytes gauge
atlas_memory_usage_bytes 524288000

# HELP atlas_inference_latency_seconds LLM inference latency
# TYPE atlas_inference_latency_seconds histogram
atlas_inference_latency_seconds_bucket{provider="groq",le="1"} 5
atlas_inference_latency_seconds_bucket{provider="groq",le="5"} 18
...
```

---

## 2. Prometheus Server Setup

### 2.1 Instalación

**Option A: Package manager**
```bash
# macOS
brew install prometheus

# Ubuntu/Debian
sudo apt-get install prometheus

# Verify
prometheus --version
```

**Option B: Docker** (recomendado para prod)
```bash
docker run --detach \
  --name prometheus \
  --publish 9090:9090 \
  -v /tmp/prometheus.yml:/etc/prometheus/prometheus.yml \
  -v prometheus_data:/prometheus \
  prom/prometheus:latest \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus
```

### 2.2 Configurar Prometheus (prometheus.yml)

```yaml
# /etc/prometheus/prometheus.yml (or /tmp/prometheus.yml for Docker)

global:
  scrape_interval: 15s       # Scrape metrics every 15 seconds
  evaluation_interval: 15s   # Evaluate rules every 15 seconds
  external_labels:
    monitor: 'atlas-core'
    environment: 'production'

# Remote storage (optional, for long-term retention)
# remote_write:
#   - url: "http://mimir:9009/api/prom/push"
#     queue_config:
#       max_samples_per_send: 1000

scrape_configs:
  # Atlas Core local
  - job_name: 'atlas'
    static_configs:
      - targets: ['localhost:7331']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s
    # Optional: Add metrics relabeling
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'atlas_.*'
        action: keep

  # Optional: Hermes-VPS remote (if using Tailscale tunnel)
  # - job_name: 'hermes'
  #   static_configs:
  #     - targets: ['100.108.132.116:8443']  # Tailscale IP
  #   scheme: https
  #   tls_config:
  #     insecure_skip_verify: true  # Only in dev!
  #   scrape_interval: 30s

# Alerting rules
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']  # AlertManager endpoint

# Alert rules (see section 3)
rule_files:
  - 'atlas_alerts.yml'
```

### 2.3 Iniciar Prometheus

**Standalone:**
```bash
prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/var/lib/prometheus
# → http://localhost:9090
```

**Docker:**
```bash
docker restart prometheus
# → http://localhost:9090
```

Verifica que Prometheus esté scrapeando Atlas:
- Navega a http://localhost:9090/targets
- Deberías ver `atlas` job con estado "UP"

---

## 3. Alerting Rules (atlas_alerts.yml)

```yaml
# /etc/prometheus/atlas_alerts.yml

groups:
  - name: atlas_core
    interval: 30s
    rules:
      # High memory usage
      - alert: AtlasMemoryUsageHigh
        expr: |
          atlas_memory_usage_bytes > 1000000000  # 1GB
        for: 5m
        labels:
          severity: warning
          component: atlas
        annotations:
          summary: "Atlas memory usage >1GB"
          description: "Atlas is using {{ humanize .Value }} bytes"
          runbook: "https://github.com/therealronin23/atlas/wiki/Runbook-Memory"

      # Very high memory (near OMEGA threshold)
      - alert: AtlasMemoryUsageCritical
        expr: |
          atlas_memory_usage_bytes > 1500000000  # 1.5GB
        for: 2m
        labels:
          severity: critical
          component: atlas
        annotations:
          summary: "Atlas memory usage >1.5GB (OMEGA threshold imminent)"
          description: "Memory: {{ humanize .Value }} bytes. May trigger OMEGA mode."

      # High CPU temperature
      - alert: AtlasTemperatureWarning
        expr: |
          atlas_environment_cpu_temp_celsius > 70  # DEGRADED threshold
        for: 2m
        labels:
          severity: warning
          component: thermal
        annotations:
          summary: "Atlas CPU >70°C (DEGRADED mode)"
          description: "Temperature: {{ .Value }}°C"

      # Critical temperature
      - alert: AtlasTemperatureCritical
        expr: |
          atlas_environment_cpu_temp_celsius > 80  # OMEGA threshold
        for: 1m
        labels:
          severity: critical
          component: thermal
        annotations:
          summary: "Atlas CPU >80°C (OMEGA mode activated)"
          description: "Temperature: {{ .Value }}°C. Local inference suspended."

      # Task failure rate
      - alert: AtlasTaskFailureRateHigh
        expr: |
          rate(atlas_task_count{status="failed"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          component: orchestrator
        annotations:
          summary: "Atlas task failure rate >10%"
          description: "Failure rate: {{ .Value | humanizePercentage }}"

      # Merkle chain verification failure
      - alert: AtlasMerkleVerifyFailure
        expr: |
          atlas_merkle_verify_failures_total > 0
        for: 1m
        labels:
          severity: critical
          component: security
        annotations:
          summary: "Merkle chain verification failed"
          description: "Total failures: {{ .Value }}. Investigate immediately."
          runbook: "https://github.com/therealronin23/atlas/wiki/Runbook-Merkle"

      # Inference provider down
      - alert: AtlasInferenceProviderDown
        expr: |
          atlas_inference_provider_available{provider="groq"} == 0
        for: 5m
        labels:
          severity: warning
          component: inference
        annotations:
          summary: "Inference provider {{ $labels.provider }} is down"
          description: "Provider {{ $labels.provider }} has not responded in 5+ minutes."

      # Offline queue backup (Hermes unreachable)
      - alert: AtlasHermesUnreachable
        expr: |
          atlas_offline_queue_size > 10
        for: 10m
        labels:
          severity: warning
          component: hermes
        annotations:
          summary: "Hermes unreachable ({{ .Value }} tasks queued)"
          description: "Hermes has been unreachable for 10+ minutes. {{ .Value }} tasks in offline queue."
          runbook: "https://github.com/therealronin23/atlas/wiki/Runbook-Hermes"

      # Vector store overload
      - alert: AtlasVectorStoreSlowQueries
        expr: |
          histogram_quantile(0.95, rate(atlas_vector_store_query_latency_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
          component: memory
        annotations:
          summary: "Vector store 95th percentile latency >500ms"
          description: "Vector queries are slow. Check KuzuDB or reduce pattern count."

      # PII redaction failures
      - alert: AtlasPIIRedactionFailures
        expr: |
          increase(atlas_pii_redaction_failures_total[5m]) > 0
        for: 1m
        labels:
          severity: warning
          component: security
        annotations:
          summary: "PII redaction failure detected"
          description: "{{ .Value }} PII redaction failures in last 5 minutes."

      # Ghost Replay cache thrashing
      - alert: AtlasGhostReplayCacheThrashing
        expr: |
          (rate(atlas_ghost_replay_evictions_total[5m]) / rate(atlas_ghost_replay_hits_total[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
          component: memory
        annotations:
          summary: "Ghost Replay cache thrashing (eviction:hit ratio >50%)"
          description: "Cache is evicting entries too frequently. Consider increasing max_entries."

      # Service unavailable
      - alert: AtlasServiceDown
        expr: |
          up{job="atlas"} == 0
        for: 2m
        labels:
          severity: critical
          component: service
        annotations:
          summary: "Atlas service is DOWN"
          description: "Atlas Core has not responded to scrape requests for 2+ minutes."
```

---

## 4. Grafana Dashboard Setup

### 4.1 Instalar Grafana

```bash
# macOS
brew install grafana

# Ubuntu
sudo apt-get install grafana-server

# Docker
docker run --detach \
  --name grafana \
  --publish 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  grafana/grafana:latest
```

### 4.2 Crear Dashboard

1. Navega a http://localhost:3000 (default: admin/admin)
2. Click "Add data source"
3. Selecciona "Prometheus"
4. URL: `http://localhost:9090`
5. Click "Save & test"
6. Import dashboard JSON (next section) o crear manual

### 4.3 Dashboard JSON Template

```json
{
  "dashboard": {
    "title": "Atlas Core Monitoring",
    "tags": ["atlas", "production"],
    "timezone": "UTC",
    "panels": [
      {
        "title": "Memory Usage",
        "targets": [
          {
            "expr": "atlas_memory_usage_bytes / 1000000000",
            "legendFormat": "Memory (GB)"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Task Success Rate",
        "targets": [
          {
            "expr": "rate(atlas_task_count{status=\"completed\"}[5m]) / (rate(atlas_task_count[5m]))",
            "legendFormat": "Success %"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Temperature (°C)",
        "targets": [
          {
            "expr": "atlas_environment_cpu_temp_celsius",
            "legendFormat": "CPU Temp"
          }
        ],
        "thresholds": [
          { "value": 70, "color": "yellow" },
          { "value": 80, "color": "red" }
        ],
        "type": "gauge"
      },
      {
        "title": "Inference Latency (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(atlas_inference_latency_seconds_bucket[5m]))",
            "legendFormat": "{{ provider }}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Merkle Chain Health",
        "targets": [
          {
            "expr": "atlas_merkle_chain_depth",
            "legendFormat": "Chain depth"
          }
        ],
        "type": "counter"
      },
      {
        "title": "Hermes Connectivity",
        "targets": [
          {
            "expr": "atlas_hermes_available",
            "legendFormat": "Hermes available"
          }
        ],
        "type": "stat",
        "thresholds": [
          { "value": 0, "color": "red" },
          { "value": 1, "color": "green" }
        ]
      }
    ]
  }
}
```

---

## 5. Metrics Reference (ADR-024 Complete List)

### Task Execution
```
atlas_task_count{status}                    # Counter: tasks by status
atlas_task_duration_seconds{status}         # Histogram: task execution time
atlas_approval_wait_time_seconds            # Histogram: approval queue wait time
```

### Memory & Performance
```
atlas_memory_usage_bytes                    # Gauge: current memory usage
atlas_memory_peak_bytes                     # Gauge: peak memory since startup
atlas_vector_store_entries                  # Gauge: active patterns in KuzuDB
atlas_vector_store_query_latency_seconds    # Histogram: similarity search latency
```

### Thermal & Operational Modes
```
atlas_environment_cpu_temp_celsius          # Gauge: CPU temperature
atlas_environment_memory_available_bytes    # Gauge: free RAM
atlas_operational_mode                      # Gauge: current mode (0=NORMAL, 1=DEGRADED, 2=OMEGA)
atlas_mode_transitions_total{from,to}       # Counter: mode transitions
```

### Security & Audit
```
atlas_capability_tokens_issued_total        # Counter: capability tokens issued
atlas_capability_denials_total              # Counter: denied capabilities
atlas_merkle_verify_failures_total          # Counter: Merkle chain verify failures
atlas_pii_redaction_attempts_total          # Counter: PII redaction attempts
atlas_pii_redaction_failures_total          # Counter: PII redaction failures
atlas_sandbox_exec_failures_total           # Counter: sandbox execution failures
atlas_pending_approvals_count                # Gauge: pending approval tasks
```

### Inference & Routing
```
atlas_inference_latency_seconds{provider}   # Histogram: LLM latency by provider
atlas_inference_errors_total{provider,error} # Counter: LLM errors by provider
atlas_inference_provider_available{provider} # Gauge: provider health (0/1)
atlas_classifier_decisions_total{decision}  # Counter: routing decisions
atlas_slm_classifier_invocations_total      # Counter: SLM classifier calls
```

### Memory & Caching
```
atlas_ghost_replay_hits_total                # Counter: cache hits
atlas_ghost_replay_misses_total              # Counter: cache misses
atlas_ghost_replay_evictions_total           # Counter: LRU evictions
atlas_memory_distiller_chunks_compressed     # Counter: chunks compressed
```

### Integration & Delegation
```
atlas_hermes_available                       # Gauge: Hermes reachable (0/1)
atlas_offline_queue_size                     # Gauge: pending delegations
atlas_offline_queue_max_size                 # Gauge: configured queue limit
atlas_delegation_failures_total              # Counter: failed delegations
```

---

## 6. Production Deployment Checklist

- [ ] Prometheus installed and configured (prometheus.yml)
- [ ] Alert rules loaded (atlas_alerts.yml)
- [ ] AlertManager configured (see section 7)
- [ ] Grafana dashboards imported
- [ ] Remote storage configured (optional, for >30 days retention)
- [ ] Backup policy defined (Prometheus data rotation)
- [ ] Alerting escalation chain defined (who gets paged?)
- [ ] Runbooks linked in alert annotations
- [ ] Health check dashboard accessible
- [ ] Log shipping configured (if using ELK/Loki)
- [ ] RBAC / authentication enabled (optional)
- [ ] SSL/TLS for Grafana (if prod)

---

## 7. AlertManager Setup (Optional)

### 7.1 Install & Configure

```bash
# macOS
brew install alertmanager

# Ubuntu
sudo apt-get install alertmanager
```

Create `/etc/alertmanager/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m
  slack_api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'

route:
  receiver: 'default'
  group_by: ['component', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  routes:
    - match:
        severity: critical
      receiver: 'critical'
      group_wait: 0s
    - match:
        severity: warning
      receiver: 'default'

receivers:
  - name: 'default'
    slack_configs:
      - channel: '#atlas-alerts'
        title: 'Alert: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'critical'
    slack_configs:
      - channel: '#atlas-critical'
        title: '🔴 CRITICAL: {{ .GroupLabels.alertname }}'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
```

### 7.2 Start AlertManager

```bash
alertmanager --config.file=/etc/alertmanager/alertmanager.yml
```

---

## 8. Long-Term Retention (Production)

### 8.1 Local Retention

By default, Prometheus keeps 15 days. Adjust:

```bash
prometheus --storage.tsdb.retention.time=90d
```

### 8.2 Remote Storage (Mimir/Cortex)

For >90 days, use remote storage:

```yaml
remote_write:
  - url: "http://mimir:9009/api/prom/push"
    queue_config:
      capacity: 10000
      max_shards: 200
      min_shards: 1
      max_samples_per_send: 500
      batch_send_wait: 5s
      min_backoff: 30ms
      max_backoff: 100ms
```

---

## 9. Monitoring the Monitor

Add self-monitoring:

```yaml
# prometheus.yml scrape_configs

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
    scrape_interval: 15s
```

Key metrics to watch:
- `prometheus_tsdb_symbol_table_size_bytes` — DB size
- `prometheus_tsdb_compaction_duration_seconds` — Performance
- `prometheus_rule_evaluation_failures_total` — Rule health

---

## 10. Troubleshooting

### Prometheus not scraping Atlas

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Atlas metrics endpoint
curl http://localhost:7331/metrics

# Restart Atlas with ATLAS_PROMETHEUS=1
ATLAS_PROMETHEUS=1 atlas serve
```

### High memory usage

```bash
# Reduce retention
prometheus --storage.tsdb.retention.time=7d

# Reduce scrape frequency
# Edit prometheus.yml, set scrape_interval: 30s
```

### Alerts not firing

```bash
# Check AlertManager logs
journalctl -u alertmanager -f

# Verify prometheus.yml syntax
promtool check config /etc/prometheus/prometheus.yml

# Verify alert rules
promtool check rules /etc/prometheus/atlas_alerts.yml
```

---

## 11. References

- Prometheus docs: https://prometheus.io/docs/
- Alerting best practices: https://prometheus.io/docs/practices/alerting/
- Atlas ADR-024: `/docs/adr_024_observability_logging_v2.md`
- GitHub runbooks: https://github.com/therealronin23/atlas/wiki/Runbooks/

---

**Status:** ADR-024 MVP now operacionalizado. Producción listo.  
**Next:** Hermes webhook (eliminar polling), auto-patch ColdUpdate.
