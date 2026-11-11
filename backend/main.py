import os
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime, select

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://admin:adminpassword@127.0.0.1:5432/locator_db"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# --- MODEL ORM ---
class Package(Base):
    __tablename__ = "packages"
    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String, unique=True, index=True)
    package_code = Column(String, unique=True)
    status = Column(String, default="IDLE")
    battery_level = Column(Integer, default=100)
    # Włączona obsługa stref czasowych zgodna z TIMESTAMP WITH TIME ZONE w init.sql
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# --- SCHEMATY PYDANTIC ---
class PackageCreate(BaseModel):
    mac_address: str
    package_code: str

class StatusUpdate(BaseModel):
    status: str
    battery_level: int | None = None

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

app = FastAPI(title="Smart Parcel Cloud API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/packages")
async def get_all_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package))
    return result.scalars().all()

@app.post("/api/packages/register")
async def register_package(pkg: PackageCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.mac_address == pkg.mac_address))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="MAC already registered")

    new_pkg = Package(mac_address=pkg.mac_address, package_code=pkg.package_code)
    db.add(new_pkg)
    await db.commit()
    return {"status": "success", "package_code": pkg.package_code}

@app.post("/api/locate/{mac_address}")
async def locate_package(mac_address: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.mac_address == mac_address))
    package = result.scalar_one_or_none()
    
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
        
    package.status = "LOCATING"
    package.last_seen = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "success", "message": f"Package {mac_address} marked as LOCATING"}

@app.patch("/api/packages/{mac_address}/status")
async def update_package_status(mac_address: str, payload: StatusUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.mac_address == mac_address))
    package = result.scalar_one_or_none()
    
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
        
    package.status = payload.status
    package.last_seen = datetime.now(timezone.utc)
    if payload.battery_level is not None:
        package.battery_level = payload.battery_level
        
    await db.commit()
    return {"status": "success", "new_status": package.status}