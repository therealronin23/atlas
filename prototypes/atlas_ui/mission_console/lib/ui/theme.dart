import 'package:flutter/material.dart';

class AtlasTheme {
  // Semantic Color Grammar from DIRECCION_ESTETICA.md
  static const Color azulInteraccion = Color(0xFF2196F3);
  static const Color cianIA = Color(0xFF00E5FF); // Glow, thinking
  static const Color verdeVerificado = Color(0xFF00E676);
  static const Color ambarPendiente = Color(0xFFFFC400);
  static const Color rojoError = Color(0xFFFF1744);
  static const Color moradoMemoria = Color(0xFFD500F9); // Ext. IA
  static const Color grisSistema = Color(0xFF9E9E9E);
  static const Color naranjaRiesgo = Color(0xFFFF6D00); // Friction

  // Background and surfaces (Deep black, not gray-app)
  static const Color background = Color(0xFF060B10);
  static const Color surface = Color(0xFF141A21);
  static const Color surfaceElevated = Color(0xFF1E252E);

  static ThemeData get darkTheme {
    return ThemeData.dark(useMaterial3: true).copyWith(
      scaffoldBackgroundColor: background,
      colorScheme: const ColorScheme.dark(
        primary: cianIA,
        secondary: azulInteraccion,
        surface: surface,
        error: rojoError,
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: Color(0x339EEFFF)),
        ),
      ),
      textTheme: const TextTheme(
        bodyMedium: TextStyle(fontFamily: 'monospace', color: Colors.white70),
        titleLarge: TextStyle(fontFamily: 'monospace', color: Colors.white, fontWeight: FontWeight.bold),
        titleMedium: TextStyle(fontFamily: 'monospace', color: Colors.white, fontWeight: FontWeight.bold),
      ),
    );
  }
}
