/// Modelo de misión, calcado del payload REAL de `GET /missions`.
///
/// Los campos salen de sondear el bridge vivo el 2026-08-10, no de un
/// documento: `mission_id, intent, state, risk, origin, source, created_at,
/// updated_at, artifacts, evidence_bundle, next_action, human_action_required,
/// gate, model_use, soul_invocations, receipt_ref`.
///
/// Todo se parsea a la defensiva. El bridge sirve misiones de cinco orígenes
/// distintos (`self_audit`, `swarm`, `manual`, `ecosystem_drift_radar`…) y no
/// todas traen los mismos campos poblados: `gate` y `receipt_ref` llegan nulos
/// a menudo. Una UI que asuma que están se cae contra los datos de verdad, que
/// es justo lo que este proyecto lleva una semana corrigiendo en otros sitios.
library;

class Mission {
  const Mission({
    required this.id,
    required this.intent,
    required this.state,
    required this.risk,
    required this.origin,
    required this.createdAt,
    required this.updatedAt,
    required this.humanActionRequired,
    this.artifacts = const [],
    this.nextAction,
    this.evidenceBundle,
    this.gate,
    this.receiptRef,
    this.source,
  });

  final String id;
  final String intent;
  final String state;
  final String risk;
  final String origin;
  final String createdAt;
  final String updatedAt;
  final bool humanActionRequired;
  final List<String> artifacts;
  final Map<String, dynamic>? nextAction;
  final Map<String, dynamic>? evidenceBundle;
  final Map<String, dynamic>? gate;
  final String? receiptRef;
  final Map<String, dynamic>? source;

  factory Mission.fromJson(Map<String, dynamic> json) {
    return Mission(
      id: _str(json['mission_id']),
      intent: _str(json['intent']),
      state: _str(json['state'], fallback: 'desconocido'),
      risk: _str(json['risk'], fallback: 'desconocido'),
      origin: _str(json['origin'], fallback: 'desconocido'),
      createdAt: _str(json['created_at']),
      updatedAt: _str(json['updated_at']),
      humanActionRequired: json['human_action_required'] == true,
      artifacts: _strList(json['artifacts']),
      nextAction: _map(json['next_action']),
      evidenceBundle: _map(json['evidence_bundle']),
      gate: _map(json['gate']),
      receiptRef: json['receipt_ref'] == null ? null : _str(json['receipt_ref']),
      source: _map(json['source']),
    );
  }

  /// El comando que el operador debe ejecutar, si la misión trae uno.
  ///
  /// `next_action` es `{kind, command}` en las misiones de `ecosystem_drift` y
  /// puede faltar en otras. Se devuelve nulo en vez de una cadena vacía para
  /// que la UI distinga "no hay acción" de "acción vacía".
  String? get nextCommand {
    final command = nextAction?['command'];
    if (command is String && command.trim().isNotEmpty) return command;
    return null;
  }

  bool get esperandoAprobacion => state == 'awaiting_human_approval';

  static String _str(dynamic value, {String fallback = ''}) =>
      value is String ? value : (value?.toString() ?? fallback);

  static Map<String, dynamic>? _map(dynamic value) =>
      value is Map<String, dynamic> ? value : null;

  static List<String> _strList(dynamic value) {
    if (value is List) return value.map((e) => e.toString()).toList();
    return const [];
  }
}

/// Los agregados que el bridge ya calcula: `by_state`, `by_risk`, `by_origin`.
///
/// Se usan tal cual en vez de recontar en el cliente. Contar aquí daría números
/// distintos de los del servidor en cuanto `limit` recorte la lista — dos
/// fuentes de verdad para la misma cifra es como se fabrican los paneles que
/// mienten.
class MissionsPage {
  const MissionsPage({
    required this.total,
    required this.missions,
    required this.byState,
    required this.byRisk,
    required this.byOrigin,
  });

  final int total;
  final List<Mission> missions;
  final Map<String, int> byState;
  final Map<String, int> byRisk;
  final Map<String, int> byOrigin;

  factory MissionsPage.fromJson(Map<String, dynamic> json) {
    return MissionsPage(
      total: (json['total'] as num?)?.toInt() ?? 0,
      missions: ((json['missions'] as List?) ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(Mission.fromJson)
          .toList(),
      byState: _counts(json['by_state']),
      byRisk: _counts(json['by_risk']),
      byOrigin: _counts(json['by_origin']),
    );
  }

  static Map<String, int> _counts(dynamic value) {
    if (value is! Map) return const {};
    return value.map((k, v) => MapEntry('$k', (v as num?)?.toInt() ?? 0));
  }
}

/// Evento del stream `WS /events`, en la forma que emite `OsEvent`.
class OsEvent {
  const OsEvent({
    required this.kind,
    required this.at,
    required this.payload,
  });

  final String kind;
  final String at;
  final Map<String, dynamic> payload;

  factory OsEvent.fromJson(Map<String, dynamic> json) {
    // El nombre del campo varía entre versiones del bridge; se aceptan los dos
    // en vez de fallar, porque un panel de eventos que se queda mudo por un
    // renombrado es peor que uno que muestra "desconocido".
    final kind = json['kind'] ?? json['type'] ?? json['event'] ?? 'desconocido';
    final at = json['at'] ?? json['timestamp'] ?? json['ts'] ?? '';
    return OsEvent(
      kind: '$kind',
      at: '$at',
      payload: json,
    );
  }
}
