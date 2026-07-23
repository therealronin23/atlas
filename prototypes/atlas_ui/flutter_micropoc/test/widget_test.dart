// Smoke test mínimo del micro-PoC: la pantalla monta sin excepciones.
// No es el foco de este ítem (medición, no cobertura de producto).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flutter_micropoc/main.dart';

void main() {
  testWidgets('MicroPocApp builds without throwing', (WidgetTester tester) async {
    await tester.pumpWidget(const MicroPocApp());
    await tester.pump();

    expect(find.byType(Scaffold), findsOneWidget);
  });
}
