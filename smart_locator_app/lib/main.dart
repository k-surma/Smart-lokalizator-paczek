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

void main() {
  runApp(const SmartLocatorApp());
}

class SmartLocatorApp extends StatelessWidget {
  const SmartLocatorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PUDO Smart Lokalizator',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.amber,
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}

class QrScannerPage extends StatefulWidget {
  final String title;
  const QrScannerPage({super.key, required this.title});

  @override
  State<QrScannerPage> createState() => _QrScannerPageState();
}

class _QrScannerPageState extends State<QrScannerPage> {
  bool _scanned = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
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
        backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
        duration: const Duration(seconds: 4),
      ),
    );
  }

  Future<String?> _scanCode(String title) async {
    return Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => QrScannerPage(title: title)),
    );
  }

  Future<void> _showAcceptDialog({required bool isOutbound}) async {
    final codeCtrl = TextEditingController();
    final macCtrl = TextEditingController();

    await showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(isOutbound
            ? "Przyjmij NADANIE od klienta"
            : "Przyjmij paczkę OD KURIERA"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: codeCtrl,
              decoration: InputDecoration(
                labelText: "Kod paczki / ID InPost",
                suffixIcon: IconButton(
                  icon: const Icon(Icons.qr_code_scanner),
                  onPressed: () async {
                    final scanned = await _scanCode("Skanuj etykietę InPost");
                    if (scanned != null) codeCtrl.text = scanned;
                  },
                ),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: macCtrl,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(
                labelText: "Adres MAC lokalizatora XIAO",
                hintText: "np. AA:BB:CC:DD:EE:FF",
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Anuluj")),
          FilledButton(
            onPressed: () async {
              final code = codeCtrl.text.trim();
              final mac = macCtrl.text.trim().toUpperCase();
              if (code.isEmpty || mac.isEmpty) {
                _showSnack("Wpisz kod paczki i adres MAC", isError: true);
                return;
              }
              Navigator.pop(ctx);
              await _submitAccept(code: code, mac: mac, isOutbound: isOutbound);
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
        if (!isOutbound && data["pickup_code"] != null) {
          _showPickupCodeDialog(data);
        } else {
          _showSnack("Nadana w punkcie: ${data['package_code']} (MAC: $mac)");
        }
      } else {
        final err = jsonDecode(resp.body)["detail"] ?? resp.body;
        _showSnack("Błąd: $err", isError: true);
      }
    } catch (e) {
      _showSnack("Błąd sieci: $e", isError: true);
    }
  }

  void _showPickupCodeDialog(Map<String, dynamic> pkg) {
    final phone = (pkg["recipient_phone"] ?? "").toString();
    final last4 = phone.length >= 4 ? phone.substring(phone.length - 4) : "brak";
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Status: Do odbioru w punkcie"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("Numer: ${pkg['package_code']}"),
            Text("Gabaryt: ${pkg['parcel_size'] ?? '-'}  |  MAC: ${pkg['mac_address']}"),
            const Divider(),
            Text("4 ostatnie cyfry tel.: $last4",
                style: const TextStyle(fontWeight: FontWeight.bold)),
            Text("Kod odbioru (PIN): ${pkg['pickup_code']}",
                style: const TextStyle(
                    fontSize: 22, fontWeight: FontWeight.bold, color: Colors.indigo)),
          ],
        ),
        actions: [
          FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text("OK")),
        ],
      ),
    );
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

  Future<void> _showClientVerifyDialog() async {
    final phone4Ctrl = TextEditingController();
    final qrCtrl = TextEditingController();
    final pinCtrl = TextEditingController();

    await showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Wydaj paczkę klientowi"),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: phone4Ctrl,
                keyboardType: TextInputType.number,
                maxLength: 4,
                decoration: const InputDecoration(
                  labelText: "4 ostatnie cyfry telefonu klienta",
                  hintText: "np. 0700",
                ),
              ),
              const Text("— LUB —", style: TextStyle(color: Colors.grey)),
              TextField(
                controller: qrCtrl,
                decoration: InputDecoration(
                  labelText: "Kod QR klienta",
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.qr_code_scanner),
                    onPressed: () async {
                      final scanned = await _scanCode("Skanuj QR klienta");
                      if (scanned != null) qrCtrl.text = scanned;
                    },
                  ),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: pinCtrl,
                keyboardType: TextInputType.number,
                maxLength: 6,
                decoration: const InputDecoration(
                  labelText: "6-cyfrowy kod odbioru (PIN)",
                  hintText: "np. 482910",
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Anuluj")),
          FilledButton(
            onPressed: () async {
              final pin = pinCtrl.text.trim();
              final last4 = phone4Ctrl.text.trim();
              final qr = qrCtrl.text.trim();
              if (pin.isEmpty || (last4.isEmpty && qr.isEmpty)) {
                _showSnack("Podaj PIN oraz 4 cyfry tel. lub QR", isError: true);
                return;
              }
              Navigator.pop(ctx);
              await _verifyClientAndLocate(pin: pin, phoneLast4: last4, qrCode: qr);
            },
            child: const Text("Znajdź i lokalizuj"),
          ),
        ],
      ),
    );
  }

  Future<void> _verifyClientAndLocate({
    required String pin,
    String? phoneLast4,
    String? qrCode,
  }) async {
    try {
      final resp = await http.post(
        Uri.parse("$apiBaseUrl/api/inpost/client-verify"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "pickup_code": pin,
          "phone_last4": (phoneLast4 != null && phoneLast4.isNotEmpty) ? phoneLast4 : null,
          "qr_code": (qrCode != null && qrCode.isNotEmpty) ? qrCode : null,
        }),
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

  void _openRadarSheet(Map<String, dynamic> pkg) {
    final mac = pkg["mac_address"]?.toString();
    if (mac == null || mac.isEmpty) {
      _showSnack("Ta paczka nie ma przypiętego tagu BLE", isError: true);
      return;
    }
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => BleRadarSheet(
        pkg: pkg,
        onFound: () async => _updateStatus(mac, "FOUND", battery: 95),
        onDeliver: () async => _markAsDelivered(pkg["id"]),
      ),
    ).then((_) => _fetchPackages());
  }

  String _formatPudoStatus(String? s) {
    switch (s) {
      case "dispatched_by_sender":
        return "Nadana w punkcie";
      case "ready_to_pickup":
        return "Do odbioru";
      case "collected_from_sender":
        return "Odebrana przez kuriera";
      case "delivered":
        return "Wydana klientowi";
      default:
        return "Do nadania";
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("PUDO Lokalizator (InPost + BLE)"),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _fetchPackages),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(10),
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(backgroundColor: Colors.indigo),
                        icon: const Icon(Icons.archive_outlined),
                        label: const Text("Nadanie\n(od klienta)", textAlign: TextAlign.center),
                        onPressed: () => _showAcceptDialog(isOutbound: true),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(backgroundColor: Colors.blueGrey),
                        icon: const Icon(Icons.local_shipping_outlined),
                        label: const Text("Wydaj kurierowi\n(QR)", textAlign: TextAlign.center),
                        onPressed: _courierPickupFlow,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(backgroundColor: Colors.teal),
                        icon: const Icon(Icons.move_to_inbox),
                        label: const Text("Przyjmij\nod kuriera", textAlign: TextAlign.center),
                        onPressed: () => _showAcceptDialog(isOutbound: false),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(backgroundColor: Colors.amber.shade800),
                        icon: const Icon(Icons.person_pin_circle_outlined),
                        label: const Text("Wydaj klientowi\n(PIN / QR)", textAlign: TextAlign.center),
                        onPressed: _showClientVerifyDialog,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _fetchPackages,
                    child: ListView.builder(
                      itemCount: _packages.length,
                      itemBuilder: (_, i) {
                        final p = _packages[i];
                        final isOutbound = p["direction"] == "OUTBOUND";
                        final status = p["status"] ?? "IDLE";
                        final isDelivered = status == "DELIVERED";
                        final mac = p["mac_address"];
                        final pin = p["pickup_code"];
                        final size = p["parcel_size"] ?? "-";
                        final pudoLabel = _formatPudoStatus(p["inpost_pudo_status"]);

                        return Card(
                          margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                          child: ListTile(
                            leading: CircleAvatar(
                              backgroundColor: isOutbound ? Colors.indigo : Colors.teal,
                              foregroundColor: Colors.white,
                              child: Text(isOutbound ? "NAD" : "ODB",
                                  style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                            ),
                            title: Text("${p['package_code']}",
                                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text("Gabaryt: $size  |  MAC: ${mac ?? 'zwolniony'}"),
                                if (pin != null)
                                  Text("PIN: $pin  |  Tel: ${p['recipient_phone'] ?? '-'}",
                                      style: const TextStyle(fontWeight: FontWeight.w600)),
                                Text("InPost PUDO: $pudoLabel  ($status)",
                                    style: TextStyle(
                                        color: isDelivered ? Colors.grey : Colors.deepOrange,
                                        fontWeight: FontWeight.bold)),
                              ],
                            ),
                            trailing: isDelivered
                                ? const Icon(Icons.check_circle, color: Colors.grey)
                                : IconButton(
                                    icon: const Icon(Icons.radar, color: Colors.deepOrange),
                                    onPressed: () async {
                                      if (mac != null) {
                                        await http.post(Uri.parse("$apiBaseUrl/api/locate/$mac"));
                                        _openRadarSheet(p);
                                      }
                                    },
                                  ),
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
  final Future<void> Function() onFound;
  final Future<void> Function() onDeliver;

  const BleRadarSheet({
    super.key,
    required this.pkg,
    required this.onFound,
    required this.onDeliver,
  });

  @override
  State<BleRadarSheet> createState() => _BleRadarSheetState();
}

class _BleRadarSheetState extends State<BleRadarSheet> {
  final List<int> _rssiWindow = [];
  static const int _windowSize = 10;
  double _threshold = -60.0;
  double? _filteredRssi;
  bool _triggered = false;
  StreamSubscription<List<ScanResult>>? _scanSub;

  String get _targetMac => (widget.pkg["mac_address"] ?? "").toString().toUpperCase();

  @override
  void initState() {
    super.initState();
    _startBleScan();
  }

  Future<void> _startBleScan() async {
    await FlutterBluePlus.stopScan();
    _scanSub = FlutterBluePlus.scanResults.listen((results) {
      for (final r in results) {
        if (r.device.remoteId.str.toUpperCase() == _targetMac) {
          _addRssiSample(r.rssi, r.device);
        }
      }
    });
    await FlutterBluePlus.startScan(
      timeout: const Duration(minutes: 3),
      androidScanMode: AndroidScanMode.lowLatency,
    );
  }

  void _addRssiSample(int rssi, BluetoothDevice device) {
    _rssiWindow.add(rssi);
    if (_rssiWindow.length > _windowSize) _rssiWindow.removeAt(0);

    double avg;
    if (_rssiWindow.length >= 4) {
      final sorted = List<int>.from(_rssiWindow)..sort();
      final trimmed = sorted.sublist(1, sorted.length - 1);
      avg = trimmed.reduce((a, b) => a + b) / trimmed.length;
    } else {
      avg = _rssiWindow.reduce((a, b) => a + b) / _rssiWindow.length;
    }

    if (mounted) setState(() => _filteredRssi = avg);

    if (!_triggered && avg >= _threshold) {
      _triggered = true;
      _triggerGattBuzzer(device);
      widget.onFound();
    }
  }

  Future<void> _triggerGattBuzzer(BluetoothDevice device) async {
    try {
      await device.connect(timeout: const Duration(seconds: 5));
      final services = await device.discoverServices();
      for (final s in services) {
        if (s.uuid.toString().toLowerCase() == gattServiceUuid) {
          for (final c in s.characteristics) {
            if (c.uuid.toString().toLowerCase() == gattBuzzerCharUuid) {
              await c.write([0x01]);
            }
          }
        }
      }
      await device.disconnect();
    } catch (_) {}
  }

  @override
  void dispose() {
    _scanSub?.cancel();
    FlutterBluePlus.stopScan();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isOutbound = widget.pkg["direction"] == "OUTBOUND";
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            isOutbound ? "Szukanie NADANIA dla kuriera" : "Szukanie paczki DLA KLIENTA",
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 6),
          Text("Kod: ${widget.pkg['package_code']}"),
          Text("Gabaryt: ${widget.pkg['parcel_size'] ?? '-'}  |  MAC: $_targetMac",
              style: const TextStyle(color: Colors.black54)),
          const SizedBox(height: 16),
          Text(
            _filteredRssi == null ? "Skanowanie BLE..." : "${_filteredRssi!.toStringAsFixed(1)} dBm",
            style: TextStyle(
              fontSize: 34,
              fontWeight: FontWeight.bold,
              color: _triggered ? Colors.green : Colors.deepOrange,
            ),
          ),
          if (_triggered)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text("ZNALEZIONO! Sygnał wysłany do lokalizatora.",
                  style: TextStyle(color: Colors.green, fontWeight: FontWeight.bold)),
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              const Text("Próg dBm:"),
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
              Text("${_threshold.round()}"),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: Colors.green.shade700,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              icon: const Icon(Icons.check_circle_outline),
              label: Text(
                isOutbound
                    ? "Potwierdź wydanie KURIEROWI (Odoo)"
                    : "Potwierdź wydanie KLIENTOWI (InPost + Odoo)",
              ),
              onPressed: () async {
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
