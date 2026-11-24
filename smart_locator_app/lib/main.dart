import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:http/http.dart' as http;
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:permission_handler/permission_handler.dart';

const String apiBaseUrl = "http://63.187.131.29:8000";
const String gattServiceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214";
const String gattBuzzerCharUuid = "19b10001-e8f2-537e-4f6c-d104768a1214";
const String gattBatteryServiceUuid = "0000180f-0000-1000-8000-00805f9b34fb";
const String gattBatteryCharUuid = "00002a19-0000-1000-8000-00805f9b34fb";
const String gattCustomBatteryCharUuid = "19b10002-e8f2-537e-4f6c-d104768a1214";

/// Normalizuje adres MAC w dowolnym formacie (AABBCCDDEEFF, aa:bb:..., aa-bb-..., JSON)
/// do kanonicznego formatu AA:BB:CC:DD:EE:FF. Zwraca null, jeśli format jest błędny.
String? normalizeMacAddress(String raw) {
  var cleaned = raw.trim();
  if (cleaned.isEmpty) return null;

  if (cleaned.startsWith('{')) {
    try {
      final decoded = jsonDecode(cleaned);
      if (decoded is Map) {
        for (final key in ['mac_address', 'mac', 'address']) {
          final val = decoded[key]?.toString().trim();
          if (val != null && val.isNotEmpty) {
            cleaned = val;
            break;
          }
        }
      }
    } catch (_) {}
  }

  String? hexOnly;
  final sepMatch = RegExp(r'([0-9A-Fa-f]{2}(?:[:\-\s][0-9A-Fa-f]{2}){5})')
      .firstMatch(cleaned);
  if (sepMatch != null) {
    hexOnly = sepMatch.group(1)!.replaceAll(RegExp(r'[^0-9A-Fa-f]'), '').toUpperCase();
  } else {
    final plainMatch = RegExp(r'(?<![0-9A-Fa-f])([0-9A-Fa-f]{12})(?![0-9A-Fa-f])')
        .firstMatch(cleaned);
    if (plainMatch != null) {
      hexOnly = plainMatch.group(1)!.toUpperCase();
    }
  }

  if (hexOnly == null || hexOnly.length != 12) return null;
  return List.generate(6, (i) => hexOnly!.substring(i * 2, i * 2 + 2)).join(':');
}

void main() {
  runApp(const SmartLocatorApp());
}

class SmartLocatorApp extends StatelessWidget {
  const SmartLocatorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PUDO Lokalizator',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1F2937),
        scaffoldBackgroundColor: const Color(0xFFF8FAFC),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.white,
          foregroundColor: Color(0xFF111827),
          elevation: 0,
          scrolledUnderElevation: 0,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}

class QrScannerPage extends StatefulWidget {
  final String title;
  final bool allowManualInput;
  const QrScannerPage({
    super.key,
    required this.title,
    this.allowManualInput = true,
  });

  @override
  State<QrScannerPage> createState() => _QrScannerPageState();
}

class _QrScannerPageState extends State<QrScannerPage> {
  bool _scanned = false;

  Future<void> _openManualDialog() async {
    _scanned = true;
    final ctrl = TextEditingController();
    final manual = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Wpisz kod ręcznie"),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: "Numer przesyłki lub kod QR",
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Anuluj")),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, ctrl.text.trim()),
            child: const Text("Zatwierdź"),
          ),
        ],
      ),
    );
    if (!mounted) return;
    if (manual != null && manual.isNotEmpty) {
      Navigator.of(context).pop(manual);
    } else {
      _scanned = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.title),
        actions: [
          if (widget.allowManualInput)
            IconButton(
              icon: const Icon(Icons.keyboard),
              tooltip: "Wpisz ręcznie",
              onPressed: _openManualDialog,
            ),
        ],
      ),
      body: MobileScanner(
        onDetect: (BarcodeCapture capture) {
          if (_scanned) return;
          for (final barcode in capture.barcodes) {
            final value = barcode.rawValue;
            if (value != null && value.trim().isNotEmpty) {
              _scanned = true;
              Navigator.of(context).pop(value.trim());
              break;
            }
          }
        },
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<dynamic> _packages = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _requestPermissions();
    _fetchPackages();
  }

  Future<void> _requestPermissions() async {
    await [
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
      Permission.locationWhenInUse,
      Permission.camera,
    ].request();
  }

  Future<void> _fetchPackages() async {
    setState(() => _loading = true);
    try {
      final resp = await http.get(Uri.parse("$apiBaseUrl/api/packages"));
      if (resp.statusCode == 200) {
        setState(() => _packages = jsonDecode(resp.body));
      }
    } catch (e) {
      _showSnack("Błąd połączenia z serwerem: $e", isError: true);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        behavior: SnackBarBehavior.floating,
        backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
        duration: const Duration(seconds: 4),
      ),
    );
  }

  Future<String?> _scanCode(String title, {bool allowManualInput = true}) async {
    return Navigator.of(context).push<String>(
      MaterialPageRoute(
        builder: (_) => QrScannerPage(title: title, allowManualInput: allowManualInput),
      ),
    );
  }

  Future<void> _showAcceptDialog({required bool isOutbound}) async {
    final codeCtrl = TextEditingController();
    final macCtrl = TextEditingController();

    await showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(
          isOutbound ? "Przyjmij NADANIE od klienta" : "Przyjmij paczkę OD KURIERA",
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: codeCtrl,
              decoration: InputDecoration(
                labelText: "Kod paczki / ID InPost",
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.qr_code_scanner),
                  tooltip: "Skanuj etykietę paczki",
                  onPressed: () async {
                    final scanned = await _scanCode(
                      "Skanuj etykietę InPost",
                      allowManualInput: false,
                    );
                    if (scanned != null) codeCtrl.text = scanned;
                  },
                ),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: macCtrl,
              textCapitalization: TextCapitalization.characters,
              decoration: InputDecoration(
                labelText: "Adres MAC lokalizatora XIAO",
                hintText: "AABBCCDDEEFF lub AA:BB:CC:DD:EE:FF",
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.qr_code_scanner),
                  tooltip: "Skanuj QR lokalizatora",
                  onPressed: () async {
                    final scanned = await _scanCode(
                      "Skanuj QR lokalizatora (MAC)",
                      allowManualInput: false,
                    );
                    if (scanned != null) {
                      final normalized = normalizeMacAddress(scanned);
                      if (normalized != null) {
                        macCtrl.text = normalized;
                      } else {
                        macCtrl.text = scanned;
                        _showSnack(
                          "Zeskanowany QR nie zawiera poprawnego 12-znakowego MAC",
                          isError: true,
                        );
                      }
                    }
                  },
                ),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Anuluj")),
          FilledButton(
            onPressed: () async {
              final code = codeCtrl.text.trim();
              final normalizedMac = normalizeMacAddress(macCtrl.text);
              if (code.isEmpty) {
                _showSnack("Zeskanuj lub wpisz kod paczki", isError: true);
                return;
              }
              if (normalizedMac == null) {
                _showSnack(
                  "Nieprawidłowy MAC (wpisz 12 znaków hex, np. AABBCCDDEEFF)",
                  isError: true,
                );
                return;
              }
              Navigator.pop(ctx);
              await _submitAccept(code: code, mac: normalizedMac, isOutbound: isOutbound);
            },
            child: const Text("Sprawdź w InPost i połącz"),
          ),
        ],
      ),
    );
  }

  Future<void> _submitAccept({
    required String code,
    required String mac,
    required bool isOutbound,
  }) async {
    final endpoint = isOutbound
        ? "$apiBaseUrl/api/inpost/accept-outbound"
        : "$apiBaseUrl/api/inpost/accept-inbound";
    try {
      final resp = await http.post(
        Uri.parse(endpoint),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"code": code, "mac_address": mac}),
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        await _fetchPackages();
        final label = isOutbound ? "Nadana w punkcie" : "Przyjęta do odbioru";
        _showSnack("$label: ${data['package_code']}");
      } else {
        final err = jsonDecode(resp.body)["detail"] ?? resp.body;
        _showSnack("Błąd: $err", isError: true);
      }
    } catch (e) {
      _showSnack("Błąd sieci: $e", isError: true);
    }
  }

  Future<void> _courierPickupFlow() async {
    final qr = await _scanCode("Skanuj QR kuriera (Nadanie)");
    if (qr == null) return;
    try {
      final resp = await http.post(
        Uri.parse("$apiBaseUrl/api/inpost/courier-pickup"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"code": qr}),
      );
      if (resp.statusCode == 200) {
        final pkg = jsonDecode(resp.body);
        await _fetchPackages();
        _openRadarSheet(pkg);
      } else {
        final err = jsonDecode(resp.body)["detail"] ?? resp.body;
        _showSnack("Błąd: $err", isError: true);
      }
    } catch (e) {
      _showSnack("Błąd sieci: $e", isError: true);
    }
  }

  Future<void> _clientPickupFlow() async {
    final qr = await _scanCode("Skanuj QR klienta (Odbiór)");
    if (qr == null) return;
    try {
      final resp = await http.post(
        Uri.parse("$apiBaseUrl/api/inpost/client-verify"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"code": qr}),
      );
      if (resp.statusCode == 200) {
        final pkg = jsonDecode(resp.body);
        await _fetchPackages();
        _openRadarSheet(pkg);
      } else {
        final err = jsonDecode(resp.body)["detail"] ?? resp.body;
        _showSnack("Odmowa: $err", isError: true);
      }
    } catch (e) {
      _showSnack("Błąd sieci: $e", isError: true);
    }
  }

  Future<void> _markAsDelivered(int packageId) async {
    try {
      final resp = await http.post(Uri.parse("$apiBaseUrl/api/packages/$packageId/deliver"));
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        await _fetchPackages();
        _showSnack(data["inpost_sync_info"] ?? "Oznaczono jako wydaną!");
      } else {
        final err = jsonDecode(resp.body)["detail"] ?? resp.body;
        _showSnack("Błąd wydania: $err", isError: true);
      }
    } catch (e) {
      _showSnack("Błąd sieci: $e", isError: true);
    }
  }

  Future<void> _updateStatus(String mac, String status, {int? battery}) async {
    try {
      await http.patch(
        Uri.parse("$apiBaseUrl/api/packages/$mac/status"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"status": status, "battery_level": battery}),
      );
      await _fetchPackages();
    } catch (_) {}
  }

  Future<void> _updateBattery(String mac, int battery) async {
    try {
      await http.patch(
        Uri.parse("$apiBaseUrl/api/packages/$mac/battery"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"battery_level": battery}),
      );
      await _fetchPackages();
    } catch (_) {}
  }

  void _openRadarSheet(Map<String, dynamic> pkg) {
    final mac = pkg["mac_address"]?.toString();
    if (mac == null || mac.isEmpty) {
      _showSnack("Ta paczka nie ma przypiętego tagu BLE", isError: true);
      return;
    }
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => BleRadarSheet(
        pkg: pkg,
        onFound: (int? battery) async => _updateStatus(mac, "FOUND", battery: battery),
        onBatteryRead: (int battery) async => _updateBattery(mac, battery),
        onDeliver: () async => _markAsDelivered(pkg["id"]),
      ),
    ).then((_) => _fetchPackages());
  }

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onPressed,
  }) {
    return Expanded(
      child: FilledButton.icon(
        style: FilledButton.styleFrom(
          backgroundColor: color,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        icon: Icon(icon, size: 20),
        label: Text(
          label,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
        onPressed: onPressed,
      ),
    );
  }

  IconData _batteryIcon(int? level) {
    if (level == null) return Icons.battery_unknown;
    if (level >= 80) return Icons.battery_full;
    if (level >= 50) return Icons.battery_5_bar;
    if (level >= 25) return Icons.battery_3_bar;
    return Icons.battery_alert;
  }

  Color _batteryColor(int? level) {
    if (level == null) return Colors.grey;
    if (level >= 50) return Colors.green.shade700;
    if (level >= 20) return Colors.orange.shade700;
    return Colors.red.shade700;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          "PUDO Lokalizator",
          style: TextStyle(fontWeight: FontWeight.w700, fontSize: 19),
        ),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _fetchPackages),
        ],
      ),
      body: Column(
        children: [
          Container(
            color: Colors.white,
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
            child: Column(
              children: [
                Row(
                  children: [
                    _buildActionButton(
                      icon: Icons.archive_outlined,
                      label: "Nadanie\n(od klienta)",
                      color: const Color(0xFF334155),
                      onPressed: () => _showAcceptDialog(isOutbound: true),
                    ),
                    const SizedBox(width: 8),
                    _buildActionButton(
                      icon: Icons.local_shipping_outlined,
                      label: "Wydaj kurierowi\n(QR)",
                      color: const Color(0xFF475569),
                      onPressed: _courierPickupFlow,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    _buildActionButton(
                      icon: Icons.move_to_inbox,
                      label: "Przyjmij\nod kuriera",
                      color: const Color(0xFF0F766E),
                      onPressed: () => _showAcceptDialog(isOutbound: false),
                    ),
                    const SizedBox(width: 8),
                    _buildActionButton(
                      icon: Icons.qr_code_scanner,
                      label: "Wydaj klientowi\n(QR)",
                      color: const Color(0xFFD97706),
                      onPressed: _clientPickupFlow,
                    ),
                  ],
                ),
              ],
            ),
          ),
          const Divider(height: 1, color: Color(0xFFE2E8F0)),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _fetchPackages,
                    child: _packages.isEmpty
                        ? ListView(
                            children: const [
                              SizedBox(height: 80),
                              Center(
                                child: Text(
                                  "Brak paczek",
                                  style: TextStyle(color: Colors.grey, fontSize: 15),
                                ),
                              ),
                            ],
                          )
                        : ListView.separated(
                            padding: const EdgeInsets.all(12),
                            itemCount: _packages.length,
                            separatorBuilder: (_, __) => const SizedBox(height: 8),
                            itemBuilder: (_, i) {
                              final p = _packages[i];
                              final status = p["status"] ?? "IDLE";
                              final isDelivered = status == "DELIVERED";
                              final mac = p["mac_address"]?.toString();
                              final int? battery = p["battery_level"] is num
                                  ? (p["battery_level"] as num).toInt()
                                  : null;

                              return Material(
                                color: Colors.white,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                  side: const BorderSide(color: Color(0xFFE2E8F0)),
                                ),
                                child: ListTile(
                                  contentPadding:
                                      const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                                  title: Text(
                                    "${p['package_code']}",
                                    style: TextStyle(
                                      fontWeight: FontWeight.w600,
                                      fontSize: 14,
                                      color: isDelivered ? Colors.grey : const Color(0xFF111827),
                                    ),
                                  ),
                                  subtitle: Padding(
                                    padding: const EdgeInsets.only(top: 4),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(
                                          _batteryIcon(battery),
                                          size: 16,
                                          color: _batteryColor(battery),
                                        ),
                                        const SizedBox(width: 4),
                                        Text(
                                          battery != null ? "$battery%" : "-",
                                          style: TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w500,
                                            color: _batteryColor(battery),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  trailing: isDelivered
                                      ? const Icon(Icons.check_circle, color: Colors.grey)
                                      : IconButton(
                                          icon: const Icon(Icons.radar, color: Color(0xFFD97706)),
                                          onPressed: () async {
                                            if (mac != null && mac.isNotEmpty) {
                                              await http.post(
                                                  Uri.parse("$apiBaseUrl/api/locate/$mac"));
                                              _openRadarSheet(p);
                                            }
                                          },
                                        ),
                                  onTap: (!isDelivered && mac != null && mac.isNotEmpty)
                                      ? () async {
                                          await http
                                              .post(Uri.parse("$apiBaseUrl/api/locate/$mac"));
                                          _openRadarSheet(p);
                                        }
                                      : null,
                                ),
                              );
                            },
                          ),
                  ),
          ),
        ],
      ),
    );
  }
}

class BleRadarSheet extends StatefulWidget {
  final Map<String, dynamic> pkg;
  final Future<void> Function(int? battery) onFound;
  final Future<void> Function(int battery) onBatteryRead;
  final Future<void> Function() onDeliver;

  const BleRadarSheet({
    super.key,
    required this.pkg,
    required this.onFound,
    required this.onBatteryRead,
    required this.onDeliver,
  });

  @override
  State<BleRadarSheet> createState() => _BleRadarSheetState();
}

class _RssiSample {
  final DateTime timestamp;
  final int rssi;
  const _RssiSample(this.timestamp, this.rssi);
}

class _BleRadarSheetState extends State<BleRadarSheet> {
  final List<_RssiSample> _rssiBuffer = [];
  static const int _maxBufferSamples = 25;
  static const int _windowMs = 2000;
  static const int _minSamplesForTrigger = 5;
  static const Duration _uiRefreshInterval = Duration(milliseconds: 500);

  double _threshold = -60.0;
  double? _filteredRssi;
  int _averagedCount = 0;
  bool _alarmActive = false;
  bool _markedFound = false;
  bool _bleBusy = false;
  bool _disposed = false;
  int? _batteryLevel;
  BluetoothDevice? _foundDevice;
  StreamSubscription<List<ScanResult>>? _scanSub;
  Timer? _uiTimer;
  Timer? _scanWatchdog;

  String get _targetMac {
    final raw = (widget.pkg["mac_address"] ?? "").toString();
    return normalizeMacAddress(raw) ?? raw.toUpperCase();
  }

  @override
  void initState() {
    super.initState();
    _batteryLevel = widget.pkg["battery_level"] is num
        ? (widget.pkg["battery_level"] as num).toInt()
        : null;
    _initBleRadar();
  }

  Future<void> _initBleRadar() async {
    _scanSub = FlutterBluePlus.onScanResults.listen((results) {
      final now = DateTime.now();
      for (final r in results) {
        if (r.device.remoteId.str.toUpperCase() == _targetMac) {
          _foundDevice = r.device;
          _collectRssiSample(r.rssi, now);
        }
      }
    });

    try {
      await FlutterBluePlus.stopScan();
    } catch (_) {}
    await _startBleScan();

    _uiTimer = Timer.periodic(_uiRefreshInterval, (_) => _processRssiTick());

    _scanWatchdog = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!_disposed && !_bleBusy && !FlutterBluePlus.isScanningNow) {
        _startBleScan();
      }
    });
  }

  Future<void> _startBleScan() async {
    if (_disposed) return;
    try {
      await FlutterBluePlus.startScan(
        timeout: const Duration(minutes: 5),
        continuousUpdates: true,
        continuousDivisor: 1,
        androidScanMode: AndroidScanMode.lowLatency,
      );
    } catch (_) {}
  }

  void _collectRssiSample(int rssi, DateTime now) {
    if (rssi == 127 || rssi > 0 || rssi < -120) return;
    _rssiBuffer.add(_RssiSample(now, rssi));
    if (_rssiBuffer.length > _maxBufferSamples) {
      _rssiBuffer.removeAt(0);
    }
  }

  void _processRssiTick() {
    if (_disposed || !mounted) return;

    final now = DateTime.now();
    _rssiBuffer.removeWhere(
      (s) => now.difference(s.timestamp).inMilliseconds > _windowMs,
    );

    if (_rssiBuffer.isEmpty) {
      if (_averagedCount != 0) {
        setState(() => _averagedCount = 0);
      }
      return;
    }

    final sorted = _rssiBuffer.map((s) => s.rssi).toList()..sort();
    List<int> core;
    if (sorted.length >= 5) {
      final trim = (sorted.length * 0.2).floor().clamp(1, (sorted.length - 1) ~/ 2);
      core = sorted.sublist(trim, sorted.length - trim);
    } else if (sorted.length >= 3) {
      core = sorted.sublist(1, sorted.length - 1);
    } else {
      core = sorted;
    }

    final avg = core.reduce((a, b) => a + b) / core.length;
    final sampleCount = _rssiBuffer.length;

    setState(() {
      _filteredRssi = avg;
      _averagedCount = sampleCount;
    });

    if (!_alarmActive &&
        !_markedFound &&
        !_bleBusy &&
        _foundDevice != null &&
        sampleCount >= _minSamplesForTrigger &&
        avg >= _threshold) {
      _activateLocatorAlarm(_foundDevice!);
    }
  }

  Future<void> _activateLocatorAlarm(BluetoothDevice device) async {
    if (mounted) setState(() => _bleBusy = true);
    final battery = await _sendGattCommand(device, 0x01, readBattery: true);
    if (mounted) {
      setState(() {
        _alarmActive = true;
        _bleBusy = false;
        if (battery != null) _batteryLevel = battery;
      });
    }
    if (battery != null) {
      await widget.onBatteryRead(battery);
    }
  }

  Future<void> _stopAlarmAndMarkFound() async {
    if (_bleBusy) return;
    if (mounted) setState(() => _bleBusy = true);

    int? battery = _batteryLevel;
    if (_foundDevice != null) {
      final readBat = await _sendGattCommand(_foundDevice!, 0x00, readBattery: true);
      if (readBat != null) battery = readBat;
    }

    await widget.onFound(battery);
    if (mounted) {
      setState(() {
        _alarmActive = false;
        _markedFound = true;
        _bleBusy = false;
        if (battery != null) _batteryLevel = battery;
      });
    }
  }

  /// Wysyła komendę do lokalizatora (0x01 = ON, 0x00 = OFF), opcjonalnie czyta baterię
  /// i wznawia ciągłe skanowanie RSSI po rozłączeniu.
  Future<int?> _sendGattCommand(
    BluetoothDevice device,
    int commandByte, {
    bool readBattery = false,
  }) async {
    int? battery;
    try {
      await FlutterBluePlus.stopScan();
      await device.connect(license: License.free, timeout: const Duration(seconds: 5));
      final services = await device.discoverServices();
      for (final s in services) {
        final sUuid = s.uuid.toString().toLowerCase();
        if (sUuid == gattServiceUuid) {
          for (final c in s.characteristics) {
            final cUuid = c.uuid.toString().toLowerCase();
            if (cUuid == gattBuzzerCharUuid) {
              await c.write([commandByte]);
            } else if (readBattery && cUuid == gattCustomBatteryCharUuid) {
              final val = await c.read();
              if (val.isNotEmpty) battery = val.first.clamp(0, 100);
            }
          }
        } else if (readBattery && (sUuid == gattBatteryServiceUuid || sUuid == "180f")) {
          for (final c in s.characteristics) {
            final cUuid = c.uuid.toString().toLowerCase();
            if (cUuid == gattBatteryCharUuid || cUuid == "2a19") {
              final val = await c.read();
              if (val.isNotEmpty) battery = val.first.clamp(0, 100);
            }
          }
        }
      }
    } catch (_) {
    } finally {
      try {
        await device.disconnect();
      } catch (_) {}
      _rssiBuffer.clear();
      if (!_disposed && mounted) {
        await _startBleScan();
      }
    }
    return battery;
  }

  @override
  void dispose() {
    _disposed = true;
    _uiTimer?.cancel();
    _scanWatchdog?.cancel();
    _scanSub?.cancel();
    FlutterBluePlus.stopScan();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isOutbound = widget.pkg["direction"] == "OUTBOUND";
    final double signalProgress =
        _filteredRssi == null ? 0.0 : ((_filteredRssi! + 100.0) / 60.0).clamp(0.0, 1.0);

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 36,
            height: 4,
            margin: const EdgeInsets.only(bottom: 14),
            decoration: BoxDecoration(
              color: Colors.grey.shade300,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Text(
            "${widget.pkg['package_code']}",
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          Text(
            "Bateria: ${_batteryLevel != null ? '$_batteryLevel%' : '-'}",
            style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
          ),
          const SizedBox(height: 16),
          Text(
            _filteredRssi == null ? "Skanowanie BLE..." : "${_filteredRssi!.toStringAsFixed(1)} dBm",
            style: TextStyle(
              fontSize: 34,
              fontWeight: FontWeight.bold,
              color: _markedFound
                  ? Colors.green.shade700
                  : (_alarmActive ? Colors.amber.shade800 : const Color(0xFF1F2937)),
            ),
          ),
          if (_averagedCount > 0)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                "Średnia z $_averagedCount ramek (odświeżanie 0,5 s)",
                style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
              ),
            ),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: _filteredRssi == null ? null : signalProgress,
              minHeight: 8,
              backgroundColor: Colors.grey.shade200,
              color: _markedFound
                  ? Colors.green.shade700
                  : (_alarmActive ? Colors.amber.shade700 : Colors.blueGrey),
            ),
          ),
          if (_alarmActive)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                "Alarm aktywny (0x01)",
                style: TextStyle(color: Colors.deepOrange, fontWeight: FontWeight.w600),
              ),
            ),
          if (_markedFound)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                "Znaleziono — alarm wyłączony (FOUND)",
                style: TextStyle(color: Colors.green, fontWeight: FontWeight.w600),
              ),
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              const Text("Próg:"),
              Expanded(
                child: Slider(
                  min: -90,
                  max: -30,
                  divisions: 60,
                  value: _threshold,
                  label: "${_threshold.round()} dBm",
                  onChanged: (v) => setState(() => _threshold = v),
                ),
              ),
              Text("${_threshold.round()} dBm"),
            ],
          ),
          const SizedBox(height: 10),
          if (!_markedFound)
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: _alarmActive ? Colors.orange.shade800 : Colors.blueGrey,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                icon: _bleBusy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.notifications_off_outlined),
                label: Text(
                  _alarmActive
                      ? "Wyłącz lokalizator i oznacz jako ZNALEZIONO"
                      : "Oznacz jako ZNALEZIONO",
                ),
                onPressed: _bleBusy ? null : _stopAlarmAndMarkFound,
              ),
            ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.green.shade700,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              icon: const Icon(Icons.check_circle_outline),
              label: Text(
                isOutbound ? "Potwierdź wydanie KURIEROWI" : "Potwierdź wydanie KLIENTOWI",
              ),
              onPressed: () async {
                if (_alarmActive && _foundDevice != null) {
                  await _sendGattCommand(_foundDevice!, 0x00);
                }
                await widget.onDeliver();
                if (context.mounted) Navigator.pop(context);
              },
            ),
          ),
        ],
      ),
    );
  }
}
