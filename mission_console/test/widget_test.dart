/// Smoke de la app: arranca sin bridge y NO inventa datos.
///
/// Sustituye al `widget_test.dart` que genera `flutter create` (contaba
/// pulsaciones de un contador que ya no existe). Lo que fija es el criterio de
/// aceptación de t7-f3: **contra el runtime real, nunca contra datos de
/// ejemplo**. Sin bridge levantado la app tiene que decirlo, no maquetar.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mission_console/api/bridge_client.dart';
import 'package:mission_console/screens/missions_screen.dart';

void main() {
  testWidgets('sin bridge, la pantalla explica el fallo y no maqueta',
      (tester) async {
    // Puerto cerrado a propósito: es el escenario de "el operador no arrancó
    // `atlas os-bridge`", que es como se va a encontrar la app la mitad de las
    // veces.
    final client = BridgeClient(base: Uri.parse('http://127.0.0.1:1'));
    addTearDown(client.close);

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: MissionsScreen(client: client)),
    ));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.textContaining('El bridge no responde'), findsOneWidget);
    expect(find.textContaining('atlas os-bridge'), findsOneWidget);
    expect(find.text('Reintentar'), findsOneWidget);
  });
}
