import os
import random
import httpx
import pytest

LIVE_URL = os.getenv("LIVE_API_URL", "http://127.0.0.1:8000").rstrip("/")


@pytest.mark.live
def test_live_server_full_ble_cycle():
    """
    Smoke test przeciwko zywemu kontenerowi FastAPI + PostgreSQL/Odoo.
    Tworzy paczke testowa, przechodzi LOCATING -> bateria -> FOUND -> DELIVERED (zwalnia MAC).
    """
    suffix = f"{random.randint(10, 99)}"
    raw_mac = f"aa00bb00cc{suffix}"
    canon_mac = f"AA:00:BB:00:CC:{suffix}"
    pkg_code = f"SMOKE-TEST-{random.randint(100000, 999999)}"

    with httpx.Client(base_url=LIVE_URL, timeout=10.0) as c:
        assert c.get("/api/packages").status_code == 200

        r_reg = c.post("/api/packages/register", json={"mac_address": raw_mac, "package_code": pkg_code})
        assert r_reg.status_code == 200, r_reg.text
        pkg = r_reg.json()
        assert pkg["mac_address"] == canon_mac

        assert c.post(f"/api/locate/{raw_mac}").json()["status"] == "LOCATING"
        assert c.patch(f"/api/packages/{raw_mac}/battery", json={"battery_level": 77}).json()["battery_level"] == 77
        assert c.patch(f"/api/packages/{raw_mac}/battery", json={"battery_level": 150}).status_code == 400

        r_found = c.patch(f"/api/packages/{raw_mac}/status", json={"status": "FOUND", "battery_level": 76})
        assert r_found.status_code == 200
        assert r_found.json()["status"] == "FOUND"

        r_del = c.post(f"/api/packages/{pkg['id']}/deliver")
        assert r_del.status_code == 200
        assert r_del.json()["status"] == "DELIVERED"
        assert r_del.json()["mac_address"] is None
