/// Pantalla principal: las misiones REALES del bridge.
///
/// Prioriza lo que pide decisión humana, porque es lo único que la consola
/// puede desbloquear: el 2026-08-10 el runtime servía 293 misiones de las que
/// **6** estaban en `awaiting_human_approval` y 203 ya rechazadas. Una lista
/// plana de 293 entierra las 6 que importan.
library;

import 'package:flutter/material.dart';

import '../api/bridge_client.dart';
import '../models/mission.dart';
import '../theme.dart';
import '../widgets/piezas.dart' as piezas;
import 'mission_detail.dart';

class MissionsScreen extends StatefulWidget {
  const MissionsScreen({required this.client, super.key});

  final BridgeClient client;

  @override
  State<MissionsScreen> createState() => _MissionsScreenState();
}

class _MissionsScreenState extends State<MissionsScreen> {
  MissionsPage? _pagina;
  String? _error;
  bool _cargando = true;

  /// Filtro por estado. `null` = todos. Arranca en el estado que pide acción
  /// humana: es la razón de ser de esta pantalla.
  String? _estado = 'awaiting_human_approval';

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      // 500 y no 50: con 293 misiones vivas, un límite bajo recortaría en
      // silencio y los contadores de arriba (que vienen del servidor y cuentan
      // el total) no cuadrarían con la lista de abajo.
      final pagina = await widget.client.missions(limit: 500);
      if (!mounted) return;
      setState(() {
        _pagina = pagina;
        _cargando = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _cargando = false;
      });
    }
  }

  List<Mission> get _visibles {
    final todas = _pagina?.missions ?? const <Mission>[];
    if (_estado == null) return todas;
    return todas.where((m) => m.state == _estado).toList();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return piezas.PanelDeError(mensaje: _error!, onReintentar: _cargar);
    }
    if (_cargando && _pagina == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final pagina = _pagina!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Cabecera(pagina: pagina, onRecargar: _cargar, cargando: _cargando),
        _Contadores(
          pagina: pagina,
          seleccionado: _estado,
          onSeleccionar: (estado) => setState(() => _estado = estado),
        ),
        const Divider(height: 1),
        Expanded(child: _Lista(misiones: _visibles, client: widget.client)),
      ],
    );
  }
}

class _Cabecera extends StatelessWidget {
  const _Cabecera({
    required this.pagina,
    required this.onRecargar,
    required this.cargando,
  });

  final MissionsPage pagina;
  final VoidCallback onRecargar;
  final bool cargando;

  @override
  Widget build(BuildContext context) {
    final esperando = pagina.byState['awaiting_human_approval'] ?? 0;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 10),
      child: Row(
        children: [
          Text('${pagina.total} misiones',
              style: const TextStyle(
                  fontSize: 20, fontWeight: FontWeight.w600, color: kTexto)),
          const SizedBox(width: 12),
          if (esperando > 0)
            piezas.Chip('$esperando esperando decisión',
                color: kEsperando, icono: Icons.pan_tool_alt),
          const Spacer(),
          IconButton(
            onPressed: cargando ? null : onRecargar,
            icon: cargando
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
            tooltip: 'Recargar desde el bridge',
          ),
        ],
      ),
    );
  }
}

class _Contadores extends StatelessWidget {
  const _Contadores({
    required this.pagina,
    required this.seleccionado,
    required this.onSeleccionar,
  });

  final MissionsPage pagina;
  final String? seleccionado;
  final ValueChanged<String?> onSeleccionar;

  @override
  Widget build(BuildContext context) {
    // Orden fijo y por relevancia operativa, no alfabético ni por volumen: lo
    // que pide decisión va primero aunque sean 6 contra 203 rechazadas.
    const orden = [
      'awaiting_human_approval',
      'plan_proposed',
      'failed',
      'applied',
      'rejected',
    ];
    final estados = [
      ...orden.where(pagina.byState.containsKey),
      ...pagina.byState.keys.where((k) => !orden.contains(k)),
    ];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 14),
      child: Row(
        children: [
          piezas.Contador(
            etiqueta: 'todas',
            valor: pagina.total,
            color: kNeutro,
            activo: seleccionado == null,
            onTap: () => onSeleccionar(null),
          ),
          const SizedBox(width: 8),
          for (final estado in estados) ...[
            piezas.Contador(
              etiqueta: estado.replaceAll('_', ' '),
              valor: pagina.byState[estado] ?? 0,
              color: colorDeEstado(estado),
              activo: seleccionado == estado,
              onTap: () => onSeleccionar(estado),
            ),
            const SizedBox(width: 8),
          ],
        ],
      ),
    );
  }
}

class _Lista extends StatelessWidget {
  const _Lista({required this.misiones, required this.client});

  final List<Mission> misiones;
  final BridgeClient client;

  @override
  Widget build(BuildContext context) {
    if (misiones.isEmpty) {
      return const Center(
        child: Text('Ninguna misión en este estado.',
            style: TextStyle(color: kTextoTenue)),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 6),
      itemCount: misiones.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, i) => _Fila(mision: misiones[i], client: client),
    );
  }
}

class _Fila extends StatelessWidget {
  const _Fila({required this.mision, required this.client});

  final Mission mision;
  final BridgeClient client;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => MissionDetailScreen(
            missionId: mision.id,
            client: client,
          ),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 3,
              height: 34,
              margin: const EdgeInsets.only(right: 12, top: 2),
              color: colorDeEstado(mision.state),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    mision.intent,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: kTexto, fontSize: 13.5),
                  ),
                  const SizedBox(height: 6),
                  Wrap(spacing: 6, runSpacing: 4, children: [
                    piezas.Chip(mision.state.replaceAll('_', ' '),
                        color: colorDeEstado(mision.state)),
                    piezas.Chip(mision.risk, color: colorDeRiesgo(mision.risk)),
                    piezas.Chip(mision.origin, color: kNeutro),
                    if (mision.humanActionRequired)
                      piezas.Chip('acción humana',
                          color: kEsperando, icono: Icons.pan_tool_alt),
                  ]),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Text(
              mision.id,
              style: const TextStyle(
                  color: kTextoTenue, fontSize: 11, fontFamily: 'monospace'),
            ),
          ],
        ),
      ),
    );
  }
}
