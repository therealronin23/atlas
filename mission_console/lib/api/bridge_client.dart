/// Cliente del Atlas OS Bridge (ADR-058) — `127.0.0.1:7341`.
///
/// Sólo `dart:io` y `dart:convert`: sin `http` ni `web_socket_channel`. No es
/// ascetismo, es que el bridge escucha en loopback y habla JSON y WebSocket
/// planos, y `HttpClient` de la stdlib cubre ambos. Menos dependencias que
/// auditar en un cliente que va a manejar aprobaciones de misiones.
///
/// Contrato mapeado sondeando el servidor VIVO el 2026-08-10, no leyendo docs:
///
///   GET  /health                    {status, real, service, os_events, ...}
///   GET  /missions?limit=N          {real, total, by_state, by_risk, by_origin, missions[]}
///   GET  /missions/{id}             {real, mission, receipt}
///   GET  /missions/radar            {real, findings[]}
///   POST /missions/{id}/approve
///   POST /missions/{id}/reject
///   WS   /events                    reenvía los últimos 50 y luego stream
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../models/mission.dart';

class BridgeException implements Exception {
  BridgeException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => statusCode == null
      ? 'BridgeException: $message'
      : 'BridgeException($statusCode): $message';
}

class BridgeClient {
  BridgeClient({
    Uri? base,
    this.authToken,
    HttpClient? httpClient,
  })  : base = base ?? Uri.parse('http://127.0.0.1:7341'),
        _http = httpClient ?? HttpClient();

  final Uri base;

  /// El bridge exige token sólo cuando NO escucha en loopback
  /// (`_configured_strong_token`). En local va nulo; se admite para no tener
  /// que reescribir el cliente el día que se exponga.
  final String? authToken;

  final HttpClient _http;

  void close() => _http.close(force: true);

  Future<Map<String, dynamic>> health() => _getJson('/health');

  Future<MissionsPage> missions({int limit = 50}) async {
    final json = await _getJson('/missions', query: {'limit': '$limit'});
    return MissionsPage.fromJson(json);
  }

  Future<Map<String, dynamic>> missionDetail(String id) =>
      _getJson('/missions/${Uri.encodeComponent(id)}');

  Future<List<Map<String, dynamic>>> radar() async {
    final json = await _getJson('/missions/radar');
    return ((json['findings'] as List?) ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  Future<Map<String, dynamic>> approve(String id) =>
      _postJson('/missions/${Uri.encodeComponent(id)}/approve');

  Future<Map<String, dynamic>> reject(String id) =>
      _postJson('/missions/${Uri.encodeComponent(id)}/reject');

  /// Stream de eventos del OS. El servidor reenvía los últimos 50 al conectar
  /// y luego empuja los nuevos, así que el panel arranca con contexto.
  Stream<OsEvent> events() async* {
    final uri = base.replace(scheme: 'ws', path: '/events');
    final socket = await WebSocket.connect(
      uri.toString(),
      headers: {
        // OBLIGATORIO. `_validate_websocket_origin` del bridge cierra con 1008
        // si falta `Origin` — es su defensa contra CSWSH (un navegador podría
        // abrir este WS desde otra página y leer los eventos del OS). Un
        // cliente de escritorio no manda `Origin` por su cuenta, así que hay
        // que ponerlo, igual al host, o el panel se queda mudo.
        //
        // Detectado ejecutando la app contra el runtime real: los tests
        // pasaban, la lista de misiones cargaba, y el panel decía "el bridge
        // cerró el stream". Contra un mock no habría salido.
        'origin': base.replace(scheme: 'http').origin,
        if (authToken != null) 'authorization': 'Bearer $authToken',
      },
    );
    try {
      await for (final raw in socket) {
        if (raw is! String) continue;
        final decoded = jsonDecode(raw);
        if (decoded is Map<String, dynamic>) yield OsEvent.fromJson(decoded);
      }
    } finally {
      await socket.close();
    }
  }

  Future<Map<String, dynamic>> _getJson(
    String path, {
    Map<String, String>? query,
  }) async {
    final uri = base.replace(path: path, queryParameters: query);
    final request = await _http.getUrl(uri);
    _authorize(request);
    return _leer(await request.close(), uri);
  }

  Future<Map<String, dynamic>> _postJson(String path) async {
    final uri = base.replace(path: path);
    final request = await _http.postUrl(uri);
    _authorize(request);
    request.headers.contentType = ContentType.json;
    request.write('{}');
    return _leer(await request.close(), uri);
  }

  void _authorize(HttpClientRequest request) {
    final token = authToken;
    if (token != null) request.headers.set('authorization', 'Bearer $token');
  }

  Future<Map<String, dynamic>> _leer(HttpClientResponse response, Uri uri) async {
    final body = await response.transform(utf8.decoder).join();
    if (response.statusCode >= 400) {
      // El cuerpo del error del bridge suele traer el motivo; se conserva
      // recortado. Un "error 500" a secas obliga a ir al log del servidor, y la
      // gracia de esta consola es no tener que hacerlo.
      throw BridgeException(
        '$uri -> ${_recorte(body)}',
        statusCode: response.statusCode,
      );
    }
    final decoded = jsonDecode(body);
    if (decoded is! Map<String, dynamic>) {
      throw BridgeException('$uri devolvió ${decoded.runtimeType}, no un objeto');
    }
    return decoded;
  }

  static String _recorte(String texto) =>
      texto.length <= 300 ? texto : '${texto.substring(0, 300)}…';
}
