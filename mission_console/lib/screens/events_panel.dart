/// Panel lateral con el stream vivo de `WS /events`.
///
/// El bridge reenvía los últimos 50 eventos al conectar y luego empuja los
/// nuevos, así que el panel arranca con contexto en vez de con un vacío que
/// parece una desconexión.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../api/bridge_client.dart';
import '../models/mission.dart';
import '../theme.dart';

class EventsPanel extends StatefulWidget {
  const EventsPanel({required this.client, super.key});

  final BridgeClient client;

  @override
  State<EventsPanel> createState() => _EventsPanelState();
}

class _EventsPanelState extends State<EventsPanel> {
  final List<OsEvent> _eventos = [];
  StreamSubscription<OsEvent>? _sub;
  String? _error;

  /// Tope de eventos en memoria. El stream es indefinido: sin techo, una sesión
  /// larga acaba con la lista entera del día en RAM y el scroll inservible.
  static const int _maximo = 300;

  @override
  void initState() {
    super.initState();
    _conectar();
  }

  void _conectar() {
    setState(() => _error = null);
    _sub?.cancel();
    _sub = widget.client.events().listen(
      (evento) {
        if (!mounted) return;
        setState(() {
          _eventos.insert(0, evento);
          if (_eventos.length > _maximo) _eventos.removeLast();
        });
      },
      onError: (Object e) {
        if (!mounted) return;
        setState(() => _error = '$e');
      },
      onDone: () {
        if (!mounted) return;
        setState(() => _error = 'el bridge cerró el stream de eventos');
      },
    );
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 340,
      decoration: const BoxDecoration(
        color: kPanel,
        border: Border(left: BorderSide(color: kBorde)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 12, 10),
            child: Row(children: [
              Icon(Icons.circle,
                  size: 9, color: _error == null ? kAplicado : kFallido),
              const SizedBox(width: 8),
              const Text('Eventos del OS',
                  style: TextStyle(
                      fontSize: 13, fontWeight: FontWeight.w600, color: kTexto)),
              const Spacer(),
              Text('${_eventos.length}',
                  style: const TextStyle(color: kTextoTenue, fontSize: 11)),
            ]),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(_error!,
                    style: const TextStyle(color: kFallido, fontSize: 11)),
                const SizedBox(height: 6),
                TextButton(
                    onPressed: _conectar, child: const Text('Reconectar')),
              ]),
            ),
          const Divider(height: 1),
          Expanded(
            child: _eventos.isEmpty
                ? const Center(
                    child: Text('Sin eventos todavía.',
                        style: TextStyle(color: kTextoTenue, fontSize: 12)))
                : ListView.builder(
                    itemCount: _eventos.length,
                    itemBuilder: (_, i) => _Evento(evento: _eventos[i]),
                  ),
          ),
        ],
      ),
    );
  }
}

class _Evento extends StatelessWidget {
  const _Evento({required this.evento});

  final OsEvent evento;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(evento.kind,
              style: const TextStyle(
                  color: kPropuesto, fontSize: 12, fontFamily: 'monospace')),
          if (evento.at.isNotEmpty)
            Text(evento.at,
                style: const TextStyle(color: kTextoTenue, fontSize: 10)),
        ],
      ),
    );
  }
}
