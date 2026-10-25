# Smart Lokalizator Paczek - System IoT

## Opis Projektu
System lokalizacji paczek w magazynie punktu odbioru, wykorzystujący technologię Bluetooth Low Energy (BLE) oraz urządzenia IoT. Celem projektu jest drastyczne skrócenie czasu poszukiwania przesyłek przez pracowników. System opiera się na doczepianych do paczek modułach wielokrotnego użytku, które na żądanie emitują sygnał świetlny i dźwiękowy, a także na ciągłym szacowaniu ich położenia za pomocą trylateracji sygnału RSSI.

## Architektura Systemu
Rozwiązanie składa się z czterech głównych warstw komunikujących się w lokalnej sieci sklepu:
1. **Aplikacja kliencka (Frontend):** PWA w React.js dla pracowników (skaner kodów, wyszukiwarka).
2. **Serwer centralny (Backend):** Python (FastAPI) odpowiadający za API, logikę biznesową, obliczenia przestrzenne (NumPy) oraz integrację z systemem paczek w sklepie.
3. **Bramki (Gateways):** Trzy urządzenia oparte na Seeed XIAO nRF52840 a bezprzewodową siecią Bluetooth LE.
4. **Lokalizatory (Hardware):** Autorskie urządzenia oparte na Seeed XIAO nRF52840, zasilane akumulatorem LiPo, wyposażone w diodę LED o wysokiej jasności i pasywny brzęczyk piezo.

## Struktura Repozytorium

```text
Smart-lokalizator-paczek/
├── frontend/                 # Aplikacja PWA (React.js)
│   ├── src/                  # Kod źródłowy aplikacji (komponenty, widoki)
│   ├── public/               # Manifest PWA, ikony
│   └── package.json          # Zależności frontendowe
├── backend/                  # Serwer API i logika trylateracji (Python/FastAPI)
│   ├── api/                  # Endpoinyt REST (rutery)
│   ├── core/                 # Algorytmy trylateracji, logika MQTT
│   ├── models/               # Modele danych i schematy bazy
│   ├── requirements.txt      # Zależności backendowe (FastAPI, NumPy, Paho-MQTT, itp.)
│   └── main.py               # Plik startowy serwera
├── firmware/                 # Oprogramowanie wbudowane (C++/Arduino)
│   ├── gateway/              # Kod dla bramek Olimex ESP32-POE (MQTT <-> BLE)
│   └── locator/              # Kod dla modułów XIAO nRF52840 (BLE, obsługa GPIO, ADC)
├── hardware/                 # Projekty sprzętowe
│   ├── 3d_models/            # Skrypty OpenSCAD i wygenerowane pliki STL (obudowy, klipsy)
│   └── schematics/           # Schematy elektroniczne i diagramy podłączeń
├── docs/                     # Dokumentacja projektu (diagramy sekwencji, analiza wymagań)
├── docker-compose.yml        # Konfiguracja środowiska (PostgreSQL, Redis, Eclipse Mosquitto, Backend)
└── README.md                 # Główny plik informacyjny
```

## Stos Technologiczny
* **Frontend:** React.js, PWA, HTML5-QRCode (obsługa skanera)
* **Backend:** Python, FastAPI, NumPy (obliczenia przestrzenne)
* **Bazy danych:** PostgreSQL (dane relacyjne, historia), Redis (cache danych telemetrycznych RSSI)
* **Broker wiadomości:** Eclipse Mosquitto (MQTT)
* **Urządzenia IoT:** Seeed XIAO nRF52840 (C++), Olimex ESP32-POE (C++)
* **Protokoły komunikacyjne:** REST API, MQTT, Bluetooth Low Energy (BLE 5)

## Przepływ Pracy (Główne Procesy)

# Architektura i Przepływ Danych

Projekt wykorzystuje hybrydową architekturę Edge Computing połączoną z protokołem BLE (Bluetooth Low Energy) oraz backendem w FastAPI i systemem ERP Odoo.

##  Topologia Sprzętowa

W systemie pracują 4 mikrokontrolery **Seeed XIAO nRF52840**, z których każdy pełni ściśle określoną rolę:

1. **Paczka (Tag BLE):** Zasilana bateryjnie. Cyklicznie rozgłasza swój adres MAC (Beacon) i czeka na połączenie GATT, by uruchomić diodę/buzzer.
2. **Bramki Satelitarne (Bramka B i C):** Zasilane z gniazdek ściennych. Zawieszone w rogach magazynu. Ich jedynym zadaniem jest nasłuch (skanowanie RSSI Paczki) i retransmisja wyników przez BLE.
3. **Bramka Główna (Agregator / Bramka A):** Wpięta kablem USB do nieruchomego serwera (laptopa). Skanuje eter, zbiera odczyty od siebie oraz z Bramek B i C, a następnie przesyła je kablem (Serial/UART) do backendu.

---

##  Przepływ 1: Ciągłe Śledzenie Pozycji (Trilateracja w Tle)

Proces ten działa nieprzerwanie w tle, aktualizując pozycję paczki bez udziału użytkownika.

```mermaid
sequenceDiagram
    participant P as Paczka (Tag)
    participant B as Bramka B & C
    participant A as Bramka A (Agregator)
    participant API as FastAPI (Serwer)
    participant O as Odoo (Baza/UI)

    loop Co X sekund
        P->>B: [BLE] Rozgłaszanie (MAC)
        P->>A: [BLE] Rozgłaszanie (MAC)
        Note over B: Mierzy RSSI Paczki
        Note over A: Mierzy RSSI Paczki
        B->>A: [BLE] Retransmisja (Odebrano: Paczka X, RSSI: -65dBm)
        Note over A: Agregacja danych (A, B, C)
        A->>API: [USB / UART] Zrzut paczki: "A:-50,B:-65,C:-70"
        Note over API: Obliczanie pozycji (X, Y) z przecinających się okręgów (Trilateracja)
        API->>O: [API / Baza] Aktualizacja kropki na mapie magazynu
    end


sequenceDiagram
    actor U as Pracownik
    participant O as Odoo (Interfejs)
    participant API as FastAPI (Serwer)
    participant A as Bramka A (Agregator)
    participant P as Paczka (Tag)

    U->>O: Klika przycisk " Lokalizuj (Paczka X)"
    O->>API: [HTTP POST] /api/locate/MAC_PACZKI
    API->>A: [USB / UART] Wysyła JSON z poleceniem i adresem MAC
    Note over A: Przerywa skanowanie
    A->>P: [BLE] Zestawia połączenie (GATT Connect)
    A->>P: [BLE] Wpisuje wartość '1' do charakterystyki LED/Buzzer
    Note over P: Uruchamia Diodę i Buzzer na 10 sekund
    P-->>A: [BLE] Potwierdzenie / Rozłączenie
    Note over A: Wznawia skanowanie RSSI
    A-->>API: [USB / UART] Zwraca status "Sukces"
