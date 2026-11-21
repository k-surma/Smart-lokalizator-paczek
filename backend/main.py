import asyncio
import json
import os
import random
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, select, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://odoo:odoopassword@db-odoo:5432/odoo_db"
)
INPOST_SANDBOX_URL = "https://sandbox-api-shipx-pl.easypack24.net/v1"
INPOST_ORG_ID = os.getenv("INPOST_ORG_ID", "").strip()
INPOST_TOKEN = os.getenv("INPOST_TOKEN", "").strip()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"statement_cache_size": 0},
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# ==============================================================================
# 1. MODEL BAZY DANYCH (współdzielona tabela 'packages' z Odoo 17)
# ==============================================================================
class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String, unique=True, nullable=True, index=True)
    package_code = Column(String, unique=True, nullable=False, index=True)
    direction = Column(String, default="INBOUND", nullable=False)  # INBOUND | OUTBOUND
    status = Column(String, default="IDLE", nullable=False)        # IDLE | LOCATING | FOUND | DELIVERED
    battery_level = Column(Integer, default=100)
    last_seen = Column(DateTime(timezone=False), default=datetime.utcnow)

    # Integracja InPost ShipX Sandbox + Maszyna stanów PUDO
    inpost_shipment_id = Column(Integer, nullable=True)
    inpost_api_status = Column(String, nullable=True)
    inpost_pudo_status = Column(String, default="confirmed")       # confirmed | dispatched_by_sender | ready_to_pickup | collected_from_sender | delivered
    parcel_size = Column(String, nullable=True)                    # A | B | C
    recipient_phone = Column(String, nullable=True)
    pickup_code = Column(String, nullable=True)


# ==============================================================================
# 2. SCHEMATY PYDANTIC
# ==============================================================================
class PackageRegisterRequest(BaseModel):
    mac_address: str
    package_code: str


class PackageStatusUpdateRequest(BaseModel):
    status: str
    battery_level: Optional[int] = None


class InpostAcceptRequest(BaseModel):
    code: str
    mac_address: str


class CourierPickupRequest(BaseModel):
    code: str


class ClientVerifyRequest(BaseModel):
    code: Optional[str] = None
    qr_code: Optional[str] = None
    pickup_code: Optional[str] = None
    phone_last4: Optional[str] = None


class SimulateInboundRequest(BaseModel):
    recipient_phone: str = "500600700"
    recipient_email: str = "klient@zabka-pudo.pl"
    size_template: str = "medium"          # small | medium | large
    target_point: str = "KRA01M"
    mac_address: Optional[str] = None


class PackageResponse(BaseModel):
    id: int
    mac_address: Optional[str] = None
    package_code: str
    direction: str = "INBOUND"
    status: str
    battery_level: Optional[int] = 100
    last_seen: Optional[datetime] = None
    inpost_shipment_id: Optional[int] = None
    inpost_api_status: Optional[str] = None
    inpost_pudo_status: Optional[str] = None
    parcel_size: Optional[str] = None
    recipient_phone: Optional[str] = None
    pickup_code: Optional[str] = None
    inpost_sync_info: Optional[str] = None

    class Config:
        from_attributes = True


# ==============================================================================
# 3. INICJALIZACJA FASTAPI I BEZPIECZNA MIGRACJA TABELI
# ==============================================================================
app = FastAPI(title="Smart Parcel PUDO API (Odoo 17 + InPost ShipX Sandbox)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        migrations = [
            "ALTER TABLE packages ALTER COLUMN mac_address DROP NOT NULL;",
            "ALTER TABLE packages ADD COLUMN IF NOT EXISTS direction VARCHAR DEFAULT 'INBOUND' NOT NULL;",
            "ALTER TABLE packages ADD COLUMN IF NOT EXISTS inpost_shipment_id INTEGER;",
            "ALTER TABLE packages ADD COLUMN IF NOT EXISTS inpost_api_status VARCHAR;",
            "ALTER TABLE packages ADD COLUMN IF NOT EXISTS inpost_pudo_status VARCHAR DEFAULT 'confirmed';",
            "ALTER TABLE packages ADD COLUMN IF NOT EXISTS parcel_size VARCHAR;",
            "ALTER TABLE packages ADD COLUMN IF NOT EXISTS recipient_phone VARCHAR;",
            "ALTER TABLE packages ADD COLUMN IF NOT EXISTS pickup_code VARCHAR;",
        ]
        for stmt in migrations:
            await conn.execute(text(stmt))


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ==============================================================================
# 4. FUNKCJE POMOCNICZE (NORMALIZACJA MAC + INPOST SHIPX SANDBOX)
# ==============================================================================
def normalize_mac(raw_mac: Optional[str]) -> Optional[str]:
    """
    Akceptuje adres MAC bez dwukropków (aabbccddeeff), z dwukropkami/myślnikami/spacjami
    oraz z kodu QR w formacie JSON ({"mac": "..."}). Zwraca kanoniczny AA:BB:CC:DD:EE:FF.
    """
    if raw_mac is None or not raw_mac.strip():
        return None
    cleaned = raw_mac.strip()

    if cleaned.startswith("{"):
        try:
            parsed = json.loads(cleaned)
            for key in ("mac_address", "mac", "address"):
                if parsed.get(key):
                    cleaned = str(parsed[key]).strip()
                    break
        except json.JSONDecodeError:
            pass

    sep_match = re.search(r"([0-9A-Fa-f]{2}(?:[:\-\s][0-9A-Fa-f]{2}){5})", cleaned)
    if sep_match:
        hex_only = re.sub(r"[^0-9A-Fa-f]", "", sep_match.group(1)).upper()
    else:
        plain_match = re.search(r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{12})(?![0-9A-Fa-f])", cleaned)
        if not plain_match:
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowy adres MAC: '{raw_mac}'. Podaj 12 znaków hex (np. AABBCCDDEEFF lub AA:BB:CC:DD:EE:FF).",
            )
        hex_only = plain_match.group(1).upper()

    return ":".join(hex_only[i:i + 2] for i in range(0, 12, 2))


def extract_tracking_code(raw_input: str) -> str:
    cleaned = raw_input.strip()
    if cleaned.startswith("{"):
        try:
            parsed = json.loads(cleaned)
            for key in ("tracking_number", "package_code", "code", "id"):
                if parsed.get(key):
                    return str(parsed[key]).strip()
        except json.JSONDecodeError:
            pass
    match_24 = re.search(r"(?<!\d)(\d{24})(?!\d)", cleaned)
    if match_24:
        return match_24.group(1)
    if "number=" in cleaned:
        return cleaned.split("number=")[-1].split("&")[0].strip()
    return cleaned


def map_inpost_size(shipment: Dict[str, Any]) -> str:
    parcels = shipment.get("parcels") or []
    if parcels:
        template = (parcels[0].get("template") or "").lower()
        return {"small": "A", "medium": "B", "large": "C"}.get(template, "B")
    custom_size = (shipment.get("custom_attributes") or {}).get("size")
    if custom_size:
        return str(custom_size).upper()
    return "B"


def normalize_phone(phone: Optional[str]) -> str:
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def require_inpost_config():
    if not INPOST_ORG_ID or not INPOST_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Brak konfiguracji INPOST_ORG_ID lub INPOST_TOKEN w pliku .env na serwerze EC2."
        )


async def fetch_shipment_from_inpost(raw_code: str) -> Dict[str, Any]:
    require_inpost_config()
    code = extract_tracking_code(raw_code)
    headers = {"Authorization": f"Bearer {INPOST_TOKEN}"}

    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(
            f"{INPOST_SANDBOX_URL}/organizations/{INPOST_ORG_ID}/shipments",
            headers=headers,
            params={"tracking_number": code},
        )
        if resp.status_code == 200:
            items = resp.json().get("items") or []
            if items:
                return items[0]

        if code.isdigit() and len(code) < 15:
            resp_id = await client.get(
                f"{INPOST_SANDBOX_URL}/shipments/{code}",
                headers=headers,
            )
            if resp_id.status_code == 200:
                return resp_id.json()

        resp_ref = await client.get(
            f"{INPOST_SANDBOX_URL}/organizations/{INPOST_ORG_ID}/shipments",
            headers=headers,
            params={"reference": code},
        )
        if resp_ref.status_code == 200:
            items = resp_ref.json().get("items") or []
            if items:
                return items[0]

        resp_list = await client.get(
            f"{INPOST_SANDBOX_URL}/organizations/{INPOST_ORG_ID}/shipments",
            headers=headers,
            params={"per_page": 50},
        )
        if resp_list.status_code == 200:
            for item in resp_list.json().get("items") or []:
                if (
                    str(item.get("tracking_number") or "") == code
                    or str(item.get("id") or "") == code
                    or str(item.get("reference") or "") == code
                ):
                    return item

        if resp.status_code in (401, 403):
            raise HTTPException(
                status_code=502,
                detail="Błąd autoryzacji InPost Sandbox API (sprawdź INPOST_TOKEN i INPOST_ORG_ID)."
            )

        # Fallback: endpoint /tracking/{code} znajduje też paczki wyklikane ręcznie w panelu WWW Sandbox
        resp_track = await client.get(
            f"{INPOST_SANDBOX_URL}/tracking/{code}",
            headers=headers,
        )
        if resp_track.status_code == 200:
            return resp_track.json()

    raise HTTPException(
        status_code=404,
        detail=f"Przesyłka '{code}' nie istnieje w Twoim koncie InPost Sandbox."
    )


async def sync_event_with_inpost(pkg: Package, event_label: str) -> str:
    """Odpytuje InPost Sandbox API i próbuje zapisać adnotację o zmianie etapu PUDO."""
    if not pkg.inpost_shipment_id or not INPOST_TOKEN:
        return "Zaktualizowano lokalnie w Odoo."

    headers = {
        "Authorization": f"Bearer {INPOST_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        put_resp = await client.put(
            f"{INPOST_SANDBOX_URL}/shipments/{pkg.inpost_shipment_id}",
            headers=headers,
            json={"comments": f"{event_label}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"},
        )
        get_resp = await client.get(
            f"{INPOST_SANDBOX_URL}/shipments/{pkg.inpost_shipment_id}",
            headers=headers,
        )
        if get_resp.status_code == 200:
            pkg.inpost_api_status = get_resp.json().get("status") or pkg.inpost_api_status

        if put_resp.status_code in (200, 201):
            return f"Zsynchronizowano z InPost Sandbox (HTTP {put_resp.status_code}) i Odoo."
        return (
            f"Zaktualizowano w Odoo (PUDO: {pkg.inpost_pudo_status}). "
            f"Status po stronie InPost Sandbox API: {pkg.inpost_api_status or 'confirmed'}."
        )


async def release_or_validate_mac(db: AsyncSession, clean_mac: str, current_tracking: str):
    mac_owner_res = await db.execute(select(Package).where(Package.mac_address == clean_mac))
    mac_owner = mac_owner_res.scalars().first()
    if mac_owner and mac_owner.package_code != current_tracking:
        if mac_owner.status != "DELIVERED":
            raise HTTPException(
                status_code=409,
                detail=f"Lokalizator {clean_mac} jest zajęty przez niewydaną paczkę {mac_owner.package_code}."
            )
        mac_owner.mac_address = None
        await db.flush()


async def bind_package_with_tag(
    db: AsyncSession,
    inpost_data: Dict[str, Any],
    mac_address: Optional[str],
    direction: str,
    pudo_status: str,
) -> Package:
    clean_mac = normalize_mac(mac_address)
    tracking = str(inpost_data.get("tracking_number") or inpost_data.get("id"))
    shipment_id = inpost_data.get("id")
    api_status = inpost_data.get("status", "confirmed")
    parcel_size = map_inpost_size(inpost_data)
    receiver = inpost_data.get("receiver") or {}
    phone = normalize_phone(receiver.get("phone"))

    if clean_mac:
        await release_or_validate_mac(db, clean_mac, tracking)

    pkg_res = await db.execute(select(Package).where(Package.package_code == tracking))
    pkg = pkg_res.scalars().first()

    if pkg:
        pkg.mac_address = clean_mac if clean_mac is not None else pkg.mac_address
        pkg.direction = direction
        pkg.status = "IDLE"
        pkg.last_seen = datetime.utcnow()
        pkg.inpost_shipment_id = shipment_id
        pkg.inpost_api_status = api_status
        pkg.inpost_pudo_status = pudo_status
        pkg.parcel_size = parcel_size
        pkg.recipient_phone = phone or pkg.recipient_phone
    else:
        pkg = Package(
            mac_address=clean_mac,
            package_code=tracking,
            direction=direction,
            status="IDLE",
            battery_level=100,
            last_seen=datetime.utcnow(),
            inpost_shipment_id=shipment_id,
            inpost_api_status=api_status,
            inpost_pudo_status=pudo_status,
            parcel_size=parcel_size,
            recipient_phone=phone,
            pickup_code=None,
        )
        db.add(pkg)

    try:
        await db.commit()
        await db.refresh(pkg)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Konflikt unikalności MAC lub numeru paczki.")
    return pkg


# ==============================================================================
# 5. PROCES 1: NADAWANIE PACZKI (OUTBOUND)
# ==============================================================================
@app.post("/api/inpost/accept-outbound", response_model=PackageResponse)
async def accept_outbound_parcel(req: InpostAcceptRequest, db: AsyncSession = Depends(get_db)):
    clean_mac = normalize_mac(req.mac_address)
    if not clean_mac:
        raise HTTPException(status_code=400, detail="Wpisz lub zeskanuj adres MAC lokalizatora.")
    inpost_data = await fetch_shipment_from_inpost(req.code)
    pkg = await bind_package_with_tag(
        db, inpost_data, clean_mac, direction="OUTBOUND", pudo_status="dispatched_by_sender"
    )
    sync_msg = await sync_event_with_inpost(pkg, "PUDO_DISPATCHED_BY_SENDER")
    await db.commit()
    await db.refresh(pkg)
    resp = PackageResponse.model_validate(pkg)
    resp.inpost_sync_info = sync_msg
    return resp


@app.post("/api/inpost/courier-pickup", response_model=PackageResponse)
async def courier_pickup_locate(req: CourierPickupRequest, db: AsyncSession = Depends(get_db)):
    code = extract_tracking_code(req.code)
    result = await db.execute(
        select(Package).where(
            or_(
                Package.package_code == code,
                Package.inpost_shipment_id == (int(code) if code.isdigit() and len(code) < 15 else -1),
            ),
            Package.direction == "OUTBOUND",
        )
    )
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Brak w magazynie nadanej paczki dla kodu: {code}")
    if pkg.status == "DELIVERED":
        raise HTTPException(status_code=400, detail="Ta paczka została już wydana kurierowi.")
    if not pkg.mac_address:
        raise HTTPException(status_code=400, detail="Paczka nie ma przypiętego lokalizatora BLE.")

    pkg.status = "LOCATING"
    pkg.last_seen = datetime.utcnow()
    await db.commit()
    await db.refresh(pkg)
    return pkg


# ==============================================================================
# 6. PROCES 2: ODBIÓR OD KURIERA I WYDANIE KLIENTOWI (INBOUND - TYLKO SKANER QR)
# ==============================================================================
@app.post("/api/inpost/accept-inbound", response_model=PackageResponse)
async def accept_inbound_parcel(req: InpostAcceptRequest, db: AsyncSession = Depends(get_db)):
    clean_mac = normalize_mac(req.mac_address)
    if not clean_mac:
        raise HTTPException(status_code=400, detail="Wpisz lub zeskanuj adres MAC lokalizatora.")
    inpost_data = await fetch_shipment_from_inpost(req.code)
    pkg = await bind_package_with_tag(
        db, inpost_data, clean_mac, direction="INBOUND", pudo_status="ready_to_pickup"
    )
    sync_msg = await sync_event_with_inpost(pkg, "PUDO_READY_TO_PICKUP")
    await db.commit()
    await db.refresh(pkg)
    resp = PackageResponse.model_validate(pkg)
    resp.inpost_sync_info = sync_msg
    return resp


@app.post("/api/inpost/client-verify", response_model=PackageResponse)
async def verify_client_pickup(req: ClientVerifyRequest, db: AsyncSession = Depends(get_db)):
    raw_code = (req.code or req.qr_code or "").strip()
    if not raw_code:
        raise HTTPException(status_code=400, detail="Zeskanuj kod QR lub podaj numer przesyłki.")

    scanned = extract_tracking_code(raw_code)
    result = await db.execute(
        select(Package).where(
            or_(
                Package.package_code == scanned,
                Package.inpost_shipment_id == (int(scanned) if scanned.isdigit() and len(scanned) < 15 else -1),
            ),
            Package.direction == "INBOUND",
        )
    )
    matched = result.scalars().first()

    if not matched:
        raise HTTPException(status_code=404, detail=f"Brak w magazynie paczki do odbioru dla kodu: {scanned}")
    if matched.status == "DELIVERED":
        raise HTTPException(status_code=400, detail="Ta paczka została już wydana klientowi.")
    if not matched.mac_address:
        raise HTTPException(status_code=400, detail="Paczka nie ma przypiętego lokalizatora BLE.")

    matched.status = "LOCATING"
    matched.last_seen = datetime.utcnow()
    await db.commit()
    await db.refresh(matched)
    return matched


# ==============================================================================
# 7. SYMULACJA PEŁNEGO NADANIA -> DO ODBIORU (WYWOŁYWANA PRZYCISKIEM W ODOO)
# ==============================================================================
@app.post("/api/inpost/simulate-ready-for-pickup", response_model=PackageResponse)
async def simulate_ready_for_pickup(req: SimulateInboundRequest, db: AsyncSession = Depends(get_db)):
    require_inpost_config()
    clean_mac = normalize_mac(req.mac_address)
    headers = {"Authorization": f"Bearer {INPOST_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "receiver": {
            "first_name": "Jan",
            "last_name": "Kowalski",
            "email": req.recipient_email,