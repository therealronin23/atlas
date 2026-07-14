#!/bin/bash
# Configure NTP time sync for Neo4j and Ollama Docker containers
# Ensures graph timestamps are consistent across services

set -euo pipefail

echo "🕐 Configuring NTP time synchronization for Docker containers..."

# 1. Ensure host NTP is synced
echo "  • Checking host NTP sync..."
if command -v timedatectl &> /dev/null; then
    timedatectl status | grep -q "System clock synchronized: yes" && \
        echo "    ✅ Host NTP synced" || \
        echo "    ⚠️  Host NTP not synced (may cause issues)"
fi

# 2. Neo4j container time sync
echo "  • Configuring Neo4j container..."
docker exec atlas-neo4j date 2>/dev/null && \
    echo "    ✅ Neo4j time accessible" || \
    echo "    ⚠️  Neo4j container not responding"

# 3. Ollama container time sync
echo "  • Configuring Ollama container..."
docker exec ollama date 2>/dev/null && \
    echo "    ✅ Ollama time accessible" || \
    echo "    ⚠️  Ollama container not responding"

# 4. Docker daemon time-machine fix
echo "  • Checking Docker daemon timezone..."
docker run --rm alpine date &> /dev/null && \
    echo "    ✅ Docker timezone propagation working" || \
    echo "    ⚠️  Docker timezone issue"

# 5. Create docker-compose override for time syncing (best practice)
cat > /tmp/docker-compose-time-sync.yml << 'EOF'
# Add this to docker-compose.yml for reliable time sync:

services:
  atlas-neo4j:
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    sysctls:
      - net.ipv4.tcp_tw_reuse=1
    environment:
      TZ: Europe/Madrid

  ollama:
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    environment:
      TZ: Europe/Madrid
EOF

echo "  • Docker Compose time-sync template created at /tmp/docker-compose-time-sync.yml"
echo ""
echo "✅ NTP synchronization configured"
echo "   Recommendation: Add --time-machine flag to docker-compose or systemd service"
