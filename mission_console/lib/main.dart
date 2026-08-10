/// Mission Console — la UI de misiones de Atlas (ADR-085, ADR-058).
///
/// Habla con el Atlas OS Bridge en `127.0.0.1:7341`. **Nunca con datos de
/// ejemplo**: si el bridge no está levantado, la app lo dice y explica cómo
/// arrancarlo, en vez de pintar una maqueta bonita que no significa nada. Ese
/// es el criterio de aceptación de t7-f3 y también la disciplina del resto del
/// repositorio — evidencia o silencio, nunca decorado.
///
/// El puerto se puede cambiar sin recompilar:
///     flutter run -d linux --dart-define=ATLAS_BRIDGE=http://127.0.0.1:7341
library;

import 'package:flutter/material.dart';

import 'api/bridge_client.dart';
import 'screens/events_panel.dart';
import 'screens/missions_screen.dart';
import 'theme.dart';

const String _bridgePorDefecto =
    String.fromEnvironment('ATLAS_BRIDGE', defaultValue: 'http://127.0.0.1:7341');

const String _token = String.fromEnvironment('ATLAS_BRIDGE_TOKEN');

void main() {
  runApp(const MissionConsoleApp());
}

class MissionConsoleApp extends StatefulWidget {
  const MissionConsoleApp({super.key});

  @override
  State<MissionConsoleApp> createState() => _MissionConsoleAppState();
}

class _MissionConsoleAppState extends State<MissionConsoleApp> {
  late final BridgeClient _client = BridgeClient(
    base: Uri.parse(_bridgePorDefecto),
    authToken: _token.isEmpty ? null : _token,
  );

  @override
  void dispose() {
    _client.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Atlas · Mission Console',
      debugShowCheckedModeBanner: false,
      theme: construirTema(),
      home: Scaffold(
        appBar: AppBar(
          backgroundColor: kPanel,
          titleSpacing: 20,
          title: Row(children: [
            const Text('Atlas',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(width: 8),
            const Text('Mission Console',
                style: TextStyle(color: kTextoTenue, fontSize: 14)),
            const Spacer(),
            Text(_bridgePorDefecto,
                style: const TextStyle(
                    color: kTextoTenue, fontSize: 11, fontFamily: 'monospace')),
          ]),
        ),
        body: Row(
          children: [
            Expanded(child: MissionsScreen(client: _client)),
            EventsPanel(client: _client),
          ],
        ),
      ),
    );
  }
}
