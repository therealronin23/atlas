// Atlas — T2.1 micro-PoC Flutter (t2-1-micropoc-flutter).
//
// Pantalla única de medición: shader de glow (dart:ui FragmentProgram),
// partículas orbitando (CustomPainter, patrón "OrbPainter" de
// docs/design/ui/research/research-flutter.md), contador de fps en vivo, y
// conexión WebSocket real contra el bridge de Atlas (127.0.0.1:7341/events,
// ADR-058). No es producto: es instrumentación para medir, ver
// docs/design/ui/research/DECISION_STACK_T21.md.

import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

void main() {
  runApp(const MicroPocApp());
}

class MicroPocApp extends StatelessWidget {
  const MicroPocApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Atlas T2.1 micro-PoC (Flutter)',
      theme: ThemeData.dark(useMaterial3: true),
      home: const MicroPocScreen(),
    );
  }
}

class MicroPocScreen extends StatefulWidget {
  const MicroPocScreen({super.key});

  @override
  State<MicroPocScreen> createState() => _MicroPocScreenState();
}

class _MicroPocScreenState extends State<MicroPocScreen>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  final Stopwatch _clock = Stopwatch()..start();
  double _timeSeconds = 0;

  ui.FragmentShader? _glowShader;
  String _shaderStatus = 'cargando...';

  final List<_Particle> _particles = List.generate(
    24,
    (i) => _Particle(seed: i),
  );

  // Contador de fps: media móvil sobre el último segundo real.
  final List<Duration> _frameTimestamps = [];
  double _fps = 0;

  WebSocketChannel? _wsChannel;
  String _wsStatus = 'sin conectar';
  int _wsEventCount = 0;
  StreamSubscription<dynamic>? _wsSub;

  Timer? _statsLogTimer;

  @override
  void initState() {
    super.initState();
    _loadShader();
    _connectWebSocket();
    _ticker = createTicker(_onTick)..start();
    // Log a stdout para medir sin capturar el display real (esta tarea es
    // instrumentación de medición, no una acción de Atlas sobre GUI).
    _statsLogTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      debugPrint(
        'MICROPOC_STATS fps=${_fps.toStringAsFixed(0)} '
        'shader=$_shaderStatus ws=$_wsStatus wsEvents=$_wsEventCount',
      );
    });
  }

  Future<void> _loadShader() async {
    try {
      final program = await ui.FragmentProgram.fromAsset('shaders/glow.frag');
      setState(() {
        _glowShader = program.fragmentShader();
        _shaderStatus = 'ok (dart:ui FragmentProgram)';
      });
    } catch (e) {
      setState(() {
        _shaderStatus = 'FALLO: $e';
      });
    }
  }

  void _connectWebSocket() {
    try {
      // El bridge (src/atlas/api/server.py:_validate_websocket_origin,
      // ADR-058) exige un header Origin que coincida con el Host o sea
      // loopback-a-loopback — protección tipo CSRF pensada para clientes
      // navegador. Un cliente nativo (Dart dart:io, o cualquier cliente WS
      // no-browser) no lo envía por defecto: hallazgo real de este
      // micro-PoC, no un bug de Flutter. IOWebSocketChannel sí permite
      // fijar headers a mano.
      final channel = IOWebSocketChannel.connect(
        Uri.parse('ws://127.0.0.1:7341/events'),
        headers: {'Origin': 'http://127.0.0.1:7341'},
      );
      _wsChannel = channel;
      setState(() => _wsStatus = 'conectando...');
      _wsSub = channel.stream.listen(
        (event) {
          setState(() {
            _wsStatus = 'conectado, evento recibido';
            _wsEventCount += 1;
          });
        },
        onError: (Object err) {
          setState(() => _wsStatus = 'error: $err');
        },
        onDone: () {
          setState(() => _wsStatus = 'cerrado por el servidor');
        },
      );
    } catch (e) {
      setState(() => _wsStatus = 'FALLO al conectar: $e');
    }
  }

  void _onTick(Duration elapsed) {
    _frameTimestamps.add(elapsed);
    while (_frameTimestamps.isNotEmpty &&
        elapsed - _frameTimestamps.first > const Duration(seconds: 1)) {
      _frameTimestamps.removeAt(0);
    }
    setState(() {
      _timeSeconds = _clock.elapsedMilliseconds / 1000.0;
      _fps = _frameTimestamps.length.toDouble();
      for (final p in _particles) {
        p.advance(_timeSeconds);
      }
    });
  }

  @override
  void dispose() {
    _ticker.dispose();
    _statsLogTimer?.cancel();
    _wsSub?.cancel();
    _wsChannel?.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF060B10),
      body: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _ParticlePainter(
                particles: _particles,
                timeSeconds: _timeSeconds,
              ),
            ),
          ),
          if (_glowShader != null)
            Center(
              child: SizedBox(
                width: 420,
                height: 420,
                child: CustomPaint(
                  painter: _ShaderGlowPainter(
                    shader: _glowShader!,
                    timeSeconds: _timeSeconds,
                  ),
                ),
              ),
            ),
          Positioned(
            top: 24,
            left: 24,
            child: _HudPanel(
              fps: _fps,
              shaderStatus: _shaderStatus,
              wsStatus: _wsStatus,
              wsEventCount: _wsEventCount,
            ),
          ),
        ],
      ),
    );
  }
}

class _HudPanel extends StatelessWidget {
  const _HudPanel({
    required this.fps,
    required this.shaderStatus,
    required this.wsStatus,
    required this.wsEventCount,
  });

  final double fps;
  final String shaderStatus;
  final String wsStatus;
  final int wsEventCount;

  @override
  Widget build(BuildContext context) {
    const style = TextStyle(
      color: Color(0xFF9EEFFF),
      fontFamily: 'monospace',
      fontSize: 14,
    );
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.55),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0x339EEFFF)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Atlas T2.1 micro-PoC — Flutter', style: style),
          Text('fps: ${fps.toStringAsFixed(0)}', style: style),
          Text('shader: $shaderStatus', style: style),
          Text('ws (127.0.0.1:7341/events): $wsStatus', style: style),
          Text('ws eventos recibidos: $wsEventCount', style: style),
        ],
      ),
    );
  }
}

class _ShaderGlowPainter extends CustomPainter {
  _ShaderGlowPainter({required this.shader, required this.timeSeconds});

  final ui.FragmentShader shader;
  final double timeSeconds;

  @override
  void paint(Canvas canvas, Size size) {
    shader
      ..setFloat(0, size.width)
      ..setFloat(1, size.height)
      ..setFloat(2, timeSeconds);
    canvas.drawRect(Offset.zero & size, Paint()..shader = shader);
  }

  @override
  bool shouldRepaint(covariant _ShaderGlowPainter oldDelegate) => true;
}

/// Partícula orbitando el centro — patrón "OrbPainter" documentado en
/// research-flutter.md (glow central + trigonometría), sin depender del
/// paquete particle_field para mantener el micro-PoC sin dependencias
/// adicionales de dibujo.
class _Particle {
  _Particle({required int seed})
      : radius = 90 + (seed * 13 % 140).toDouble(),
        angleOffset = seed * 0.61,
        speed = 0.4 + (seed % 5) * 0.08,
        size = 2.0 + (seed % 4).toDouble();

  final double radius;
  final double angleOffset;
  final double speed;
  final double size;
  Offset position = Offset.zero;

  void advance(double timeSeconds) {
    final angle = angleOffset + timeSeconds * speed;
    position = Offset(math.cos(angle), math.sin(angle)) * radius;
  }
}

class _ParticlePainter extends CustomPainter {
  _ParticlePainter({required this.particles, required this.timeSeconds});

  final List<_Particle> particles;
  final double timeSeconds;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final paint = Paint()
      ..color = const Color(0xFF6FE3FF)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3);
    for (final p in particles) {
      canvas.drawCircle(center + p.position, p.size, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _ParticlePainter oldDelegate) => true;
}
