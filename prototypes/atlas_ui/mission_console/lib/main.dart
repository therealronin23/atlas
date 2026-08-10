import 'package:flutter/material.dart';
import 'api/bridge_client.dart';
import 'ui/theme.dart';
import 'ui/mission_card.dart';
import 'ui/knowledge_graph_view.dart';

void main() {
  runApp(const MissionConsoleApp());
}

class MissionConsoleApp extends StatelessWidget {
  const MissionConsoleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Atlas Mission Console (T2.1)',
      theme: AtlasTheme.darkTheme,
      home: const MissionConsoleScreen(),
    );
  }
}

class MissionConsoleScreen extends StatefulWidget {
  const MissionConsoleScreen({super.key});

  @override
  State<MissionConsoleScreen> createState() => _MissionConsoleScreenState();
}

class _MissionConsoleScreenState extends State<MissionConsoleScreen> {
  final BridgeClient _client = BridgeClient();
  List<dynamic> _missions = [];
  bool _isLoading = true;
  String _error = '';
  int _wsEventCount = 0;
  int _selectedIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadMissions();
    _client.connectEvents().listen((event) {
      if (mounted) {
        setState(() {
          _wsEventCount++;
        });
      }
    }, onError: (err) {
      debugPrint('WS Error: $err');
    });
  }

  Future<void> _loadMissions() async {
    setState(() {
      _isLoading = true;
      _error = '';
    });
    try {
      final missions = await _client.getMissions();
      if (mounted) {
        setState(() {
          _missions = missions;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _client.disconnectEvents();
    super.dispose();
  }

  Future<void> _handleApprove(String id) async {
    try {
      await _client.approveMission(id);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Mission $id approved')),
        );
        _loadMissions();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to approve: $e', style: const TextStyle(color: AtlasTheme.rojoError))),
        );
      }
    }
  }

  Future<void> _handlePark(String id) async {
    try {
      await _client.parkMission(id);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Mission $id parked (rejected)')),
        );
        _loadMissions();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to park: $e', style: const TextStyle(color: AtlasTheme.rojoError))),
        );
      }
    }
  }

  Widget _buildMissions() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator(color: AtlasTheme.cianIA));
    }
    if (_error.isNotEmpty) {
      return Center(child: Text('Error: $_error', style: const TextStyle(color: AtlasTheme.rojoError, fontFamily: 'monospace')));
    }
    if (_missions.isEmpty) {
      return const Center(
        child: Text(
          'sin datos',
          style: TextStyle(color: AtlasTheme.grisSistema, fontSize: 18, fontFamily: 'monospace'),
        ),
      );
    }
    return ListView.builder(
      itemCount: _missions.length,
      itemBuilder: (context, index) {
        final mission = _missions[index] as Map<String, dynamic>;
        return MissionCard(
          mission: mission,
          onApprove: () => _handleApprove(mission['id']),
          onPark: () => _handlePark(mission['id']),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Atlas Mission Console', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: AtlasTheme.surfaceElevated,
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 16.0),
              child: Row(
                children: [
                  const Icon(Icons.cable, color: AtlasTheme.cianIA, size: 16),
                  const SizedBox(width: 8),
                  Text('WS Events: $_wsEventCount', style: const TextStyle(color: AtlasTheme.cianIA, fontFamily: 'monospace')),
                ],
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadMissions,
          ),
        ],
      ),
      body: _selectedIndex == 0 ? _buildMissions() : KnowledgeGraphView(client: _client),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _selectedIndex,
        onTap: (index) => setState(() => _selectedIndex = index),
        selectedItemColor: AtlasTheme.cianIA,
        unselectedItemColor: AtlasTheme.grisSistema,
        backgroundColor: AtlasTheme.surfaceElevated,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.list), label: 'Missions'),
          BottomNavigationBarItem(icon: Icon(Icons.hub), label: 'Knowledge Graph'),
        ],
      ),
    );
  }
}
