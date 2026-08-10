/// Piezas de UI reutilizadas por las dos pantallas.
library;

import 'package:flutter/material.dart';

import '../theme.dart';

/// Etiqueta compacta de estado/riesgo/origen.
class Chip extends StatelessWidget {
  const Chip(this.texto, {required this.color, this.icono, super.key});

  final String texto;
  final Color color;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        border: Border.all(color: color.withValues(alpha: 0.5)),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icono != null) ...[
            Icon(icono, size: 12, color: color),
            const SizedBox(width: 4),
          ],
          Text(
            texto,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

/// Contador de una casilla de `by_state` / `by_risk`, pulsable para filtrar.
class Contador extends StatelessWidget {
  const Contador({
    required this.etiqueta,
    required this.valor,
    required this.color,
    required this.activo,
    required this.onTap,
    super.key,
  });

  final String etiqueta;
  final int valor;
  final Color color;
  final bool activo;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: activo ? color.withValues(alpha: 0.18) : kPanel,
          border: Border.all(color: activo ? color : kBorde),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('$valor',
                style: TextStyle(
                    color: color, fontSize: 20, fontWeight: FontWeight.bold)),
            Text(etiqueta,
                style: const TextStyle(color: kTextoTenue, fontSize: 11)),
          ],
        ),
      ),
    );
  }
}

/// Bloque de error honesto: dice qué falló y contra qué, sin tragárselo.
class PanelDeError extends StatelessWidget {
  const PanelDeError({required this.mensaje, this.onReintentar, super.key});

  final String mensaje;
  final VoidCallback? onReintentar;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 620),
        child: Container(
          margin: const EdgeInsets.all(24),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: kPanel,
            border: Border.all(color: kFallido.withValues(alpha: 0.6)),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Icon(Icons.link_off, color: kFallido, size: 18),
                const SizedBox(width: 8),
                Text('El bridge no responde',
                    style: TextStyle(
                        color: kFallido,
                        fontSize: 15,
                        fontWeight: FontWeight.w600)),
              ]),
              const SizedBox(height: 10),
              SelectableText(mensaje,
                  style: const TextStyle(
                      color: kTextoTenue, fontSize: 12, height: 1.5)),
              const SizedBox(height: 14),
              const Text(
                'Arráncalo con:  atlas os-bridge',
                style: TextStyle(
                    color: kTexto, fontSize: 12, fontFamily: 'monospace'),
              ),
              if (onReintentar != null) ...[
                const SizedBox(height: 14),
                FilledButton.tonalIcon(
                  onPressed: onReintentar,
                  icon: const Icon(Icons.refresh, size: 16),
                  label: const Text('Reintentar'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
