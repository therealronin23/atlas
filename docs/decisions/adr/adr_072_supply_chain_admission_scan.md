# ADR-072 — Escaneo local y acotado antes de admitir artefactos de terceros

- **Estado**: aceptado (A1; aún sin consumidor de runtime)
- **Fecha**: 2026-07-20
- **Contexto previo**: AGENTS.md invariantes 1, 4, 6 y 8; ADR-063 Gate
  Engine; investigación limpia de Cline/Aider/OpenHands y del escáner
  Bumblebee fijado a commit `4a02b80aaca86641767c0d6cbe77c6856e4b481b`.

## Contexto

Atlas necesita examinar plugins, herramientas y artefactos externos antes de
que un futuro instalador los admita. Las investigaciones confirmaron que copiar
un instalador de plugins no es aceptable: los sistemas observados permiten
fuentes mutables, scripts de ciclo de vida o ejecución antes de que exista una
frontera de admisión de Atlas. Un escáner que importe, instale o ejecute para
"entender" un paquete invalidaría precisamente esa frontera.

La primera necesidad concreta es una evidencia local, reproducible y
serializable sobre un árbol ya materializado, sin dependencia nueva ni servicio
remoto. También debe distinguir una observación completa de una cortada por
límites: el segundo caso no puede convertirse silenciosamente en permiso.

## Decisión

1. Se incorpora `SupplyChainScanner` como API de biblioteca local y
   exclusivamente de lectura. A1 **no** modifica aún el instalador, TrialGate,
   CLI ni registro de plugins; por tanto no se declara una admisión runtime
   activa.
2. El recorrido sólo hashea ficheros regulares, no sigue enlaces simbólicos y
   omite directorios de dependencias/caché conocidos. Límite de tiempo, número
   de ficheros, tamaño total o tamaño individual produce reporte terminal
   `partial` y veredicto `block`; una raíz ausente produce `failed`/`block`.
3. A1 extrae únicamente metadatos de `package.json`, `pyproject.toml`,
   `requirements*.txt` y `go.mod`. Los nombres de scripts npm de ciclo de vida
   se registran sin conservar ni ejecutar su comando. Los indicadores de
   paquetes son exactos tras normalización por ecosistema; no hay matching por
   subcadena ni resolución de dependencias transitivas.
4. El resultado tiene contrato Pydantic estricto y JSON Schema Draft 2020-12.
   `record_id` es el hash canónico de la evidencia (independiente de ruta,
   reloj y corrida); `scan_id` identifica una corrida concreta. El escaneo
   local de sólo lectura no es un efecto externo y no abre un recibo Merkle por
   sí mismo; la acción futura que admita o instale sí deberá hacerlo.
5. La implementación es clean-room: toma la forma de seguridad útil de
   Bumblebee (recorrido acotado, hashes estables y reporte terminal), no copia
   su código ni adopta su ejecución, dependencias o autoridad.

## Alternativas descartadas

- **Ejecutar gestores de paquetes para resolver el árbol**: descartado porque
  puede ejecutar hooks, descargar contenido mutable o tocar el host antes de
  que Atlas haya decidido admitirlo.
- **Adoptar el código de un escáner externo**: descartado; Atlas necesita una
  superficie pequeña, auditable y compatible con sus invariantes, no heredar
  su runtime ni su modelo de confianza.
- **Cablear el escáner directamente a la carga de plugins ahora**: descartado
  hasta que A2 defina staging inmutable, manifest tipado, procedencia,
  aprobación y recibo Merkle en una única transición.

## Consecuencias

- Los consumidores futuros deben volver a escanear después de cualquier
  mutación del árbol; un `record_id` sólo acredita los bytes observados.
- `partial`, `failed`, enlaces simbólicos, scripts npm de ciclo de vida y
  indicadores high/critical bloquean; indicadores medium requieren `review`.
- A2 deberá conectar este reporte al staging de PluginManifest/TrialGate antes
  de ejecutar código de terceros, añadir procedencia y firma cuando haya una
  fuente decidida, y registrar la decisión/efecto en Merkle con aprobación
  humana para sensibilidad alta.
- A1 no sustituye auditoría de CVE, verificación de lockfiles, sandbox de
  ejecución, validación de firma ni política de red. Es evidencia de admisión,
  no una promesa de que el artefacto es seguro.
