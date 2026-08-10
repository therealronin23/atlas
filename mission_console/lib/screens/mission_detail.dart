/// Detalle de una misión: evidencia, siguiente acción y la decisión humana.
///
/// `POST /missions/{id}/approve` y `/reject` cambian el estado del runtime REAL
/// del operador. Por eso van detrás de una confirmación que dice el id y lo que
/// va a pasar: un botón de aprobar a un clic, en una lista donde se navega
/// rápido, es un accidente esperando fecha.
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../api/bridge_client.dart';
import '../models/mission.dart';
import '../theme.dart';
import '../widgets/piezas.dart' as piezas;

class MissionDetailScreen extends StatefulWidget {
  const MissionDetailScreen({
    required this.missionId,
    required this.client,
    super.key,
  });

  final String missionId;
  final BridgeClient client;

  @override
  State<MissionDetailScreen> createState() => _MissionDetailScreenState();
}

class _MissionDetailScreenState extends State<MissionDetailScreen> {
  Mission? _mision;
  Map<String, dynamic>? _receipt;
  String? _error;
  bool _cargando = true;
  bool _enviando = false;

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
      final json = await widget.client.missionDetail(widget.missionId);
      final bruta = json['mission'];
      if (!mounted) return;
      setState(() {
        _mision = bruta is Map<String, dynamic> ? Mission.fromJson(bruta) : null;
        _receipt = json['receipt'] is Map<String, dynamic>
            ? json['receipt'] as Map<String, dynamic>
            : null;
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

  Future<void> _decidir({required bool aprobar}) async {
    final mision = _mision;
    if (mision == null) return;
    final confirmado = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: kPanel,
        title: Text(aprobar ? '¿Aprobar la misión?' : '¿Rechazar la misión?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(mision.id,
                style: const TextStyle(
                    fontFamily: 'monospace', fontSize: 12, color: kTextoTenue)),
            const SizedBox(height: 10),
            Text(mision.intent, style: const TextStyle(fontSize: 13)),
            const SizedBox(height: 14),
            Text(
              aprobar
                  ? 'Escribe la decisión en el runtime real. No se deshace desde aquí.'
                  : 'Marca la misión como rechazada en el runtime real.',
              style: const TextStyle(color: kEsperando, fontSize: 12),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(aprobar ? 'Aprobar' : 'Rechazar'),
          ),
        ],
      ),
    );
    if (confirmado != true) return;

    setState(() => _enviando = true);
    try {
      aprobar
          ? await widget.client.approve(mision.id)
          : await widget.client.reject(mision.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(aprobar ? 'Misión aprobada' : 'Misión rechazada'),
      ));
      await _cargar();
    } catch (e) {
      if (!mounted) return;
      // El error del bridge se enseña ENTERO. Un "no se pudo aprobar" sin el
      // motivo obliga a ir al log del servidor, que es justo lo que esta
      // consola existe para evitar.
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$e'), backgroundColor: kFallido),
      );
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.missionId,
            style: const TextStyle(fontFamily: 'monospace', fontSize: 14)),
        backgroundColor: kPanel,
      ),
      body: _cuerpo(),
    );
  }

  Widget _cuerpo() {
    if (_error != null) {
      return piezas.PanelDeError(mensaje: _error!, onReintentar: _cargar);
    }
    if (_cargando) return const Center(child: CircularProgressIndicator());
    final mision = _mision;
    if (mision == null) {
      return const Center(
        child: Text('El bridge no devolvió la misión.',
            style: TextStyle(color: kTextoTenue)),
      );
    }
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(mision.intent,
            style: const TextStyle(fontSize: 16, height: 1.45, color: kTexto)),
        const SizedBox(height: 14),
        Wrap(spacing: 6, runSpacing: 6, children: [
          piezas.Chip(mision.state.replaceAll('_', ' '),
              color: colorDeEstado(mision.state)),
          piezas.Chip('riesgo ${mision.risk}',
              color: colorDeRiesgo(mision.risk)),
          piezas.Chip(mision.origin, color: kNeutro),
        ]),
        const SizedBox(height: 20),
        if (mision.esperandoAprobacion) _acciones(),
        _seccion('Siguiente acción', mision.nextCommand,
            monoespaciado: true, vacio: 'la misión no propone comando'),
        _seccionLista('Artefactos', mision.artifacts),
        _seccionJson('Evidencia', mision.evidenceBundle),
        _seccionJson('Gate', mision.gate),
        _seccionJson('Receipt', _receipt),
        _seccion('Creada', mision.createdAt),
        _seccion('Actualizada', mision.updatedAt),
      ],
    );
  }

  Widget _acciones() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 22),
      child: Row(children: [
        FilledButton.icon(
          onPressed: _enviando ? null : () => _decidir(aprobar: true),
          icon: const Icon(Icons.check, size: 18),
          label: const Text('Aprobar'),
          style: FilledButton.styleFrom(backgroundColor: kAplicado),
        ),
        const SizedBox(width: 10),
        OutlinedButton.icon(
          onPressed: _enviando ? null : () => _decidir(aprobar: false),
          icon: const Icon(Icons.close, size: 18),
          label: const Text('Rechazar'),
        ),
        if (_enviando) ...[
          const SizedBox(width: 14),
          const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2)),
        ],
      ]),
    );
  }

  Widget _seccion(String titulo, String? valor,
      {bool monoespaciado = false, String vacio = '—'}) {
    return _marco(
      titulo,
      SelectableText(
        (valor == null || valor.isEmpty) ? vacio : valor,
        style: TextStyle(
          color: (valor == null || valor.isEmpty) ? kTextoTenue : kTexto,
          fontSize: 12.5,
          height: 1.5,
          fontFamily: monoespaciado ? 'monospace' : null,
        ),
      ),
    );
  }

  Widget _seccionLista(String titulo, List<String> valores) {
    if (valores.isEmpty) return const SizedBox.shrink();
    return _marco(
      titulo,
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final v in valores)
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: SelectableText('• $v',
                  style: const TextStyle(
                      fontSize: 12.5, fontFamily: 'monospace', color: kTexto)),
            ),
        ],
      ),
    );
  }

  Widget _seccionJson(String titulo, Map<String, dynamic>? valor) {
    if (valor == null || valor.isEmpty) return const SizedBox.shrink();
    const codificador = JsonEncoder.withIndent('  ');
    String texto;
    try {
      texto = codificador.convert(valor);
    } catch (_) {
      // Un payload con tipos no serializables no puede dejar la pantalla en
      // blanco: se enseña la representación cruda.
      texto = '$valor';
    }
    return _marco(
      titulo,
      SelectableText(texto,
          style: const TextStyle(
              fontSize: 11.5,
              fontFamily: 'monospace',
              color: kTextoTenue,
              height: 1.45)),
    );
  }

  Widget _marco(String titulo, Widget hijo) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: kPanel,
        border: Border.all(color: kBorde),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(titulo.toUpperCase(),
              style: const TextStyle(
                  color: kTextoTenue,
                  fontSize: 10.5,
                  letterSpacing: 1.1,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          hijo,
        ],
      ),
    );
  }
}
