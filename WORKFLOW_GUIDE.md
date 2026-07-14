# Atlas Core Knowledge Workflow Guide

**Status**: ✅ All components installed, configured, and validated.

---

## 📋 Quick Start (Copia y pega estos comandos)

### 1. Verificar que todo está funcionando
```bash
cd ~/proyectos/atlas-core
source .venv/bin/activate
graphify --version  # Debe mostrar: graphify 0.9.11
docker ps | grep neo4j  # Debe mostrar: neo4j running
curl http://127.0.0.1:11434/v1/models  # Debe devolver modelos disponibles
```

### 2. Actualizar el grafo (code-only, ~30s)
```bash
./scripts/update-knowledge-graph.sh
```
Esto:
- Regenera el grafo desde el código fuente
- Exporta a Obsidian vault
- Genera Cypher para Neo4j

### 3. Abrir Obsidian
```bash
# En macOS/Linux
obsidian ~/proyectos/atlas-core/graphify-vault

# O abre Obsidian manualmente y selecciona:
# Vault settings → Open folder as vault → ~/proyectos/atlas-core/graphify-vault
```

### 4. Acceder a Neo4j Browser
```bash
# Abre en navegador:
http://localhost:7474

# Login:
# User: neo4j
# Password: atlasneo4j
```

### 5. Preparar para NotebookLM
```bash
./scripts/prepare-notebooklm.sh --include-vault
# Crea: notebooklm-package/ listo para subir a NotebookLM
```

---

## 🚀 Flujo Completo (Sin Sempiternal)

### **Workflow A: Code-Only (Rápido, bajo tokens)**

```bash
# 1. Hacer cambios en src/, tests/, docs/
git add .
git commit -m "Add new feature X"
# ↓ Git hook automáticamente ejecuta update-knowledge-graph.sh ↓

# 2. El grafo se actualiza automáticamente (code-only)
# El GRAPH_REPORT.md es la guía de entrada para agentes

# 3. Abrir Obsidian para navegar el grafo
# O revisar graphify-out/GRAPH_REPORT.md
```

**Tokens consumidos**: 0 (graph puro, sin LLM)

---

### **Workflow B: GraphRAG Full (Razonamiento complejo)**

```bash
# 1. Ejecutar con Ollama local (bajo costo)
./scripts/update-knowledge-graph-rag.sh \
  --backend ollama \
  --model qwen2.5-coder:7b \
  --api-timeout 600 \
  --max-workers 2

# 2. (Opcional) Importar a Neo4j para consultas avanzadas
./scripts/neo4j-import.sh

# 3. Ejecutar queries GraphRAG en Neo4j
./scripts/neo4j-rag-query.sh
```

**Tokens consumidos**: Depende del modelo (Ollama local = ~0 tokens de API)

---

### **Workflow C: Cloud Backend (Mejor calidad, más tokens)**

```bash
# Configurar backend en .env:
# - OPENAI_API_KEY=sk-...
# - ANTHROPIC_API_KEY=sk-ant-...
# - GEMINI_API_KEY=goog-...

./scripts/update-knowledge-graph-rag.sh \
  --backend openai \
  --model gpt-4-mini \
  --api-timeout 900 \
  --token-budget 50000
```

**Tokens consumidos**: Depende del backend (ver estimaciones en AGENTS.md)

---

## 📊 Componentes

### 1. **Graphify** (Base)
```
graphify-out/
├── GRAPH_REPORT.md        ← Leer ESTO primero (entrada para agentes)
├── graph.json             ← Estructura del grafo
├── cypher.txt             ← Consultas para Neo4j
└── manifest.json          ← Metadata
```

**Cómo leer GRAPH_REPORT.md:**
- Líneas 1-20: Resumen de corpus y estadísticas
- Líneas 20-100: Comunidades (hubs principales del proyecto)
- Después: Detalles de relaciones

### 2. **Obsidian Vault**
```
graphify-vault/
├── $defs.md, $id_*.md   ← Nodos del grafo (auto-generados)
└── ...
```

**Para navegar:**
1. Abre `Obsidian → File → Open folder as vault → graphify-vault`
2. Instala plugins (recomendado):
   - **Graph View**: Panel → Graph View (esquina derecha)
   - **Dataview**: Queries sobre el grafo
   - **Breadcrumbs**: Navegación jerárquica

### 3. **Neo4j**
```
http://localhost:7474
- Browser: Consultas interactivas
- Cypher: Lenguaje de grafos
- Queries: Ver en scripts/neo4j-rag-query.sh
```

**Ejemplo de consulta:**
```cypher
MATCH (n:Module)-[r:IMPORTS]->(m:Module)
WHERE n.name CONTAINS "auth"
RETURN n, r, m
LIMIT 50
```

### 4. **NotebookLM Package**
```
notebooklm-package/
├── 00-Graphify-Report.md      ← Resumen del grafo
├── 02-Package-Metadata.md     ← Info del proyecto
├── docs/                      ← Documentación
└── vault/                     ← Obsidian vault (opcional)
```

**Usar:**
1. `./scripts/prepare-notebooklm.sh --include-vault`
2. Comprimir: `zip -r notebooklm-package.zip notebooklm-package/`
3. Subir a NotebookLM → "Upload files"

### 5. **Git Hook (Automático)**
```
.git/hooks/post-commit
- Ejecuta: ./scripts/update-knowledge-graph.sh
- Trigger: Cambios en src/, docs/, AGENTS.md, etc.
- Tiempo: ~30s (no bloquea commits)
```

---

## 🛠️ Troubleshooting

### "Graph no se actualiza"
```bash
# Verificar que el hook está instalado:
ls -la .git/hooks/post-commit

# Si no está, reinstalarlo:
./scripts/install-knowledge-hooks.sh

# Forzar update manual:
./scripts/update-knowledge-graph.sh
```

### "Neo4j está lento"
```bash
# Reiniciar Neo4j:
docker restart atlas-neo4j

# Ver logs:
docker logs atlas-neo4j | tail -50
```

### "Ollama timeout"
```bash
# Verificar que está corriendo:
curl http://127.0.0.1:11434/v1/models

# Si no, iniciar:
ollama serve

# Reducir timeout:
./scripts/update-knowledge-graph-rag.sh \
  --backend ollama \
  --api-timeout 300 \
  --max-workers 1
```

### "Obsidian no ve el vault"
```bash
# Verificar ruta:
ls -la graphify-vault/ | head

# Crear .obsidian config:
mkdir -p graphify-vault/.obsidian
echo '{"version": 2}' > graphify-vault/.obsidian/app.json
```

---

## 📈 Performance Tuning

### Para proyectos MUY grandes (>1000 archivos)
```bash
# Usar code-only (rápido):
./scripts/update-knowledge-graph.sh

# Si quieres GraphRAG, ajustar:
./scripts/update-knowledge-graph-rag.sh \
  --backend ollama \
  --token-budget 10000 \    # Limitar a 10k tokens
  --max-workers 1 \         # Un worker a la vez
  --max-concurrency 2       # 2 archivos en paralelo
```

### Para rasgar baja latencia (notebooks)
```bash
# Usar modelo más pequeño:
ollama pull qwen2.5:0.5b  # Ultra-ligero (~400MB)

./scripts/update-knowledge-graph-rag.sh \
  --backend ollama \
  --model qwen2.5:0.5b \
  --api-timeout 120
```

---

## 📚 Integration with Agents (Claude, Cursor, etc.)

### Antes de que el agente lea tu código:
1. **Lee GRAPH_REPORT.md**
   ```bash
   cat graphify-out/GRAPH_REPORT.md | head -100
   ```

2. **Consulta AGENTS.md** para el workflow recomendado
   ```bash
   cat AGENTS.md | grep -A 50 "Knowledge Workflow"
   ```

3. **Si necesitas razonamiento complejo**, importa Neo4j:
   ```bash
   ./scripts/neo4j-rag-query.sh
   ```

### Ejemplo: Claude Code
```
1. Abre Atlas Core en Claude Code
2. System Prompt automáticamente lee AGENTS.md
3. Ejecuta: /terminal: ./scripts/update-knowledge-graph.sh
4. Consulta el grafo: /files: graphify-out/GRAPH_REPORT.md
5. Navega en Obsidian para contexto visual
```

---

## 🎯 Recommended Next Steps

1. **Today**: Abre Obsidian y navega el grafo (5 min)
2. **Today**: Ejecuta una query en Neo4j (5 min)
3. **This week**: Configura NotebookLM con el paquete (10 min)
4. **This week**: Prueba un commit para validar Git hook (1 min)
5. **Optional**: Experimenta con diferentes backends (Ollama → Claude → Gemini)

---

## 📖 Full Documentation

- **AGENTS.md**: Workflow completo para agentes
- **agents.md**: Alias (apunta a AGENTS.md)
- **scripts/README.md**: Detalles técnicos de cada script
- **GRAPH_REPORT.md**: Resumen auto-generado del grafo

---

## 🚨 Critical Files (No tocar / Backup)

```
graphify-out/
- GRAPH_REPORT.md      ← Entry point para agentes
- graph.json           ← Estructura de datos
- cypher.txt           ← Neo4j import

graphify-vault/        ← 15.9k archivos Obsidian
notebooklm-package/    ← 151M paquete listo
.git/hooks/post-commit ← Automatización
```

---

## 💡 Pro Tips

- **Buscar en el grafo**: `grep -r "PATTERN" graphify-out/graph.json | jq .`
- **Contar nodos**: `jq '[.[] | select(.type == "node")] | length' graphify-out/graph.json`
- **Exportar para análisis**: `jq '.[] | select(.type == "edge")' graphify-out/graph.json > edges.jsonl`
- **Sincronizar Obsidian**: Editar archivos en vault → Graphify regenera en el next update
- **Backup del grafo**: `cp -r graphify-out graphify-out.backup.$(date +%Y%m%d)`

---

**Last Updated**: 2026-07-14 | **Stack Version**: Graphify 0.9.11 + Neo4j 5.x + Ollama 6 models
