import asyncio
import random
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, select

# --- DATABASE CONFIGURATION (SQLAlchemy + Asyncpg) ---
# Connection string points to localhost on port 5432
DATABASE_URL = "postgresql+asyncpg://admin:adminpassword@127.0.0.1:5432/locator_db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# --- ORM MODELS ---
class Package(Base):
    __tablename__ = "packages"
    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String, unique=True, index=True)
    package_code = Column(String, unique=True)
    status = Column(String)
    last_x = Column(Float)
    last_y = Column(Float)
    battery_level = Column(Integer)
    last_seen = Column(DateTime)

# Dependency to inject database session into endpoints
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# --- APP INITIALIZATION ---
app = FastAPI(title="Smart Parcel Tracker API")

# Flag for future physical hardware integration
HARDWARE_CONNECTED = False

# --- HARDWARE SIMULATOR (Mock) ---
async def hardware_simulator():
    """
    Mocks the XIAO device (Gateway A) connected via USB.
    Generates random RSSI readings and updates the database every 2 seconds.
    """
    print("[HARDWARE] Gateway A simulator started (No physical COM port detected)")
    
    while True:
        await asyncio.sleep(2.0)
        
        fake_mac = "AA:BB:CC:DD:EE:FF"
        rssi_a, rssi_b, rssi_c = random.randint(-90, -40), random.randint(-90, -40), random.randint(-90, -40)
        serial_string = f"MAC:{fake_mac}|A:{rssi_a},B:{rssi_b},C:{rssi_c}"
        
        print(f"[SERIAL RX MOCK] Received from USB: {serial_string}")
        
        # Calculate mock position (to be replaced by NumPy trilateration)
        calc_x = round(random.uniform(0.0, 10.0), 2)
        calc_y = round(random.uniform(0.0, 10.0), 2)
        
        # Save mock position to the database
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Package).where(Package.mac_address == fake_mac))
            package = result.scalar_one_or_none()
            
            if package:
                package.last_x = calc_x
                package.last_y = calc_y
                package.last_seen = datetime.utcnow()
                await session.commit()
                print(f"[DB] Updated MAC {fake_mac} in DB -> X: {calc_x}, Y: {calc_y}")
            else:
                print(f"[DB WARN] Package {fake_mac} not found in database. Seed data missing?")

@app.on_event("startup")
async def startup_event():
    if not HARDWARE_CONNECTED:
        asyncio.create_task(hardware_simulator())

# --- REST API ENDPOINTS FOR ODOO ---

@app.get("/api/packages")
async def get_all_packages(db: AsyncSession = Depends(get_db)):
    """
    Returns a list of all registered packages from the database.
    """
    result = await db.execute(select(Package))
    packages = result.scalars().all()
    return packages

@app.post("/api/locate/{mac_address}")
async def locate_package(mac_address: str, db: AsyncSession = Depends(get_db)):
    """
    Endpoint triggered from Odoo. 
    Changes package status to LOCATING and simulates dispatching a hardware command.
    """
    result = await db.execute(select(Package).where(Package.mac_address == mac_address))
    package = result.scalar_one_or_none()
    
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
        
    package.status = "LOCATING"
    await db.commit()

    command_to_send = f"LOCATE:{mac_address}\n"
    if not HARDWARE_CONNECTED:
        print(f"[SERIAL TX MOCK] Sent via USB: {command_to_send.strip()}")
    else:
        # Future hardware integration: serial_port.write(command_to_send.encode())
        pass
    
    return {"status": "success", "message": f"Locate command dispatched for {mac_address}"}

@app.get("/api/packages/{mac_address}/position")
async def get_position(mac_address: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieves the latest calculated position of a specific package from the database.
    """
    result = await db.execute(select(Package).where(Package.mac_address == mac_address))
    package = result.scalar_one_or_none()
    
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
        
    return {
        "mac": package.mac_address,
        "package_code": package.package_code,
        "x": package.last_x,
        "y": package.last_y,
        "battery": package.battery_level,
        "status": package.status,
        "timestamp": package.last_seen
    }