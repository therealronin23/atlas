# 06 — Motion Grammar

El movimiento es parte del lenguaje de Atlas. No es decoración.

## Estados del núcleo

```text
Pulso lento            = reposo / listening
Pulso medio cyan       = razonando
Pulso rápido cyan      = ejecución activa
Brillo verde breve     = validación completada
Halo ámbar             = espera aprobación humana
Tensión roja           = error/bloqueo
Ondas internas         = búsqueda de memoria/contexto
Partículas salientes   = creación de artefacto
Partículas entrantes   = memoria absorbida
```

## Estados de nodos

```text
Nodo se ilumina        = usado en el proceso actual
Nodo aumenta masa      = gana relevancia/frecuencia
Nodo se enfría         = baja actividad
Nodo tiembla           = inconsistencia/error
Nodo se fragmenta      = contradicción o fuente dudosa
Nodo se duplica        = derivación/artefacto generado
Nodo se expande        = inspección por el usuario
Nodo se bloquea        = gate activo o permiso ausente
```

## Estados de conexiones

```text
Conexión brillante     = flujo activo
Conexión más gruesa    = relación reforzada
Conexión punteada      = relación inferida/no confirmada
Conexión roja          = dependencia fallida
Conexión ámbar         = dependencia pendiente de aprobación
```

## Regla

No añadir animaciones que no correspondan a evento o estado.
