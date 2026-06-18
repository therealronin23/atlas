# Diseño de la Membrana de Seguridad (Membrane)

## Visión General
La membrana es un componente de defensa en profundidad que actúa como un filtro de contenido antes de que cualquier tarea pueda ser ejecutada por el Orchestrator. Se inspira en el concepto de *osmosis filter* y en las técnicas de hipermutación descritas en ADR‑054.

## Responsabilidades
1. **Inspección de Contenido** – Analizar archivos adjuntos, scripts y cualquier artefacto que una tarea quiera cargar.
2. **Decisión de Aprobación** – Utilizar la lógica del `Decider` para determinar si el contenido es seguro.
3. **Registro Merkle** – Cada inspección se registra en el Merkle log con `action="membrane.inspection"` y `risk_level` apropiado.
4. **Mutación Hiperbólica** – Opcionalmente aplicar transformaciones aleatorias a contenido no crítico para aumentar la resiliencia.

## API Propuesta
```python
class Membrane:
    def __init__(self, decider: Decider, logger: MerkleLogger):
        self.decider = decider
        self.logger = logger

    def protect(self, payload: bytes, context: dict) -> bool:
        """
        Evalúa el payload y devuelve True si pasa la inspección.
        Registra el resultado en Merkle.
        """
        # 1. Escaneo antivirus (reutiliza Antivirus)
        if not Antivirus.scan(payload):
            self.logger.log(action="membrane.blocked", risk="high")
            return False

        # 2. Inspección de patrón (osmosis filter)
        if not ContentFilter.is_blocked(payload):
            self.logger.log(action="membrane.blocked", risk="medium")
            return False

        # 3. Decisión del Decider
        decision = self.decider.evaluate(context, payload)
        self.logger.log(action="membrane.inspection", risk="low" if decision else "high")
        return decision
```

## Integración con Decider
- La membrana delega la decisión final al `Decider`, que evalúa políticas de acceso y riesgo.
- El `Decider` puede marcar la tarea como `REQUIRE_APPROVAL` si la membrana devuelve `True` pero el riesgo es `medium`.

## Pruebas
- **Unitarias**: Verificar que `protect()` devuelve `True` para payloads limpios y `False` para payloads con malware o patrones bloqueados.
- **Integración**: Simular una cadena completa de aprobación y asegurar que el Merkle log contiene los eventos esperados.

## Referencias
- ADR‑054 – *Defense‑in‑Depth Deception*.
- `src/atlas/security/antivirus.py` (propuesta).
- `src/atlas/security/content_filter.py` (propuesta).