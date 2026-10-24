# Analiza technologii i baz danych dla aplikacji lokalizatora paczek

## 1. Aplikacja kliencka (Frontend)
Interfejs dla pracowników sklepu działający bezpośrednio na ich telefonach komórkowych.
* **Technologia bazowa:** **React.js** skonfigurowany jako aplikacja PWA (Progressive Web App). PWA pozwala na szybkie ładowanie, dodanie ikony aplikacji na ekran główny telefonu oraz płynne działanie.
* **Kluczowe moduły:**
  * **Skaner:** Wykorzystanie bibliotek takich jak `html5-qrcode` lub `react-qr-reader` do obsługi aparatu w telefonie. Służy do skanowania kodu z paczki oraz numeru lokalizatora przy procesie przyjęcia na zaplecze.
  * **Moduł wyszukiwania:** Interfejs do wpisywania kodu odbioru podanego przez klienta, inicjujący proces namierzania paczki na magazynie.

## 2. Serwer i logika biznesowa (Backend)
Główne centrum decyzyjne systemu, uruchomione na maszynie z systemem Windows lub Linux i podłączone do switcha sieciowego.
* **Technologia bazowa:** **Python** z frameworkiem asynchronicznym (**FastAPI**). Zapewnia szybkość przetwarzania współbieżnych zapytań z urządzeń IoT.
* **Zadania komponentu:**
  * Wystawienie REST API do komunikacji z interfejsem React.js na telefonach pracowniczych.
  * Integracja przez API z już istniejącym systemem paczek w sklepie.
  * Przetwarzanie strumienia logów telemetrycznych z bramek w celu obliczeń trylateracji (wykorzystanie bibliotek takich jak `NumPy`).
  * Zarządzanie komendami zwrotnymi – wysyłanie poleceń w dół do bramek, aby konkretny lokalizator uruchomił diodę i brzęczyk.

## 3. Przechowywanie danych (Baza danych)
* **Baza główna:** **PostgreSQL**
  * Zapisywanie trwałych relacji tworzonych podczas przyjęcia (kod paczki przypisany do numeru MAC/ID modułu nRF52840). Odpięcie urządzenia przy wydaniu zamyka ten rekord.
  * Zapisywanie historii wyszukiwań oraz stanu baterii lokalizatorów na podstawie odczytów z wbudowanego przetwornika ADC.
  * Narzucenie spójności danych pozwoli zrealizować alarmy systemowe przy próbie wydania paczki bez zdjęcia modułu.
* **Baza in-memory (Opcjonalnie):** **Redis**
  * Służy jako cache dla surowych i szybko zmieniających się danych RSSI napływających z bramek w czasie rzeczywistym.

## 4. Warstwa komunikacyjna i zasada działania urządzeń IoT (Trylateracja)
Przepływ danych w warstwie sprzętowej musi zostać podzielony na dwa odcinki wykorzystujące odrębne protokoły. Aby określić pozycję w przestrzeni 2D, potrzebujemy 1 nadajnika (lokalizatora) i minimum 3 odbiorników (bramek ESP32-POE rozmieszczonych wysoko w rogach pomieszczenia).

1. **Komunikacja Lokalizatory ↔ Bramki (Bluetooth LE):** 
   Lokalizator z rdzeniem XIAO nRF52840 regularnie (np. co 1 sekundę) wysyła krótki, bezprzewodowy pakiet reklamowy BLE 5, pobierając przy tym bardzo mało prądu z akumulatora LiPo 200 mAh. Trzy okoliczne bramki odbierają ten sam sygnał i mierzą jego siłę (parametr RSSI).
2. **Komunikacja Bramki ↔ Serwer (MQTT):** 
   Bramki z zasilaniem PoE i podłączeniem do sieci Ethernet pełnią rolę translacyjną. Odbierają bezprzewodowe sygnały z lokalizatorów i za pomocą lekkiego protokołu **MQTT** na bieżąco strumieniują informacje o sile sygnału (RSSI) kablami do centralnego serwera z aplikacją Python.
3. **Przetwarzanie (Trylateracja):**
   Serwer oblicza przybliżoną odległość lokalizatora od każdej z trzech bramek na podstawie tłumienia sygnału. Wyznacza trzy wirtualne okręgi – miejsce ich przecięcia to współrzędne paczki.
4. **Wizualizacja i akcja:** 
   Aplikacja (React) wskazuje pracownikowi orientacyjną strefę magazynu (np. konkretny regał). Gdy pracownik tam dotrze, serwer przez MQTT wysyła do bramki komendę. Bramka po BLE wybudza lokalizator, który włącza zewnętrzną diodę LED i pasywny brzęczyk piezo 12 mm ułatwiając ostateczne znalezienie pudełka na półce.
