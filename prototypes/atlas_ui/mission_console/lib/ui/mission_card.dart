import 'package:flutter/material.dart';
import 'theme.dart';

class MissionCard extends StatelessWidget {
  final Map<String, dynamic> mission;
  final VoidCallback onApprove;
  final VoidCallback onPark;

  const MissionCard({
    super.key,
    required this.mission,
    required this.onApprove,
    required this.onPark,
  });

  @override
  Widget build(BuildContext context) {
    final title = mission['title'] ?? 'Unknown Mission';
    final state = mission['state'] ?? 'draft';
    final id = mission['id'] ?? '---';
    final riskStr = mission['risk'] ?? 'low';

    Color stateColor;
    switch (state) {
      case 'verified':
      case 'approved':
        stateColor = AtlasTheme.verdeVerificado;
        break;
      case 'pending':
        stateColor = AtlasTheme.ambarPendiente;
        break;
      case 'error':
        stateColor = AtlasTheme.rojoError;
        break;
      default:
        stateColor = AtlasTheme.azulInteraccion;
    }

    Color riskColor;
    if (riskStr == 'high') {
      riskColor = AtlasTheme.naranjaRiesgo;
    } else {
      riskColor = AtlasTheme.grisSistema;
    }

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 16.0),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(id, style: const TextStyle(color: AtlasTheme.grisSistema, fontSize: 12)),
                Row(
                  children: [
                    Icon(Icons.circle, size: 10, color: riskColor),
                    const SizedBox(width: 4),
                    Text('Risk: $riskStr', style: const TextStyle(fontSize: 12)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Chip(
                  label: Text(state.toUpperCase()),
                  backgroundColor: stateColor.withValues(alpha: 0.2),
                  side: BorderSide(color: stateColor),
                  labelStyle: TextStyle(color: stateColor, fontWeight: FontWeight.bold, fontSize: 12),
                ),
                if (state == 'pending' || state == 'draft')
                  Row(
                    children: [
                      TextButton(
                        onPressed: onPark,
                        style: TextButton.styleFrom(foregroundColor: AtlasTheme.grisSistema),
                        child: const Text('Park'),
                      ),
                      const SizedBox(width: 8),
                      ElevatedButton(
                        onPressed: onApprove,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AtlasTheme.verdeVerificado.withValues(alpha: 0.2),
                          foregroundColor: AtlasTheme.verdeVerificado,
                          side: const BorderSide(color: AtlasTheme.verdeVerificado),
                        ),
                        child: const Text('Approve'),
                      ),
                    ],
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
