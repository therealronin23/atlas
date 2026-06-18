# Diseño del Filtro de Osmosis

## Visión General
El filtro de osmosis es el componente responsable de la inspección de contenido antes de que este pueda pasar a la membrana. Implementa la lógica de *osmosis filter* descrita en ADR‑054, combinando detección de patrones y heurísticas de comportamiento.

## Responsabilidades
1. **Detección de Patrones** – Identificar firmas de código malicioso mediante expresiones regulares y árboles de sintaxis abstracta (AST).
2. **Evaluación de Riesgo** – Asignar un nivel de riesgo usando la puntuación de afinidad (affinity scoring) definida en ADR‑054.
3. **Bloqueo o Aprobación** – Decidir si el contenido es seguro (`allow`) o debe ser rechazado (`block`).
4. **Registro Merkle** – Cada inspección se registra con `action="osmosis.filter"` y el nivel de riesgo correspondiente.

## API Propuesta
```python
class OsmosisFilter:
    def __init__(self, antivirus: Antivirus, logger: MerkleLogger):
        self.antivirus = antivirus
        self.logger = logger

    def inspect(self, payload: bytes, context: dict) -> bool:
        """
        Evalúa el payload y devuelve True si pasa la inspección.
        Registra el resultado en Merkle.
        """
        # 1. Escaneo antivirus
        if not self.antivirus.scan(payload):
            self.logger.log(action="osmosis.filter.blocked", risk="high")
            return False

        # 2. Análisis de patrones (osmosis)
        if OsmosisPatternMatcher.is_malicious(payload):
            self.logger.log(action="osmosis.filter.blocked", risk="medium")
            return False

        # 3. Evaluación de riesgo mediante afinidad
        risk_score = AffinityScorer.score(payload, context)
        if risk_score > 0.8:
            self.logger.log(action="osmosis.filter.high_risk", risk="high")
            return False

        self.logger.log(action="osmosis.filter.allowed", risk="low")
        return True
```

## Integración con Membrana
- La membrana (`Membrane.protect`) delega la primera línea de inspección al `OsmosisFilter`.
- El resultado (`True/False`) se pasa al `Decider` para la decisión final.
- En caso de `False`, la tarea se marca como `CANCELLED` y se registra en el Merkle log.

## Pruebas Recomendadas
- **Unitarias**: Verificar que `inspect()` devuelve `True` para payloads limpios y `False` para payloads con patrones maliciosos o riesgo alto.
- **Integración**: Simular el flujo completo desde `OsmosisFilter` → `Membrane` → `Decider` y validar que el Merkle log contiene los eventos esperados.

## Referencias
- ADR‑054 – *Defense‑in‑Depth Deception*.
- `src/atlas/security/antivirus.py` (propuesta).
- `src/atlas/security/content_filter.py` (propuesta).
- `src/atlas/transparency/merkle_tree.py` – utilidades de Merkle.