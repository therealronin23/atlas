#!/bin/bash
# Script para verificar que Prometheus está scrapeando Atlas correctamente

echo "═══════════════════════════════════════════════════════════"
echo "🔍 Verificando Prometheus + Atlas Metrics"
echo "═══════════════════════════════════════════════════════════"

echo ""
echo "1️⃣  Verificando servicios activos..."
echo ""

# Verificar Prometheus
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "   ✅ Prometheus activo en http://localhost:9090"
else
    echo "   ❌ Prometheus NO está activo"
fi

# Verificar AlertManager
if curl -s http://localhost:9093/-/healthy > /dev/null 2>&1; then
    echo "   ✅ AlertManager activo en http://localhost:9093"
else
    echo "   ⚠️  AlertManager NO está activo (opcional)"
fi

# Verificar Atlas Dashboard
if curl -s http://localhost:7331/ > /dev/null 2>&1; then
    echo "   ✅ Atlas Dashboard activo en http://localhost:7331"
else
    echo "   ❌ Atlas Dashboard NO está activo"
fi

# Verificar Atlas Prometheus Exporter
if curl -s http://localhost:9091/metrics > /dev/null 2>&1; then
    echo "   ✅ Atlas Prometheus Exporter activo en http://localhost:9091/metrics"
else
    echo "   ❌ Atlas Prometheus Exporter NO está activo"
fi

echo ""
echo "2️⃣  Verificando que Prometheus está scrapeando..."
echo ""

# Verificar targets en Prometheus
TARGETS=$(curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets')
if [ "$TARGETS" != "null" ] && [ ! -z "$TARGETS" ]; then
    echo "   ✅ Prometheus targets activos:"
    curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, instance: .labels.instance, state: .health}'
else
    echo "   ⚠️  No hay targets activos en Prometheus"
fi

echo ""
echo "3️⃣  Verificando métricas de Atlas..."
echo ""

# Obtener primeras 20 líneas de métricas
METRICS=$(curl -s http://localhost:9091/metrics | head -20)
if [ ! -z "$METRICS" ]; then
    echo "   ✅ Atlas está exportando métricas:"
    curl -s http://localhost:9091/metrics | head -30
else
    echo "   ❌ No hay métricas disponibles"
fi

echo ""
echo "4️⃣  Verificando alertas en AlertManager..."
echo ""

# Obtener alertas activas
ALERTS=$(curl -s http://localhost:9093/api/v1/alerts | jq '.data | length')
echo "   ℹ️  Alertas activas: $ALERTS"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "🎯 Verificación completada"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📊 URLs para monitoreo:"
echo "   • Prometheus:       http://localhost:9090"
echo "   • AlertManager:     http://localhost:9093"
echo "   • Atlas Dashboard:  http://localhost:7331"
echo "   • Métricas raw:     http://localhost:9091/metrics"
echo ""
