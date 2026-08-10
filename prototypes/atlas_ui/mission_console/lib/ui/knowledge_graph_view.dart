import 'dart:math';
import 'package:flutter/material.dart';
import '../api/bridge_client.dart';
import 'theme.dart';

class KnowledgeGraphView extends StatefulWidget {
  final BridgeClient client;

  const KnowledgeGraphView({super.key, required this.client});

  @override
  State<KnowledgeGraphView> createState() => _KnowledgeGraphViewState();
}

class _KnowledgeGraphViewState extends State<KnowledgeGraphView> with SingleTickerProviderStateMixin {
  List<dynamic> _nodes = [];
  Map<String, List<dynamic>> _edges = {}; // from -> [to]
  bool _isLoading = true;
  String? _error;

  String? _activeCommunityPath;
  String? _activeCommunityTitle;
  
  late AnimationController _animationController;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);
    _loadCommunities();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  Future<void> _loadCommunities() async {
    setState(() {
      _isLoading = true;
      _error = null;
      _activeCommunityPath = null;
      _activeCommunityTitle = null;
    });

    try {
      final communities = await widget.client.getGraphCommunities();
      setState(() {
        _nodes = communities.take(15).toList(); // show top 15
        _edges = {};
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _loadNeighbors(String path, String title) async {
    setState(() {
      _isLoading = true;
      _error = null;
      _activeCommunityPath = path;
      _activeCommunityTitle = title;
    });

    try {
      // Extract stem from path (e.g. "docs/knowledge/foo.md" -> "foo")
      final parts = path.split('/');
      final filename = parts.last;
      final stem = filename.endsWith('.md') ? filename.substring(0, filename.length - 3) : filename;
      
      final neighbors = await widget.client.getSemanticNeighbors(stem);
      setState(() {
        _nodes = neighbors;
        _edges = {};
        for (var neighbor in neighbors) {
          // just pseudo edges for visualization: center to neighbor
          _edges.putIfAbsent(path, () => []).add(neighbor['path']);
        }
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: Row(
            children: [
              const Text(
                'LIVING KNOWLEDGE GRAPH',
                style: TextStyle(color: AtlasTheme.cianIA, fontSize: 16, fontFamily: 'monospace'),
              ),
              const Spacer(),
              if (_activeCommunityPath != null)
                TextButton.icon(
                  onPressed: _loadCommunities,
                  icon: const Icon(Icons.arrow_back, color: AtlasTheme.cianIA, size: 16),
                  label: const Text('Back to Communities', style: TextStyle(color: AtlasTheme.cianIA, fontFamily: 'monospace')),
                )
              else
                IconButton(
                  onPressed: _loadCommunities,
                  icon: const Icon(Icons.refresh, color: AtlasTheme.cianIA),
                ),
            ],
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Text('Error: $_error', style: const TextStyle(color: AtlasTheme.rojoError, fontFamily: 'monospace')),
          ),
        Expanded(
          child: _isLoading
              ? const Center(child: CircularProgressIndicator(color: AtlasTheme.cianIA))
              : LayoutBuilder(
                  builder: (context, constraints) {
                    return CustomPaint(
                      painter: _GraphPainter(
                        nodes: _nodes,
                        edges: _edges,
                        centerNodeTitle: _activeCommunityTitle,
                        animationValue: _animationController.value,
                      ),
                      child: Stack(
                        children: _buildNodeWidgets(constraints),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }

  List<Widget> _buildNodeWidgets(BoxConstraints constraints) {
    final center = Offset(constraints.maxWidth / 2, constraints.maxHeight / 2);
    final radius = min(constraints.maxWidth, constraints.maxHeight) * 0.35;
    
    List<Widget> widgets = [];
    
    if (_activeCommunityTitle != null) {
      widgets.add(
        Positioned(
          left: center.dx - 60,
          top: center.dy - 60,
          width: 120,
          height: 120,
          child: GestureDetector(
            onTap: _loadCommunities,
            child: Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AtlasTheme.cianIA.withValues(alpha: 0.1),
                border: Border.all(color: AtlasTheme.cianIA, width: 2),
                boxShadow: [
                  BoxShadow(color: AtlasTheme.cianIA.withValues(alpha: 0.5), blurRadius: 20),
                ],
              ),
              alignment: Alignment.center,
              child: Text(
                'Core:\n$_activeCommunityTitle',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white, fontSize: 12, fontFamily: 'monospace'),
              ),
            ),
          ),
        ),
      );
    }
    
    final int count = _nodes.length;
    for (int i = 0; i < count; i++) {
      final node = _nodes[i];
      final angle = (2 * pi * i) / count;
      final x = center.dx + radius * cos(angle);
      final y = center.dy + radius * sin(angle);
      
      final title = node['title'] ?? 'Unknown';
      final path = node['path'] ?? '';
      
      widgets.add(
        Positioned(
          left: x - 40,
          top: y - 40,
          width: 80,
          height: 80,
          child: MouseRegion(
            cursor: SystemMouseCursors.click,
            child: GestureDetector(
              onTap: () {
                if (_activeCommunityPath == null) {
                  _loadNeighbors(path, title);
                } else {
                  // Reached a leaf node, normally opens document
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Open Document: $title')),
                  );
                }
              },
              child: AnimatedBuilder(
                animation: _animationController,
                builder: (context, child) {
                  final glowScale = 1.0 + (_animationController.value * 0.1);
                  return Transform.scale(
                    scale: glowScale,
                    child: Container(
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: AtlasTheme.surface.withValues(alpha: 0.9),
                        border: Border.all(color: AtlasTheme.verdeVerificado, width: 1),
                        boxShadow: [
                          BoxShadow(color: AtlasTheme.verdeVerificado.withValues(alpha: 0.3), blurRadius: 10),
                        ],
                      ),
                      alignment: Alignment.center,
                      child: Padding(
                        padding: const EdgeInsets.all(4.0),
                        child: Text(
                          title,
                          textAlign: TextAlign.center,
                          style: const TextStyle(fontSize: 10, color: Colors.white, fontFamily: 'monospace'),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ),
      );
    }
    
    return widgets;
  }
}

class _GraphPainter extends CustomPainter {
  final List<dynamic> nodes;
  final Map<String, List<dynamic>> edges;
  final String? centerNodeTitle;
  final double animationValue;

  _GraphPainter({
    required this.nodes,
    required this.edges,
    required this.centerNodeTitle,
    required this.animationValue,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = min(size.width, size.height) * 0.35;
    
    final paintLine = Paint()
      ..color = AtlasTheme.cianIA.withValues(alpha: 0.3 + (animationValue * 0.2))
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
      
    // Draw radar rings
    final ringPaint = Paint()
      ..color = AtlasTheme.cianIA.withValues(alpha: 0.05)
      ..strokeWidth = 1
      ..style = PaintingStyle.stroke;
      
    canvas.drawCircle(center, radius, ringPaint);
    canvas.drawCircle(center, radius * 0.6, ringPaint);
    canvas.drawCircle(center, radius * 0.3, ringPaint);
    
    // Draw edges from center to nodes
    if (centerNodeTitle != null) {
      final int count = nodes.length;
      for (int i = 0; i < count; i++) {
        final angle = (2 * pi * i) / count;
        final x = center.dx + radius * cos(angle);
        final y = center.dy + radius * sin(angle);
        
        final path = Path();
        path.moveTo(center.dx, center.dy);
        // Draw a slight curve
        final controlX = (center.dx + x) / 2 - 20;
        final controlY = (center.dy + y) / 2 + 20;
        path.quadraticBezierTo(controlX, controlY, x, y);
        
        canvas.drawPath(path, paintLine);
      }
    } else {
      // Connect neighbors in a ring if no center node
      final int count = nodes.length;
      if (count > 1) {
        for (int i = 0; i < count; i++) {
          final angle1 = (2 * pi * i) / count;
          final x1 = center.dx + radius * cos(angle1);
          final y1 = center.dy + radius * sin(angle1);
          
          final angle2 = (2 * pi * ((i + 1) % count)) / count;
          final x2 = center.dx + radius * cos(angle2);
          final y2 = center.dy + radius * sin(angle2);
          
          canvas.drawLine(Offset(x1, y1), Offset(x2, y2), paintLine);
        }
      }
    }
  }

  @override
  bool shouldRepaint(covariant _GraphPainter oldDelegate) {
    return oldDelegate.animationValue != animationValue ||
           oldDelegate.nodes != nodes ||
           oldDelegate.edges != edges ||
           oldDelegate.centerNodeTitle != centerNodeTitle;
  }
}
