import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:permission_handler/permission_handler.dart';

void main() {
  runApp(const SmartParcelApp());
}

class SmartParcelApp extends StatelessWidget {
  const SmartParcelApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Smart Lokalizator Paczek',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      home: const PackageListScreen(),
    );
  }
}

class PackageListScreen extends StatefulWidget {
  const PackageListScreen({super.key});

  @override
  State<PackageListScreen> createState() => _PackageListScreenState();
}

class _PackageListScreenState extends State<PackageListScreen> {
  // STAŁE ELASTIC IP INSTANCJI AWS EC2:
  String awsBaseUrl = "http://63.187.131.29:8000";

  List<dynamic> packages = [];
  bool isLoading = false;
  String? errorMessage;

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
      Permission.location,
    ].request();
  }

  // 1. POBIERANIE LISTY PACZEK Z AWS (GET /api/packages)
  Future<void> _fetchPackages() async {
    setState(() {
      isLoading = true;
      errorMessage = null;
    });

    try {
      final response = await http
          .get(Uri.parse('$awsBaseUrl/api/packages'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        setState(() {
          packages = jsonDecode(response.body);
        });
      } else {
        setState(() {
          errorMessage = "Błąd serwera: HTTP ${response.statusCode}";
        });
      }
    } catch (e) {
      setState(() {
        errorMessage =
            "Brak połączenia z $awsBaseUrl.\nUpewnij się, że kontenery na AWS działają, a port 8000 jest otwarty.\n\nSzczegóły: $e";
      });
    } finally {
      setState(() {
        isLoading = false;
      });
    }
  }

  // 2. REJESTRACJA NOWEJ PACZKI (POST /api/packages/register)
  Future<void> _registerPackage(String code, String mac) async {
    try {
      final response = await http.post(
        Uri.parse('$awsBaseUrl/api/packages/register'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "package_code": code.trim(),
          "mac_address": mac.trim().toUpperCase(),
        }),
      );

      if (response.statusCode == 200) {
        _fetchPackages();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Dodano paczkę $code')),
          );
        }
      } else {
        throw Exception(response.body);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Błąd rejestracji: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  // 3. ZMIANA STATUSU NA "LOCATING" (POST /api/locate/{mac})
  Future<void> _setLocatingStatus(String mac) async {
    try {
      await http.post(Uri.parse('$awsBaseUrl/api/locate/$mac'));
      _fetchPackages();
    } catch (_) {}
  }

  // 4. AKTUALIZACJA STATUSU NA "FOUND" LUB "IDLE" (PATCH /api/packages/{mac}/status)
  Future<void> _updateStatus(String mac, String newStatus, {int? battery}) async {
    try {
      await http.patch(
        Uri.parse('$awsBaseUrl/api/packages/$mac/status'),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "status": newStatus,
          if (battery != null) "battery_level": battery,
        }),
      );
      _fetchPackages();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Błąd aktualizacji statusu: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  // Okienko zmiany adresu IP serwera AWS
  void _showServerSettingsDialog() {
    final controller = TextEditingController(text: awsBaseUrl);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Adres serwera AWS"),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: "URL FastAPI (z portem 8000)",
            hintText: "http://63.187.131.29:8000",
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text("Anuluj"),
          ),
          ElevatedButton(
            onPressed: () {
              setState(() {
                awsBaseUrl = controller.text.trim().replaceAll(RegExp(r'/$'), '');
              });
              Navigator.pop(ctx);
              _fetchPackages();
            },
            child: const Text("Zapisz i połącz"),
          ),
        ],
      ),
    );
  }

  // Okienko dodawania nowej paczki
  void _showAddPackageDialog() {
    final codeCtrl = TextEditingController(text: "PKG-2026-00${packages.length + 1}");
    final macCtrl = TextEditingController(text: "AA:BB:CC:DD:EE:0${packages.length + 1}");
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Zarejestruj paczkę"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: codeCtrl,
              decoration: const InputDecoration(
                labelText: "Kod paczki (np. PKG-2026-002)",
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: macCtrl,
              decoration: const InputDecoration(
                labelText: "Adres MAC urządzenia BLE",
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text("Anuluj"),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              _registerPackage(codeCtrl.text, macCtrl.text);
            },
            child: const Text("Dodaj do bazy"),
          ),
        ],
      ),
    );
  }

  // Otwarcie ekranu Radaru BLE dla wybranej paczki
  void _openRadarSheet(Map<String, dynamic> pkg) async {
    final String mac = pkg['mac_address'];
    await _setLocatingStatus(mac);

    if (!mounted) return;
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => RadarScannerSheet(
        packageCode: pkg['package_code'],
        targetMac: mac,
        onFound: () async {
          await _updateStatus(mac, "FOUND", battery: 95);
        },
        onResetIdle: () async {
          await _updateStatus(mac, "IDLE");
        },
      ),
    );
    _fetchPackages();
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'FOUND':
        return Colors.green;
      case 'LOCATING':
        return Colors.orange;
      default:
        return Colors.blueGrey;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Magazyn BLE (63.187.131.29)"),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: "Odśwież listę",
            onPressed: _fetchPackages,
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: "Ustawienia IP AWS",
            onPressed: _showServerSettingsDialog,
          ),
        ],
      ),
      body: isLoading
          ? const Center(child: CircularProgressIndicator())
          : errorMessage != null
              ? Padding(
                  padding: const EdgeInsets.all(24.0),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.cloud_off, size: 64, color: Colors.redAccent),
                      const SizedBox(height: 16),
                      Text(errorMessage!, textAlign: TextAlign.center),
                      const SizedBox(height: 20),
                      ElevatedButton.icon(
                        onPressed: _fetchPackages,
                        icon: const Icon(Icons.refresh),
                        label: const Text("Spróbuj ponownie"),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _fetchPackages,
                  child: packages.isEmpty
                      ? const Center(child: Text("Brak paczek w bazie."))
                      : ListView.builder(
                          padding: const EdgeInsets.all(12),
                          itemCount: packages.length,
                          itemBuilder: (ctx, i) {
                            final pkg = packages[i];
                            final status = pkg['status'] ?? 'IDLE';
                            return Card(
                              elevation: 2,
                              margin: const EdgeInsets.symmetric(vertical: 6),
                              child: ListTile(
                                leading: CircleAvatar(
                                  backgroundColor: _getStatusColor(status),
                                  child: const Icon(Icons.inventory_2, color: Colors.white),
                                ),
                                title: Text(
                                  pkg['package_code'] ?? 'Brak kodu',
                                  style: const TextStyle(fontWeight: FontWeight.bold),
                                ),
                                subtitle: Text(
                                  "MAC: ${pkg['mac_address']}\nBateria: ${pkg['battery_level']}% | Status: $status",
                                ),
                                isThreeLine: true,
                                trailing: FilledButton.icon(
                                  onPressed: () => _openRadarSheet(pkg),
                                  icon: const Icon(Icons.radar),
                                  label: const Text("Lokalizuj"),
                                ),
                              ),
                            );
                          },
                        ),
                ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showAddPackageDialog,
        icon: const Icon(Icons.add),
        label: const Text("Nowa paczka"),
      ),
    );
  }
}

// ============================================================================
// KOMPONENT RADARU BLE: CIĄGŁE SKANOWANIE + FILTR WIELODROGOWOŚCI (UŚREDNIANIE)
// ============================================================================
class RadarScannerSheet extends StatefulWidget {
  final String packageCode;
  final String targetMac;
  final Future<void> Function() onFound;
  final Future<void> Function() onResetIdle;

  const RadarScannerSheet({
    super.key,
    required this.packageCode,
    required this.targetMac,
    required this.onFound,
    required this.onResetIdle,
  });

  @override
  State<RadarScannerSheet> createState() => _RadarScannerSheetState();
}

class _RadarScannerSheetState extends State<RadarScannerSheet> {
  StreamSubscription<List<ScanResult>>? _scanSub;

  // Bufor próbek RSSI do filtracji wielodrogowości
  final List<int> _rssiBuffer = [];
  int _windowSize = 10; // Liczba próbek w oknie uśredniania (regulowana suwakiem)

  int? _rawRssi; // Ostatni surowy odczyt z radia
  double? _smoothedRssi; // Uśredniony odczyt po odrzuceniu skrajnych pików

  double rssiThreshold = -55; // Próg zaliczenia znalezienia paczki
  bool _foundSentToServer = false; // Czy wysłano już status FOUND do AWS
  String statusLog = "Ciągłe skanowanie pasma BLE...";

  @override
  void initState() {
    super.initState();
    _startContinuousBleScan();
  }

  // Algorytm: Średnia krocząca obcięta (Trimmed Moving Average)
  // Odrzuca skrajny najwyższy pik (odbicie fali) i najniższy spadek, uśredniając resztę
  double _computeFilteredRssi(int newSample) {
    _rssiBuffer.add(newSample);
    while (_rssiBuffer.length > _windowSize) {
      _rssiBuffer.removeAt(0);
    }

    if (_rssiBuffer.length < 5) {
      // Przy małej liczbie próbek liczona jest zwykła średnia arytmetyczna
      final sum = _rssiBuffer.reduce((a, b) => a + b);
      return sum / _rssiBuffer.length;
    }

    // Kopiujemy i sortujemy bufor, aby odciąć skrajny pik min i max
    final sorted = List<int>.from(_rssiBuffer)..sort();
    final trimmed = sorted.sublist(1, sorted.length - 1);
    final sum = trimmed.reduce((a, b) => a + b);
    return sum / trimmed.length;
  }

  Future<void> _startContinuousBleScan() async {
    try {
      await FlutterBluePlus.startScan(
        androidScanMode: AndroidScanMode.lowLatency,
        continuousUpdates: true,
      );

      _scanSub = FlutterBluePlus.scanResults.listen((results) async {
        for (ScanResult r in results) {
          // Podgląd wszystkich urządzeń w konsoli CMD (ułatwia szukanie MAC)
          debugPrint(
            "BLE: ${r.device.remoteId.str} | Nazwa: ${r.advertisementData.advName} | Raw RSSI: ${r.rssi} dBm",
          );

          if (r.device.remoteId.str.toUpperCase() == widget.targetMac.toUpperCase()) {
            final filtered = _computeFilteredRssi(r.rssi);

            if (mounted) {
              setState(() {
                _rawRssi = r.rssi;
                _smoothedRssi = filtered;
                statusLog =
                    "Skaner aktywny (bufor: ${_rssiBuffer.length}/$_windowSize próbek)";
              });
            }

            // Jeśli uśredniony sygnał przekroczy próg, aktualizujemy status w AWS,
            // ALE NIE ZATRZYMUJEMY SKANERA!
            if (filtered >= rssiThreshold && !_foundSentToServer) {
              _foundSentToServer = true;
              await widget.onFound();
              if (mounted) {
                setState(() {
                  statusLog =
                      "Próg osiągnięty! Wysłano FOUND do AWS (skaner działa dalej)";
                });
              }
            }
          }
        }
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          statusLog = "Błąd skanera BLE: $e";
        });
      }
    }
  }

  void _clearBuffer() {
    setState(() {
      _rssiBuffer.clear();
      _rawRssi = null;
      _smoothedRssi = null;
      _foundSentToServer = false;
      statusLog = "Bufor wyczyszczony – zbieranie nowych próbek...";
    });
  }

  @override
  void dispose() {
    // Skaner wyłącza się dopiero w momencie zamknięcia okna radaru
    FlutterBluePlus.stopScan();
    _scanSub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    double proximityProgress = 0.0;
    if (_smoothedRssi != null) {
      proximityProgress = ((_smoothedRssi! + 100) / 60).clamp(0.0, 1.0);
    }

    final bool isAboveThreshold =
        _smoothedRssi != null && _smoothedRssi! >= rssiThreshold;

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            "Radar: ${widget.packageCode}",
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          Text("Szukany MAC: ${widget.targetMac}"),
          const SizedBox(height: 16),

          // GŁÓWNY WSKAŹNIK: UŚREDNIONE RSSI
          const Text(
            "UŚREDNIONE RSSI (filtr wielodrogowości):",
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey),
          ),
          Text(
            _smoothedRssi != null
                ? "${_smoothedRssi!.toStringAsFixed(1)} dBm"
                : "-- dBm",
            style: TextStyle(
              fontSize: 46,
              fontWeight: FontWeight.bold,
              color: isAboveThreshold ? Colors.green : Colors.indigo,
            ),
          ),

          // POMOCNICZY WSKAŹNIK: SUROWY ODCZYT CHWILOWY
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.grey.shade200,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              "Surowy odczyt chwilowy (Raw): ${_rawRssi ?? '--'} dBm  |  Bufor: ${_rssiBuffer.length}/$_windowSize",
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ),

          const SizedBox(height: 14),
          LinearProgressIndicator(
            value: proximityProgress,
            minHeight: 14,
            borderRadius: BorderRadius.circular(8),
            color: isAboveThreshold ? Colors.green : Colors.orange,
          ),
          const SizedBox(height: 16),

          // SUWAK 1: PRÓG ZADZIAŁANIA (dBm)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text("Próg zaliczenia (FOUND):"),
              Text(
                "${rssiThreshold.toInt()} dBm",
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
            ],
          ),
          Slider(
            value: rssiThreshold,
            min: -90,
            max: -30,
            divisions: 60,
            label: "${rssiThreshold.toInt()} dBm",
            onChanged: (val) {
              setState(() {
                rssiThreshold = val;
                _foundSentToServer = false;
              });
            },
          ),

          // SUWAK 2: ROZMIAR OKNA UŚREDNIANIA (LICZBA PRÓBEK)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text("Okno uśredniania (tłumienie pików):"),
              Text(
                "$_windowSize próbek",
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
            ],
          ),
          Slider(
            value: _windowSize.toDouble(),
            min: 3,
            max: 30,
            divisions: 27,
            label: "$_windowSize próbek",
            onChanged: (val) {
              setState(() {
                _windowSize = val.toInt();
                while (_rssiBuffer.length > _windowSize) {
                  _rssiBuffer.removeAt(0);
                }
              });
            },
          ),

          const SizedBox(height: 4),
          Text(
            statusLog,
            textAlign: TextAlign.center,
            style: const TextStyle(fontStyle: FontStyle.italic, fontSize: 13),
          ),
          const Divider(height: 24),

          // PRZYCISKI STERUJĄCE
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              OutlinedButton.icon(
                onPressed: _clearBuffer,
                icon: const Icon(Icons.cleaning_services, size: 18),
                label: const Text("Wyczyść bufor"),
              ),
              ElevatedButton.icon(
                onPressed: () async {
                  await widget.onFound();
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text("Wysłano status FOUND do AWS")),
                    );
                  }
                },
                icon: const Icon(Icons.check_circle, color: Colors.green, size: 18),
                label: const Text("Wymuś FOUND"),
              ),
              OutlinedButton.icon(
                onPressed: () async {
                  _foundSentToServer = false;
                  await widget.onResetIdle();
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text("Zresetowano status na IDLE")),
                    );
                  }
                },
                icon: const Icon(Icons.restart_alt, size: 18),
                label: const Text("Reset IDLE"),
              ),
            ],
          ),
        ],
      ),
    );
  }
}