import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

class BridgeClient {
  static const String _baseUrl = 'http://127.0.0.1:7341';
  static const String _wsUrl = 'ws://127.0.0.1:7341/events';

  WebSocketChannel? _wsChannel;

  Stream<dynamic> connectEvents() {
    _wsChannel = IOWebSocketChannel.connect(
      Uri.parse(_wsUrl),
      headers: {'Origin': _baseUrl},
    );
    return _wsChannel!.stream;
  }

  void disconnectEvents() {
    _wsChannel?.sink.close();
  }

  Future<List<dynamic>> getMissions() async {
    final response = await http.get(Uri.parse('$_baseUrl/missions'));
    if (response.statusCode == 200) {
      final json = jsonDecode(response.body);
      return json['missions'] as List<dynamic>? ?? [];
    } else {
      throw Exception('Failed to load missions');
    }
  }

  Future<Map<String, dynamic>> getMission(String id) async {
    final response = await http.get(Uri.parse('$_baseUrl/missions/$id'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Failed to load mission $id');
    }
  }

  Future<void> approveMission(String id) async {
    final response = await http.post(Uri.parse('$_baseUrl/missions/$id/approve'));
    if (response.statusCode != 200) {
      throw Exception('Failed to approve mission $id: ${response.body}');
    }
  }

  Future<void> parkMission(String id) async {
    // "Park" currently delegates to reject or hold mechanism
    final response = await http.post(Uri.parse('$_baseUrl/missions/$id/reject'));
    if (response.statusCode != 200) {
      throw Exception('Failed to park/reject mission $id: ${response.body}');
    }
  }

  Future<Map<String, dynamic>> getRadar() async {
    final response = await http.get(Uri.parse('$_baseUrl/missions/radar'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    } else {
      throw Exception('Failed to load radar');
    }
  }

  Future<List<dynamic>> getGraphCommunities() async {
    final response = await http.get(Uri.parse('$_baseUrl/graph/communities'));
    if (response.statusCode == 200) {
      final json = jsonDecode(response.body);
      return json['communities'] as List<dynamic>? ?? [];
    } else {
      throw Exception('Failed to load communities');
    }
  }

  Future<List<dynamic>> getSemanticNeighbors(String noteStem) async {
    final response = await http.get(Uri.parse('$_baseUrl/graph/semantic_neighbors/$noteStem'));
    if (response.statusCode == 200) {
      final json = jsonDecode(response.body);
      return json['neighbors'] as List<dynamic>? ?? [];
    } else {
      throw Exception('Failed to load semantic neighbors for $noteStem');
    }
  }
}
