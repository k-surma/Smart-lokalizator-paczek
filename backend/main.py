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
    inpost_api_status = Column(String, nullable=True)              # Surowy status z API InPost
    inpost_pudo_status = Column(String, default="confirmed")       # confirmed | dispatched_by_sender | ready_to_pickup | collected_from_sender | delivered
    parcel_size = Column(String, nullable=True)                    # A | B | C
    recipient_phone = Column(String, nullable=True)
    pickup_code = Column(String, nullable=True)                    # 6-cyfrowy kod odbioru


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
# 4. FUNKCJE POMOCNICZE INPOST SHIPX SANDBOX
# ==============================================================================
def normalize_mac(raw_mac: Optional[str]) -> Optional[str]:
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
    sep = re.search(r"([0-9A-Fa-f]{2}(?:[:\-\s][0-9A-Fa-f]{2}){5})", cleaned)
    if sep:
        hx = re.sub(r"[^0-9A-Fa-f]", "", sep.group(1)).upper()
    else:
        plain = re.search(r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{12})(?![0-9A-Fa-f])", cleaned)
        if not plain:
            raise HTTPException(
                status_code=400,
                detail=f"Nieprawidłowy adres MAC: '{raw_mac}'. Podaj 12 znaków hex (np. AABBCCDDEEFF lub AA:BB:CC:DD:EE:FF).",
            )
        hx = plain.group(1).upper()
    return ":".join(hx[i:i + 2] for i in range(0, 12, 2))


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


def _shipment_matches_code(item: Dict[str, Any], code: str) -> bool:
    return (
        str(item.get("tracking_number") or "").strip() == code
        or str(item.get("id") or "").strip() == code
        or str(item.get("reference") or "").strip() == code
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
        if resp.status_code in (401, 403):
            raise HTTPException(
                status_code=502,
                detail="Błąd autoryzacji InPost Sandbox API (sprawdź INPOST_TOKEN i INPOST_ORG_ID)."
            )
        if resp.status_code == 200:
            for item in resp.json().get("items") or []:
                if _shipment_matches_code(item, code):
                    return item

        if code.isdigit() and len(code) < 15:
            resp_id = await client.get(
                f"{INPOST_SANDBOX_URL}/shipments/{code}",
                headers=headers,
            )
            if resp_id.status_code == 200:
                item = resp_id.json()
                if _shipment_matches_code(item, code):
                    return item

        resp_list = await client.get(
            f"{INPOST_SANDBOX_URL}/organizations/{INPOST_ORG_ID}/shipments",
            headers=headers,
            params={"per_page": 100},
        )
        if resp_list.status_code == 200:
            for item in resp_list.json().get("items") or []:
                if _shipment_matches_code(item, code):
                    return item

        # Fallback: endpoint /tracking/{code} znajduje paczki wyklikane ręcznie w panelu WWW Sandbox
        resp_track = await client.get(
            f"{INPOST_SANDBOX_URL}/tracking/{code}",
            headers=headers,
        )
        if resp_track.status_code == 200:
            track_data = resp_track.json()
            if str(track_data.get("tracking_number") or "").strip() == code:
                return track_data

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
    generated_pin = None

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
        if direction == "INBOUND" and not pkg.pickup_code:
            pkg.pickup_code = generated_pin
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
            pickup_code=generated_pin,
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
    if not req.mac_address.strip():
        raise HTTPException(status_code=400, detail="Wpisz adres MAC lokalizatora.")
    inpost_data = await fetch_shipment_from_inpost(req.code)
    # Po nadaniu w punkcie status PUDO zmienia się na 'dispatched_by_sender' (Nadana w punkcie)
    pkg = await bind_package_with_tag(
        db, inpost_data, req.mac_address, direction="OUTBOUND", pudo_status="dispatched_by_sender"
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
# 6. PROCES 2: ODBIÓR OD KURIERA I WYDANIE KLIENTOWI (INBOUND)
# ==============================================================================
@app.post("/api/inpost/accept-inbound", response_model=PackageResponse)
async def accept_inbound_parcel(req: InpostAcceptRequest, db: AsyncSession = Depends(get_db)):
    if not req.mac_address.strip():
        raise HTTPException(status_code=400, detail="Wpisz adres MAC lokalizatora.")
    inpost_data = await fetch_shipment_from_inpost(req.code)
    # Po przyjęciu od kuriera status PUDO przechodzi na 'ready_to_pickup' (Do odbioru w punkcie)
    pkg = await bind_package_with_tag(
        db, inpost_data, req.mac_address, direction="INBOUND", pudo_status="ready_to_pickup"
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
    """
    Tworzy prawdziwą przesyłkę w InPost ShipX Sandbox, czeka na nadanie numeru
    śledzenia (polling), przeprowadza ją przez stan 'Nadana' -> 'Do odbioru',
    generuje 6-cyfrowy kod odbioru i zapisuje w bazie Odoo.
    """
    require_inpost_config()
    headers = {"Authorization": f"Bearer {INPOST_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "receiver": {
            "first_name": "Jan",
            "last_name": "Kowalski",
            "email": req.recipient_email,
            "phone": normalize_phone(req.recipient_phone) or "500600700",
        },
        "parcels": [{"template": req.size_template}],
        "custom_attributes": {
            "sending_method": "parcel_locker",
            "target_point": req.target_point.strip().upper() or "KRA01M",
        },
        "service": "inpost_locker_standard",
        "reference": f"PUDO-SIM-{random.randint(10000, 99999)}",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        create_resp = await client.post(
            f"{INPOST_SANDBOX_URL}/organizations/{INPOST_ORG_ID}/shipments",
            headers=headers,
            json=payload,
        )
        if create_resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=create_resp.status_code,
                detail=f"InPost Sandbox odrzucił utworzenie paczki: {create_resp.text}"
            )
        shipment_data = create_resp.json()
        shipment_id = shipment_data.get("id")

        # Czekamy chwilę aż InPost Sandbox opłaci z wirtualnego salda i nada 24-cyfrowy numer
        if shipment_id and not shipment_data.get("tracking_number"):
            for _ in range(6):
                await asyncio.sleep(1.5)
                poll_resp = await client.get(
                    f"{INPOST_SANDBOX_URL}/shipments/{shipment_id}",
                    headers=headers,
                )
                if poll_resp.status_code == 200:
                    shipment_data = poll_resp.json()
                    if shipment_data.get("tracking_number"):
                        break

    pkg = await bind_package_with_tag(
        db=db,
        inpost_data=shipment_data,
        mac_address=req.mac_address,
        direction="INBOUND",
        pudo_status="ready_to_pickup",
    )
    sync_msg = await sync_event_with_inpost(pkg, "SIMULATED_DISPATCHED_TO_READY_TO_PICKUP")
    await db.commit()
    await db.refresh(pkg)
    resp = PackageResponse.model_validate(pkg)
    resp.inpost_sync_info = sync_msg
    return resp


# ==============================================================================
# 8. WYDANIE PACZKI + KARTA QR/PIN KLIENTA + STANDARDOWE ENDPOINTY BLE
# ==============================================================================
@app.post("/api/packages/{package_id}/deliver", response_model=PackageResponse)
async def deliver_package(package_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.id == package_id))
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Nie znaleziono paczki.")

    pkg.status = "DELIVERED"
    pkg.inpost_pudo_status = (
        "collected_from_sender" if pkg.direction == "OUTBOUND" else "delivered"
    )
    pkg.mac_address = None
    pkg.last_seen = datetime.utcnow()

    sync_info = await sync_event_with_inpost(
        pkg,
        "PUDO_COLLECTED_BY_COURIER" if pkg.direction == "OUTBOUND" else "PUDO_DELIVERED_TO_CLIENT",
    )
    await db.commit()
    await db.refresh(pkg)
    resp = PackageResponse.model_validate(pkg)
    resp.inpost_sync_info = sync_info
    return resp


@app.get("/api/inpost/client-pass/{package_code}", response_class=HTMLResponse)
async def get_client_pass_html(package_code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.package_code == package_code))
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Nie znaleziono paczki.")
    last4 = normalize_phone(pkg.recipient_phone)[-4:] if pkg.recipient_phone else "brak"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={pkg.package_code}"
    return f"""
    <!DOCTYPE html>
    <html lang="pl">
    <head>
      <meta charset="utf-8"/>
      <title>Przepustka QR - {pkg.package_code}</title>
      <style>
        body {{ font-family: Arial, sans-serif; text-align: center; background: #f5f5f5; padding: 30px; }}
        .card {{ background: #fff; max-width: 420px; margin: auto; padding: 24px; border-radius: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); }}
        .badge {{ display: inline-block; padding: 6px 12px; border-radius: 20px; background: #ffcc00; font-weight: bold; }}
        .pin {{ font-size: 32px; letter-spacing: 6px; font-weight: bold; color: #111; margin: 12px 0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="badge">InPost PUDO • {pkg.direction} • Gabaryt {pkg.parcel_size or '-'}</div>
        <h2>Przesyłka InPost</h2>
        <p style="font-family: monospace; font-size: 14px;">{pkg.package_code}</p>
        <img src="{qr_url}" alt="QR paczki"/>
        <hr/>

        <p style="color:#555; font-size:12px;">
          Status PUDO: {pkg.inpost_pudo_status} | InPost API: {pkg.inpost_api_status or '-'} | MAC: {pkg.mac_address or 'Brak'}
        </p>
      </div>
    </body>
    </html>
    """


@app.get("/api/packages", response_model=List[PackageResponse])
async def get_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).order_by(Package.id.desc()))
    return result.scalars().all()


@app.post("/api/packages/register", response_model=PackageResponse)
async def register_package(req: PackageRegisterRequest, db: AsyncSession = Depends(get_db)):
    clean_mac = normalize_mac(req.mac_address)
    clean_code = req.package_code.strip()
    if not clean_mac or not clean_code:
        raise HTTPException(status_code=400, detail="Kod paczki i adres MAC nie mogą być puste")

    result = await db.execute(
        select(Package).where(or_(Package.mac_address == clean_mac, Package.package_code == clean_code))
    )
    existing = result.scalars().first()
    if existing:
        existing.mac_address = clean_mac
        existing.package_code = clean_code
        existing.status = "IDLE"
        existing.last_seen = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return existing

    new_pkg = Package(
        mac_address=clean_mac,
        package_code=clean_code,
        direction="INBOUND",
        status="IDLE",
        inpost_pudo_status="ready_to_pickup",
        battery_level=100,
        last_seen=datetime.utcnow(),
    )
    db.add(new_pkg)
    await db.commit()
    await db.refresh(new_pkg)
    return new_pkg


@app.post("/api/locate/{mac_address}", response_model=PackageResponse)
async def trigger_locate(mac_address: str, db: AsyncSession = Depends(get_db)):
    clean_mac = normalize_mac(mac_address)
    result = await db.execute(select(Package).where(Package.mac_address == clean_mac))
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Nie znaleziono paczki o podanym MAC")
    pkg.status = "LOCATING"
    pkg.last_seen = datetime.utcnow()
    await db.commit()
    await db.refresh(pkg)
    return pkg


@app.patch("/api/packages/{mac_address}/status", response_model=PackageResponse)
async def update_package_status(
    mac_address: str,
    req: PackageStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    clean_mac = normalize_mac(mac_address)
    result = await db.execute(select(Package).where(Package.mac_address == clean_mac))
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Nie znaleziono paczki o podanym MAC")
    pkg.status = req.status
    if req.battery_level is not None:
        pkg.battery_level = req.battery_level
    pkg.last_seen = datetime.utcnow()
    await db.commit()
    await db.refresh(pkg)
    return pkg


class BatteryUpdateRequest(BaseModel):
    battery_level: int


@app.patch("/api/packages/{mac_address}/battery", response_model=PackageResponse)
async def update_package_battery(
    mac_address: str,
    req: BatteryUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    if not (0 <= req.battery_level <= 100):
        raise HTTPException(status_code=400, detail="Poziom baterii musi być w zakresie 0-100.")
    clean_mac = normalize_mac(mac_address)
    result = await db.execute(select(Package).where(Package.mac_address == clean_mac))
    pkg = result.scalars().first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Nie znaleziono paczki o podanym MAC")
    pkg.battery_level = req.battery_level
    pkg.last_seen = datetime.utcnow()
    await db.commit()
    await db.refresh(pkg)
    return pkg
