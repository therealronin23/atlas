"""Mission Layer runtime (Foundry, ADR-069).

`atlas.api.missions` es la PROYECCIÓN read-only (bridge); este paquete es el
lado runtime que sí ejecuta: la ruta dorada de autoconstrucción. El bridge
JAMÁS debe importar nada de aquí (ADR-058)."""
