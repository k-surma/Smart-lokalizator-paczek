import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main  # noqa: E402

RealAsyncClient = httpx.AsyncClient


class FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text or (str(json_data) if json_data is not None else "")

    def json(self):
        return self._json_data


def make_fake_httpx(handler: Callable[[str, str, Dict[str, Any]], FakeResponse]):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str, headers=None, params=None):
            return handler("GET", url, {"headers": headers, "params": params or {}})

        async def post(self, url: str, headers=None, json=None):
            return handler("POST", url, {"headers": headers, "json": json or {}})

        async def put(self, url: str, headers=None, json=None):
            return handler("PUT", url, {"headers": headers, "json": json or {}})

    class _FakeHttpxModule:
        AsyncClient = _FakeClient

    return _FakeHttpxModule


@pytest_asyncio.fixture
async def client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(main.Base.metadata.create_all)

    TestSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with TestSessionLocal() as session:
            yield session

    main.app.dependency_overrides[main.get_db] = override_get_db
    monkeypatch.setattr(main, "INPOST_ORG_ID", "7338")
    monkeypatch.setattr(main, "INPOST_TOKEN", "test-sandbox-token")

    transport = httpx.ASGITransport(app=main.app)
    async with RealAsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    main.app.dependency_overrides.clear()
    await engine.dispose()


# ==============================================================================
# 1. TESTY JEDNOSTKOWE FUNKCJI POMOCNICZYCH (MAC, QR, GABARYT, DOPASOWANIE)
# ==============================================================================
class TestHelpers:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("aabbccddeeff", "AA:BB:CC:DD:EE:FF"),
            ("AABBCCDDEEFF", "AA:BB:CC:DD:EE:FF"),
            ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),
            ("AA-BB-CC-DD-EE-FF", "AA:BB:CC:DD:EE:FF"),
            ("aa bb cc dd ee ff", "AA:BB:CC:DD:EE:FF"),
            ("MAC:aabbccddeeff", "AA:BB:CC:DD:EE:FF"),
            ('{"mac": "aabbccddeeff"}', "AA:BB:CC:DD:EE:FF"),
            ('{"mac_address": "11-22-33-44-55-66"}', "11:22:33:44:55:66"),
            ('{"address": "00:11:22:33:44:55"}', "00:11:22:33:44:55"),
            ("   ", None),
            (None, None),
        ],
    )
    def test_normalize_mac_valid(self, raw, expected):
        assert main.normalize_mac(raw) == expected

    @pytest.mark.parametrize(
        "bad_mac",
        [
            "AABBCCDDEEF",          # 11 znakow
            "AABBCCDDEEFF0",        # 13 znakow
            "GG:BB:CC:DD:EE:FF",    # spoza hex
            "NOT-A-MAC",
            '{"other": "value"}',
        ],
    )
    def test_normalize_mac_invalid_raises_400(self, bad_mac):
        with pytest.raises(HTTPException) as exc:
            main.normalize_mac(bad_mac)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("632620676600391116471450", "632620676600391116471450"),
            ("InPost: 632620676600391116471450 OK", "632620676600391116471450"),
            ("https://inpost.pl/sledzenie?number=632620676600391116471450&src=qr", "632620676600391116471450"),
            ('{"tracking_number": "632620676600391116471450"}', "632620676600391116471450"),
            ('{"package_code": "14704714"}', "14704714"),
            ("  14704714  ", "14704714"),
        ],
    )
    def test_extract_tracking_code(self, raw, expected):
        assert main.extract_tracking_code(raw) == expected

    def test_map_inpost_size_all_sources(self):
        assert main.map_inpost_size({"parcels": [{"template": "small"}]}) == "A"
        assert main.map_inpost_size({"parcels": [{"template": "medium"}]}) == "B"
        assert main.map_inpost_size({"parcels": [{"template": "large"}]}) == "C"
        assert main.map_inpost_size({"custom_attributes": {"size": "a"}}) == "A"
        assert main.map_inpost_size({}) == "B"

    def test_shipment_matches_code_strict(self):
        item = {"id": 14704714, "tracking_number": "632620676600391116471450", "reference": "REF-1"}
        assert main._shipment_matches_code(item, "632620676600391116471450") is True
        assert main._shipment_matches_code(item, "14704714") is True
        assert main._shipment_matches_code(item, "REF-1") is True
        assert main._shipment_matches_code(item, "632620676600391116479999") is False


# ==============================================================================
# 2. INTEGRACJA INPOST SHIPX + REGRESJA PODMIENIANIA PACZEK + FALLBACK /TRACKING
# ==============================================================================
class TestInpostIntegration:
    @pytest.mark.asyncio
    async def test_regression_second_parcel_does_not_overwrite_first(self, client, monkeypatch):
        """
        KRYTYCZNY TEST REGRESYJNY:
        Gdy InPost Sandbox ignoruje parametr ?tracking_number= i zwraca zawsze pierwsza paczke
        jako items[0], druga paczka (z panelu WWW, dostepna w /tracking) NIE moze nadpisac pierwszej.
        """
        code1 = "632620676600391116471111"
        code2 = "632620676600391116472222"
        first_shipment = {
            "id": 1001,
            "tracking_number": code1,
            "status": "confirmed",
            "parcels": [{"template": "small"}],
        }

        def handler(method, url, kwargs):
            if "/organizations/7338/shipments" in url:
                # Symulacja bledu InPost Sandbox: zwraca zawsze pierwsza paczke mimo filtra
                return FakeResponse(200, {"items": [first_shipment]})
            if url.endswith(f"/tracking/{code2}"):
                return FakeResponse(200, {
                    "tracking_number": code2,
                    "status": "confirmed",
                    "custom_attributes": {"size": "C"},
                })
            if "/shipments/1001" in url:
                return FakeResponse(200, first_shipment)
            return FakeResponse(404, {"message": "not found"})

        monkeypatch.setattr(main, "httpx", make_fake_httpx(handler))

        r1 = await client.post("/api/inpost/accept-outbound", json={"code": code1, "mac_address": "aa11bb22cc01"})
        assert r1.status_code == 200
        assert r1.json()["package_code"] == code1
        assert r1.json()["parcel_size"] == "A"

        r2 = await client.post("/api/inpost/accept-outbound", json={"code": code2, "mac_address": "aa11bb22cc02"})
        assert r2.status_code == 200
        assert r2.json()["package_code"] == code2
        assert r2.json()["parcel_size"] == "C"

        lst = await client.get("/api/packages")
        assert lst.status_code == 200
        codes = {p["package_code"] for p in lst.json()}
        assert codes == {code1, code2}

    @pytest.mark.asyncio
    async def test_inpost_auth_error_returns_502(self, client, monkeypatch):
        def handler(method, url, kwargs):
            return FakeResponse(401, {"message": "unauthorized"})

        monkeypatch.setattr(main, "httpx", make_fake_httpx(handler))
        r = await client.post(
            "/api/inpost/accept-outbound",
            json={"code": "632620676600391116471450", "mac_address": "aabbccddeeff"},
        )
        assert r.status_code == 502

    @pytest.mark.asyncio
    async def test_inpost_missing_parcel_returns_404(self, client, monkeypatch):
        def handler(method, url, kwargs):
            if "/organizations/7338/shipments" in url:
                return FakeResponse(200, {"items": []})
            return FakeResponse(404, {"message": "not found"})

        monkeypatch.setattr(main, "httpx", make_fake_httpx(handler))
        r = await client.post(
            "/api/inpost/accept-inbound",
            json={"code": "999999999999999999999999", "mac_address": "aabbccddeeff"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_inpost_env_returns_500(self, client, monkeypatch):
        monkeypatch.setattr(main, "INPOST_TOKEN", "")
        r = await client.post(
            "/api/inpost/accept-outbound",
            json={"code": "632620676600391116471450", "mac_address": "aabbccddeeff"},
        )
        assert r.status_code == 500


# ==============================================================================
# 3. PELNY CYKL OUTBOUND (NADANIE -> LOKALIZACJA KURIER -> FOUND -> WYDANIE)
# ==============================================================================
class TestOutboundLifecycle:
    @pytest.mark.asyncio
    async def test_full_outbound_flow(self, client, monkeypatch):
        code = "632620676600391116473333"
        shipment = {"id": 2001, "tracking_number": code, "status": "confirmed", "parcels": [{"template": "medium"}]}

        def handler(method, url, kwargs):
            if "/organizations/7338/shipments" in url:
                return FakeResponse(200, {"items": [shipment]})
            if "/shipments/2001" in url:
                return FakeResponse(200, shipment)
            return FakeResponse(404)

        monkeypatch.setattr(main, "httpx", make_fake_httpx(handler))

        # 1. Przyjecie nadania z MAC bez dwukropkow
        r_acc = await client.post("/api/inpost/accept-outbound", json={"code": code, "mac_address": "112233445566"})
        assert r_acc.status_code == 200
        pkg = r_acc.json()
        assert pkg["direction"] == "OUTBOUND"
        assert pkg["inpost_pudo_status"] == "dispatched_by_sender"
        assert pkg["mac_address"] == "11:22:33:44:55:66"
        assert pkg["status"] == "IDLE"

        # 2. Proba wydania jako paczka klienta (INBOUND) musi zawiesc (izolacja kierunkow)
        r_wrong = await client.post("/api/inpost/client-verify", json={"code": code})
        assert r_wrong.status_code == 404

        # 3. Kurier skanuje QR -> status LOCATING
        r_cur = await client.post("/api/inpost/courier-pickup", json={"code": f"https://inpost.pl/?number={code}"})
        assert r_cur.status_code == 200
        assert r_cur.json()["status"] == "LOCATING"

        # 4. Wylaczenie alarmu BLE i oznaczenie FOUND z bateria
        r_found = await client.patch(
            "/api/packages/112233445566/status",
            json={"status": "FOUND", "battery_level": 87},
        )
        assert r_found.status_code == 200
        assert r_found.json()["status"] == "FOUND"
        assert r_found.json()["battery_level"] == 87

        # 5. Wydanie kurierowi -> DELIVERED + zwolnienie MAC
        r_del = await client.post(f"/api/packages/{pkg['id']}/deliver")
        assert r_del.status_code == 200
        delivered = r_del.json()
        assert delivered["status"] == "DELIVERED"
        assert delivered["inpost_pudo_status"] == "collected_from_sender"
        assert delivered["mac_address"] is None

        # 6. Ponowna proba odbioru wydanej paczki -> 400
        r_again = await client.post("/api/inpost/courier-pickup", json={"code": code})
        assert r_again.status_code == 400


# ==============================================================================
# 4. PELNY CYKL INBOUND (PRZYJECIE -> WYDANIE QR-ONLY -> KARTA HTML -> SYMULACJA)
# ==============================================================================
class TestInboundLifecycle:
    @pytest.mark.asyncio
    async def test_full_inbound_qr_only_flow_and_html_pass(self, client, monkeypatch):
        code = "632620676600391116474444"
        shipment = {
            "id": 3001,
            "tracking_number": code,
            "status": "confirmed",
            "parcels": [{"template": "small"}],
            "receiver": {"phone": "500600700"},
        }

        def handler(method, url, kwargs):
            if "/organizations/7338/shipments" in url:
                return FakeResponse(200, {"items": [shipment]})
            if "/shipments/3001" in url:
                return FakeResponse(200, shipment)
            return FakeResponse(404)

        monkeypatch.setattr(main, "httpx", make_fake_httpx(handler))

        # 1. Przyjecie od kuriera
        r_in = await client.post("/api/inpost/accept-inbound", json={"code": code, "mac_address": "aa:bb:cc:11:22:33"})
        assert r_in.status_code == 200
        pkg = r_in.json()
        assert pkg["direction"] == "INBOUND"
        assert pkg["inpost_pudo_status"] == "ready_to_pickup"
        assert pkg["pickup_code"] is None  # system bez PIN-u

        # 2. Karta QR HTML (bez PIN i bez telefonu)
        r_html = await client.get(f"/api/inpost/client-pass/{code}")
        assert r_html.status_code == 200
        assert code in r_html.text
        assert "api.qrserver.com" in r_html.text
        assert "Kod odbioru (PIN)" not in r_html.text
        assert "4 ostatnie cyfry" not in r_html.text

        # 3. Weryfikacja klienta wylacznie po QR (bez PIN-u i telefonu)
        r_ver = await client.post("/api/inpost/client-verify", json={"code": code})
        assert r_ver.status_code == 200
        assert r_ver.json()["status"] == "LOCATING"

        # 4. Wydanie klientowi
        r_del = await client.post(f"/api/packages/{pkg['id']}/deliver")
        assert r_del.status_code == 200
        assert r_del.json()["inpost_pudo_status"] == "delivered"
        assert r_del.json()["mac_address"] is None

        # 5. Ponowna weryfikacja wydanej paczki -> 400
        r_ver2 = await client.post("/api/inpost/client-verify", json={"code": code})
        assert r_ver2.status_code == 400

    @pytest.mark.asyncio
    async def test_client_verify_empty_code_returns_400(self, client):
        r = await client.post("/api/inpost/client-verify", json={"code": "   "})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_simulate_ready_for_pickup_polls_tracking_number(self, client, monkeypatch):
        poll_count = {"n": 0}
        code = "632620676600391116475555"

        async def fast_sleep(_sec):
            return None

        def handler(method, url, kwargs):
            if method == "POST" and "/organizations/7338/shipments" in url:
                return FakeResponse(201, {"id": 4001, "tracking_number": None, "status": "created"})
            if method == "GET" and "/shipments/4001" in url:
                poll_count["n"] += 1
                if poll_count["n"] == 1:
                    return FakeResponse(200, {"id": 4001, "tracking_number": None, "status": "offer_selected"})
                return FakeResponse(200, {
                    "id": 4001,
                    "tracking_number": code,
                    "status": "confirmed",
                    "parcels": [{"template": "large"}],
                    "receiver": {"phone": "600700800"},
                })
            if method == "PUT" and "/shipments/4001" in url:
                return FakeResponse(200, {"id": 4001})
            return FakeResponse(404)

        monkeypatch.setattr(main.asyncio, "sleep", fast_sleep)
        monkeypatch.setattr(main, "httpx", make_fake_httpx(handler))

        r = await client.post(
            "/api/inpost/simulate-ready-for-pickup",
            json={"size_template": "large", "target_point": "KRA01M", "mac_address": "ffeeddccbbaa"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["package_code"] == code
        assert data["parcel_size"] == "C"
        assert data["mac_address"] == "FF:EE:DD:CC:BB:AA"
        assert poll_count["n"] >= 2


# ==============================================================================
# 5. KONFLIKTY MAC, REUZYCIE TAGU BLE, LOCATE I ENDPOINT BATERII
# ==============================================================================
class TestBleConflictsAndBattery:
    @pytest.mark.asyncio
    async def test_mac_conflict_409_and_reuse_after_deliver(self, client, monkeypatch):
        c1 = "632620676600391116476661"
        c2 = "632620676600391116476662"
        shipments = {
            c1: {"id": 5001, "tracking_number": c1, "status": "confirmed", "parcels": [{"template": "small"}]},
            c2: {"id": 5002, "tracking_number": c2, "status": "confirmed", "parcels": [{"template": "small"}]},
        }

        def handler(method, url, kwargs):
            if "/organizations/7338/shipments" in url:
                tn = kwargs["params"].get("tracking_number")
                return FakeResponse(200, {"items": [shipments[tn]] if tn in shipments else list(shipments.values())})
            return FakeResponse(200, {"status": "confirmed"})

        monkeypatch.setattr(main, "httpx", make_fake_httpx(handler))

        r1 = await client.post("/api/inpost/accept-outbound", json={"code": c1, "mac_address": "aa:aa:aa:aa:aa:01"})
        assert r1.status_code == 200
        pkg1_id = r1.json()["id"]

        # Ten sam MAC dla drugiej aktywnej paczki (nawet wpisany bez dwukropkow) -> 409 Conflict
        r_conflict = await client.post("/api/inpost/accept-outbound", json={"code": c2, "mac_address": "aaaaaaaaaa01"})
        assert r_conflict.status_code == 409

        # Wydanie pierwszej paczki zwalnia MAC
        r_del = await client.post(f"/api/packages/{pkg1_id}/deliver")
        assert r_del.status_code == 200
        assert r_del.json()["mac_address"] is None

        # Teraz ten sam MAC przechodzi bez bledu dla drugiej paczki
        r2 = await client.post("/api/inpost/accept-outbound", json={"code": c2, "mac_address": "aaaaaaaaaa01"})
        assert r2.status_code == 200
        assert r2.json()["mac_address"] == "AA:AA:AA:AA:AA:01"

    @pytest.mark.asyncio
    async def test_register_locate_status_and_battery_boundaries(self, client):
        # Rejestracja z MAC bez dwukropkow
        r_reg = await client.post("/api/packages/register", json={"mac_address": "de:ad:be:ef:00:01", "package_code": "TEST-PKG-1"})
        assert r_reg.status_code == 200
        assert r_reg.json()["mac_address"] == "DE:AD:BE:EF:00:01"

        # Wywolanie lokalizacji po MAC bez dwukropkow w sciezce URL
        r_loc = await client.post("/api/locate/deadbeef0001")
        assert r_loc.status_code == 200
        assert r_loc.json()["status"] == "LOCATING"

        # Bateria - wartosci poprawne (0, 55, 100)
        for val in (0, 55, 100):
            r_bat = await client.patch("/api/packages/deadbeef0001/battery", json={"battery_level": val})
            assert r_bat.status_code == 200
            assert r_bat.json()["battery_level"] == val

        # Bateria - wartosci spoza zakresu (-1, 101) -> 400
        for bad in (-1, 101):
            r_bad = await client.patch("/api/packages/deadbeef0001/battery", json={"battery_level": bad})
            assert r_bad.status_code == 400

        # Bateria dla nieznanego MAC -> 404, dla blednego formatu MAC -> 400
        assert (await client.patch("/api/packages/112233445566/battery", json={"battery_level": 50})).status_code == 404
        assert (await client.patch("/api/packages/INVALIDMAC/battery", json={"battery_level": 50})).status_code == 400

        # Zmiana statusu na FOUND + bateria
        r_st = await client.patch("/api/packages/deadbeef0001/status", json={"status": "FOUND", "battery_level": 91})
        assert r_st.status_code == 200
        assert r_st.json()["status"] == "FOUND"
        assert r_st.json()["battery_level"] == 91
