# Smart Lokalizator Paczek - System IoT

## Opis Projektu
System lokalizacji paczek w magazynie punktu odbioru, wykorzystujący technologię Bluetooth Low Energy (BLE) oraz urządzenia IoT. Celem projektu jest drastyczne skrócenie czasu poszukiwania przesyłek przez pracowników. System opiera się na doczepianych do paczek modułach wielokrotnego użytku, które na żądanie emitują sygnał świetlny i dźwiękowy, a także na ciągłym szacowaniu ich położenia za pomocą trylateracji sygnału RSSI.

## Architektura Systemu
Rozwiązanie składa się z czterech głównych warstw komunikujących się w lokalnej sieci sklepu:
1. **Aplikacja kliencka (Frontend):** PWA w React.js dla pracowników (skaner kodów, wyszukiwarka).
2. **Serwer centralny (Backend):** Python (FastAPI) odpowiadający za API, logikę biznesową, obliczenia przestrzenne (NumPy) oraz integrację z systemem paczek w sklepie.
3. **Bramki (Gateways):** Moduły Olimex ESP32-POE pełniące rolę tłumaczy między siecią Ethernet (MQTT) a bezprzewodową siecią Bluetooth LE.
4. **Lokalizatory (Hardware):** Autorskie urządzenia oparte na Seeed XIAO nRF52840, zasilane akumulatorem LiPo, wyposażone w diodę LED o wysokiej jasności i pasywny brzęczyk piezo.

## Struktura Repozytorium

```text
lokalizator-paczek/
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

### 1. Przyjęcie paczki
Pracownik skanuje kod paczki i numer MAC/ID lokalizatora. Backend weryfikuje dane w głównym systemie sklepowym i zapisuje powiązanie w bazie PostgreSQL. Lokalizator zostaje fizycznie przypięty do paczki.

### 2. Telemetria w tle
Lokalizatory cyklicznie rozgłaszają pakiety BLE z informacją o swoim ID i stanie baterii. Bramki rozmieszczone w pomieszczeniu odbierają te sygnały i przesyłają je po MQTT do serwera. Serwer na podstawie siły sygnału (RSSI) wylicza szacunkową strefę magazynu i buforuje ją w bazie Redis.

### 3. Wyszukiwanie paczki
Klient podaje kod odbioru. Pracownik wpisuje go w aplikacji, która wskazuje wyliczoną strefę. Po dotarciu w dany rejon, pracownik inicjuje sygnał. Serwer przez bramki wybudza odpowiedni lokalizator, który uruchamia diodę LED i brzęczyk, wskazując dokładne położenie paczki.

### 4. Wydanie i weryfikacja
Pracownik próbuje wydać paczkę w systemie. System sprawdza, czy lokalizator został z niej zdjęty. Próba wydania paczki z przypiętym urządzeniem skutkuje alarmem w aplikacji. Po poprawnym odpięciu, pracownik odkłada sprzęt na stację ładującą (piny pogo), powiązanie w bazie jest usuwane, a proces zostaje zamknięty.
