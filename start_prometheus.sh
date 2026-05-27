#!/bin/bash
# Script para iniciar Prometheus + AlertManager + Atlas Prometheus Exporter
# Ejecución: source start_prometheus.sh

set -e

export ATLAS_HOME="${ATLAS_HOME:=$HOME/atlas}"
cd /home/ronin/proyectos/atlas-core

# Cargar .env
set -a
source .env
set +a

echo "═══════════════════════════════════════════════════════════"
echo "🚀 Iniciando Prometheus + AlertManager + Atlas"
echo "═══════════════════════════════════════════════════════════"

# Verificar que Prometheus está instalado
if ! command -v prometheus &> /dev/null; then
    echo "❌ Prometheus no instalado. Ejecutar: sudo apt-get install -y prometheus prometheus-alertmanager"
    exit 1
fi

# Verificar archivos de configuración
if [ ! -f "/tmp/atlas-prometheus/prometheus.yml" ]; then
    echo "❌ prometheus.yml no encontrado"
    exit 1
fi

if [ ! -f "/tmp/atlas-prometheus/alertmanager.yml" ]; then
    echo "❌ alertmanager.yml no encontrado"
    exit 1
fi

echo "✅ Prometheus instalado"
echo "✅ Archivos de configuración listos"

# Iniciar AlertManager en background
echo ""
echo "📊 Iniciando AlertManager en puerto 9093..."
alertmanager --config.file=/tmp/atlas-prometheus/alertmanager.yml \
    --storage.path=/tmp/atlas-alertmanager-data \
    --web.listen-address=127.0.0.1:9093 &
ALERTMANAGER_PID=$!
echo "   AlertManager PID: $ALERTMANAGER_PID"

# Iniciar Prometheus en background
echo ""
echo "📊 Iniciando Prometheus en puerto 9090..."
prometheus --config.file=/tmp/atlas-prometheus/prometheus.yml \
    --storage.tsdb.path=/tmp/atlas-prometheus-data \
    --web.listen-address=127.0.0.1:9090 &
PROMETHEUS_PID=$!
echo "   Prometheus PID: $PROMETHEUS_PID"

# Esperar a que se estabilicen
sleep 3

# Verificar que Prometheus está arriba
echo ""
echo "✅ Verificando servicios..."
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "   ✅ Prometheus healthy en http://localhost:9090"
else
    echo "   ⚠️  Prometheus aún está iniciando..."
fi

if curl -s http://localhost:9093/-/healthy > /dev/null 2>&1; then
    echo "   ✅ AlertManager healthy en http://localhost:9093"
else
    echo "   ⚠️  AlertManager aún está iniciando..."
fi

# Cargar venv de Atlas
echo ""
echo "🐍 Activando venv de Atlas..."
source .venv/bin/activate

# Iniciar Atlas con Prometheus habilitado
echo ""
echo "🚀 Iniciando Atlas Core con ATLAS_PROMETHEUS=1..."
echo "   Dashboard: http://localhost:7331"
echo "   Prometheus exporter: http://localhost:9091/metrics"
echo "   Prometheus web UI: http://localhost:9090"
echo "   AlertManager web UI: http://localhost:9093"
echo ""

PYTHONPATH=src atlas serve --host 127.0.0.1 --port 7331

# Cleanup al salir
trap "kill $ALERTMANAGER_PID $PROMETHEUS_PID 2>/dev/null || true" EXIT
