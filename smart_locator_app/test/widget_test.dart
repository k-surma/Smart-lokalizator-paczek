import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../lib/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const MethodChannel permissionChannel =
      MethodChannel('flutter.baseflow.com/permissions/methods');

  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(permissionChannel, (MethodCall call) async {
      if (call.method == 'requestPermissions' && call.arguments is List) {
        return {for (final dynamic p in call.arguments as List) p as int: 1};
      }
      return 1;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(permissionChannel, null);
  });

  group('normalizeMacAddress - testy krytyczne', () {
    test('akceptuje format bez dwukropkow (male i wielkie litery)', () {
      expect(normalizeMacAddress('aabbccddeeff'), 'AA:BB:CC:DD:EE:FF');
      expect(normalizeMacAddress('001122334455'), '00:11:22:33:44:55');
      expect(normalizeMacAddress('DeAdBeEfCaFe'), 'DE:AD:BE:EF:CA:FE');
    });

    test('akceptuje dwukropki, myslniki, spacje i prefiksy', () {
      expect(normalizeMacAddress('aa:bb:cc:dd:ee:ff'), 'AA:BB:CC:DD:EE:FF');
      expect(normalizeMacAddress('aa-bb-cc-dd-ee-ff'), 'AA:BB:CC:DD:EE:FF');
      expect(normalizeMacAddress('aa bb cc dd ee ff'), 'AA:BB:CC:DD:EE:FF');
      expect(normalizeMacAddress('MAC:112233445566'), '11:22:33:44:55:66');
    });

    test('parsuje JSON z kodu QR lokalizatora', () {
      expect(normalizeMacAddress('{"mac":"aabbccddeeff"}'), 'AA:BB:CC:DD:EE:FF');
      expect(normalizeMacAddress('{"mac_address":"11-22-33-44-55-66"}'), '11:22:33:44:55:66');
      expect(normalizeMacAddress('{"address":"AA:BB:CC:DD:EE:01"}'), 'AA:BB:CC:DD:EE:01');
    });

    test('odrzuca nieprawidlowe adresy MAC', () {
      expect(normalizeMacAddress(''), isNull);
      expect(normalizeMacAddress('   '), isNull);
      expect(normalizeMacAddress('AABBCCDDEEF'), isNull);       // 11 znakow
      expect(normalizeMacAddress('AABBCCDDEEFF0'), isNull);     // 13 znakow
      expect(normalizeMacAddress('GG:BB:CC:DD:EE:FF'), isNull); // poza hex
      expect(normalizeMacAddress('{"foo":"bar"}'), isNull);
    });
  });

  group('HomeScreen - interfejs PUDO i walidacja formularzy', () {
    testWidgets('renderuje 4 glowne przyciski bez PIN-u i zamawiania kuriera', (tester) async {
      await tester.pumpWidget(const SmartLocatorApp());
      await tester.pumpAndSettle();

      expect(find.text('Nadanie\n(od klienta)'), findsOneWidget);
      expect(find.text('Wydaj kurierowi\n(QR)'), findsOneWidget);
      expect(find.text('Przyjmij\nod kuriera'), findsOneWidget);
      expect(find.text('Wydaj klientowi\n(QR)'), findsOneWidget);

      // Upewniamy sie, ze stare/usuniete elementy nie istnieja
      expect(find.textContaining('PIN'), findsNothing);
      expect(find.textContaining('Zamów kuriera'), findsNothing);
    });

    testWidgets('okno Nadania ma 2 skanery QR (paczka + MAC) i waliduje bledny MAC', (tester) async {
      await tester.pumpWidget(const SmartLocatorApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Nadanie\n(od klienta)'));
      await tester.pumpAndSettle();

      expect(find.text('Przyjmij NADANIE od klienta'), findsOneWidget);
      expect(find.byIcon(Icons.qr_code_scanner), findsNWidgets(2));

      // Puste pola -> komunikat walidacji
      await tester.tap(find.text('Sprawdź w InPost i połącz'));
      await tester.pump();
      expect(find.text('Zeskanuj lub wpisz kod paczki'), findsOneWidget);

      // Poprawny kod, ale bledny MAC -> komunikat walidacji MAC
      final fields = find.byType(TextField);
      await tester.enterText(fields.at(0), '632620676600391116471450');
      await tester.enterText(fields.at(1), 'INVALID_MAC');
      await tester.tap(find.text('Sprawdź w InPost i połącz'));
      await tester.pump();
      expect(
        find.text('Nieprawidłowy MAC (wpisz 12 znaków hex, np. AABBCCDDEEFF)'),
        findsOneWidget,
      );
    });

    testWidgets('okno Przyjecia od kuriera ma 2 skanery QR i pole MAC', (tester) async {
      await tester.pumpWidget(const SmartLocatorApp());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Przyjmij\nod kuriera'));
      await tester.pumpAndSettle();

      expect(find.text('Przyjmij paczkę OD KURIERA'), findsOneWidget);
      expect(find.text('Adres MAC lokalizatora XIAO'), findsOneWidget);
      expect(find.byIcon(Icons.qr_code_scanner), findsNWidgets(2));
    });
  });
}
