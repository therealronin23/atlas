/// El parseo se prueba contra el payload REAL del bridge, no contra uno ideal.
///
/// Los fixtures de este fichero se copiaron de la respuesta de
/// `GET /missions` del runtime vivo el 2026-08-10 (293 misiones, cinco estados,
/// cuatro orígenes). Inventarse un JSON "limpio" habría probado que el parser
/// entiende mi imaginación, no lo que el servidor manda: `gate` y `receipt_ref`
/// llegan nulos a menudo, y `source`/`next_action` son objetos anidados.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:mission_console/models/mission.dart';

// Copiado literalmente de la respuesta del bridge (ecosystem_drift_radar).
const Map<String, dynamic> _misionReal = {
  'mission_id': 'msn_ecodrift-edff03d5c37b',
  'intent': 'Actualizar docs/design/atlas_ecosystem_map.md: 7 ADR(s) sin fila',
  'state': 'plan_proposed',
  'risk': 'low',
  'origin': 'ecosystem_drift_radar',
  'source': {'kind': 'ecosystem_drift', 'ref': 'ecodrift-edff03d5c37b'},
  'created_at': '2026-08-10T15:54:14.807694+00:00',
  'updated_at': '2026-08-10T15:54:14.807694+00:00',
  'artifacts': ['docs/design/atlas_ecosystem_map.md'],
  'evidence_bundle': {
    'validation': null,
    'evidence': {
      'drift': ['ADR-079 sin fila en docs/design/atlas_ecosystem_map.md'],
    },
  },
  'next_action': {
    'kind': 'cli',
    'command': 'atlas update propose --dossier ...',
  },
  'human_action_required': true,
  'gate': null,
  'model_use': <dynamic>[],
  'soul_invocations': <dynamic>[],
  'receipt_ref': null,
};

void main() {
  group('Mission.fromJson sobre el payload real', () {
    test('lee los campos que la UI pinta', () {
      final m = Mission.fromJson(_misionReal);

      expect(m.id, 'msn_ecodrift-edff03d5c37b');
      expect(m.state, 'plan_proposed');
      expect(m.risk, 'low');
      expect(m.origin, 'ecosystem_drift_radar');
      expect(m.humanActionRequired, isTrue);
      expect(m.artifacts, ['docs/design/atlas_ecosystem_map.md']);
    });

    test('los nulos del servidor no revientan la pantalla', () {
      // `gate` y `receipt_ref` llegan nulos en la mayoría de misiones reales.
      final m = Mission.fromJson(_misionReal);

      expect(m.gate, isNull);
      expect(m.receiptRef, isNull);
    });

    test('expone el comando de next_action', () {
      final m = Mission.fromJson(_misionReal);

      expect(m.nextCommand, startsWith('atlas update propose'));
    });

    test('sin next_action devuelve null, no cadena vacía', () {
      // La UI necesita distinguir "no propone comando" de "comando vacío".
      final m = Mission.fromJson({..._misionReal, 'next_action': null});

      expect(m.nextCommand, isNull);
    });

    test('un estado nuevo del servidor no rompe el cliente', () {
      // El bridge puede añadir estados. La app tiene que seguir pintando.
      final m = Mission.fromJson({..._misionReal, 'state': 'estado_futuro'});

      expect(m.state, 'estado_futuro');
      expect(m.esperandoAprobacion, isFalse);
    });

    test('un payload mutilado no lanza', () {
      final m = Mission.fromJson({'mission_id': 'x'});

      expect(m.id, 'x');
      expect(m.state, 'desconocido');
      expect(m.artifacts, isEmpty);
      expect(m.humanActionRequired, isFalse);
    });
  });

  group('MissionsPage', () {
    test('usa los agregados del SERVIDOR, no los recuenta', () {
      // Recontar en el cliente daría cifras distintas en cuanto `limit`
      // recorte: dos fuentes de verdad para el mismo número es como se
      // fabrican los paneles que mienten.
      final page = MissionsPage.fromJson({
        'real': true,
        'total': 293,
        'by_state': {
          'plan_proposed': 35,
          'awaiting_human_approval': 6,
          'applied': 14,
          'rejected': 203,
          'failed': 35,
        },
        'by_risk': {'low': 258, 'medium': 35},
        'by_origin': {'self_audit': 285, 'swarm': 2, 'manual': 5},
        'missions': [_misionReal],
      });

      expect(page.total, 293);
      expect(page.missions, hasLength(1), reason: 'la lista viene recortada');
      expect(page.byState['awaiting_human_approval'], 6);
      expect(page.byRisk['low'], 258);
      expect(page.byOrigin['self_audit'], 285);
    });

    test('una página vacía no lanza', () {
      final page = MissionsPage.fromJson({'real': true});

      expect(page.total, 0);
      expect(page.missions, isEmpty);
      expect(page.byState, isEmpty);
    });
  });

  group('OsEvent', () {
    test('acepta los nombres alternativos del campo de tipo', () {
      // Un panel de eventos que se queda mudo por un renombrado del servidor
      // es peor que uno que enseña "desconocido".
      expect(OsEvent.fromJson({'kind': 'mission.created'}).kind,
          'mission.created');
      expect(OsEvent.fromJson({'type': 'tool.invoked'}).kind, 'tool.invoked');
      expect(OsEvent.fromJson({}).kind, 'desconocido');
    });
  });
}
