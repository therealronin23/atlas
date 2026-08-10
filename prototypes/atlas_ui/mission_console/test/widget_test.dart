import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mission_console/main.dart';

void main() {
  testWidgets('MissionConsoleApp builds without throwing', (WidgetTester tester) async {
    await tester.pumpWidget(const MissionConsoleApp());
    await tester.pump();

    expect(find.byType(Scaffold), findsOneWidget);
  });
}
