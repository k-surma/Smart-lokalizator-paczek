import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://odoo:odoopassword@db-odoo:5432/odoo_db"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


# Model wskazujący na tę samą tabelę 'packages', z której korzysta moduł Odoo
class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String(17), unique=True, nullable=False, index=True)
    package_code = Column(String(50), unique=True, nullable=False)
    status = Column(String(20), default="IDLE", nullable=False)
    battery_level = Column(Integer, default=100)
    # DateTime(timezone=False) jest w 100% kompatybilne z fields.Datetime w Odoo 17
    last_seen = Column(DateTime(timezone=False), default=datetime.utcnow)


class PackageRegisterRequest(BaseModel):
    mac_address: str
    package_code: str


class PackageStatusUpdateRequest(BaseModel):
    status: str
    battery_level: Optional[int] = None


class PackageResponse(BaseModel):
    id: int
    mac_address: str
    package_code: str
    status: str
    battery_level: Optional[int]
    last_seen: Optional[datetime]

    class Config:
        from_attributes = True


app = FastAPI(title="Smart Parcel Cloud API (Shared Odoo DB)")

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

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Package).where(Package.mac_address == "AA:BB:CC:DD:EE:FF")
        )
        if not result.scalar_one_or_none():
            session.add(
                Package(
                    mac_address="AA:BB:CC:DD:EE:FF",
                    package_code="PKG-2026-001",
                    status="IDLE",
                    battery_level=100,
                    last_seen=datetime.utcnow(),
                )
            )
            await session.commit()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@app.get("/api/packages", response_model=List[PackageResponse])
async def get_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).order_by(Package.id.desc()))
    return result.scalars().all()


@app.post("/api/packages/register", response_model=PackageResponse)
async def register_package(req: PackageRegisterRequest, db: AsyncSession = Depends(get_db)):
    clean_mac = req.mac_address.strip().upper()
    result = await db.execute(select(Package).where(Package.mac_address == clean_mac))
    existing = result.scalar_one_or_none()

    if existing:
        existing.package_code = req.package_code.strip()
        existing.status = "IDLE"
        existing.last_seen = datetime.utcnow()
        await db.commit()
        await db.refresh(existing)
        return existing

    new_pkg = Package(
        mac_address=clean_mac,
        package_code=req.package_code.strip(),
        status="IDLE",
        battery_level=100,
        last_seen=datetime.utcnow(),
    )
    db.add(new_pkg)
    await db.commit()
    await db.refresh(new_pkg)
    return new_pkg


@app.post("/api/locate/{mac_address}", response_model=PackageResponse)
async def trigger_locate(mac_address: str, db: AsyncSession = Depends(get_db)):
    clean_mac = mac_address.strip().upper()
    result = await db.execute(select(Package).where(Package.mac_address == clean_mac))
    pkg = result.scalar_one_or_none()

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
    clean_mac = mac_address.strip().upper()
    result = await db.execute(select(Package).where(Package.mac_address == clean_mac))
    pkg = result.scalar_one_or_none()

    if not pkg:
        raise HTTPException(status_code=404, detail="Nie znaleziono paczki o podanym MAC")

    pkg.status = req.status.strip().upper()
    if req.battery_level is not None:
        pkg.battery_level = req.battery_level
    pkg.last_seen = datetime.utcnow()

    await db.commit()
    await db.refresh(pkg)
    return pkg