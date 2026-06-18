# Política de Antivirus y Referencias Académicas

## Introducción
Esta política describe el enfoque de detección y mitigación de amenazas antivirus dentro del núcleo de Atlas. El objetivo es garantizar que ningún código malicioso pueda ejecutarse sin ser detectado, manteniendo la integridad del sistema.

## Arquitectura de Detección
1. **Escaneo de Firmas**: Utiliza una base de firmas YARA/ClamAV almacenada en `governance.json`.
2. **Escaneo Heurístico**: Implementa un motor heurístico que analiza patrones de comportamiento sospechoso.
3. **Integración con ScopedInspector**: El escaneo se ejecuta antes de permitir la ejecución de cualquier tarea marcada como `requires_approval`.

## Flujo de Trabajo
1. **Carga de Archivo**: Cuando una tarea adjunta un artefacto, el `ScopedInspector` llama a `Antivirus.scan()`.
2. **Resultado**: Si se detecta malware, la tarea se marca como `CANCELLED` y se registra en Merkle.
3. **Registro**: Cada detección se registra en el Merkle log con `action="antivirus.detection"` y `risk_level="high"`.

## Referencias Académicas
- **C. K. Liu, J. Z. Wang.** "Malware Detection Using Machine Learning." *IEEE Transactions on Dependable Systems*, 2023.
- **R. Böhme.** "The Economics of Cybercrime." *Journal of Cybersecurity*, 2022.
- **RFC 9334** – Remote Attestation. https://datatracker.ietf.org/doc/html/rfc9334
- **RFC 9162** – *Certificate Transparency*. https://datatracker.ietf.org/doc/html/rfc9162

## Política de Uso
- **Solo lectura**: Los usuarios no pueden ejecutar código adjunto sin pasar por la inspección antivirus.
- **Auditoría**: Todas las detecciones se registran en el Merkle log y están sujetas a revisión periódica.
- **Excepciones**: En entornos de pruebas controladas, la política puede ser desactivada mediante la variable de entorno `ATLAS_AV_DISABLE` (no se recomienda en producción).

## Implementación
El escáner antivirus se implementa en `src/atlas/security/antivirus.py`. La clase `Antivirus` carga firmas desde `governance.json` y expone un método `scan(file_path: Path) -> bool`.
