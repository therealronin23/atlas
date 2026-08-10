/// Paleta y helpers de color, atados al VOCABULARIO del runtime.
///
/// Los estados y riesgos no son inventados: salen de `by_state` y `by_risk` del
/// bridge (`plan_proposed`, `awaiting_human_approval`, `applied`, `rejected`,
/// `failed`; `low`, `medium`). El color se deriva del estado real y cualquier
/// valor no previsto cae a un gris neutro en vez de romper — el servidor puede
/// añadir estados sin que esta app deje de pintar.
library;

import 'package:flutter/material.dart';

const Color kFondo = Color(0xFF11141A);
const Color kPanel = Color(0xFF181C24);
const Color kBorde = Color(0xFF262C38);
const Color kTexto = Color(0xFFE6E9EF);
const Color kTextoTenue = Color(0xFF98A0B0);

const Color kEsperando = Color(0xFFE0A33E); // pide decisión humana
const Color kAplicado = Color(0xFF4FB477);
const Color kRechazado = Color(0xFF7C8496);
const Color kFallido = Color(0xFFD2603F);
const Color kPropuesto = Color(0xFF5A93D4);
const Color kNeutro = Color(0xFF6D7484);

Color colorDeEstado(String estado) => switch (estado) {
      'awaiting_human_approval' => kEsperando,
      'applied' => kAplicado,
      'rejected' => kRechazado,
      'failed' => kFallido,
      'plan_proposed' => kPropuesto,
      _ => kNeutro,
    };

Color colorDeRiesgo(String riesgo) => switch (riesgo) {
      'high' => kFallido,
      'medium' => kEsperando,
      'low' => kAplicado,
      _ => kNeutro,
    };

ThemeData construirTema() {
  final base = ThemeData.dark(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: kFondo,
    colorScheme: base.colorScheme.copyWith(
      surface: kPanel,
      primary: kPropuesto,
    ),
    dividerColor: kBorde,
    textTheme: base.textTheme.apply(
      bodyColor: kTexto,
      displayColor: kTexto,
    ),
  );
}
