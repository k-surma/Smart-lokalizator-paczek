import asyncio
import random
from fastapi import FastAPI, BackgroundTasks

app = FastAPI(title="Smart Parcel Tracker API")

# Global flag for hardware simulation
HARDWARE_CONNECTED = False

# --- 1. HARDWARE SIMULATOR (Mock) ---
async def hardware_simulator():
    """
    This background task mocks the XIAO device (Gateway A) connected via USB.
    It generates random RSSI readings every 2 seconds.
    """
    print("[HARDWARE] Gateway A simulator started (No physical COM port detected)")
    
    while True:
        await asyncio.sleep(2.0)
        
        # Simulating that the hardware detected a package with a specific MAC address
        fake_mac = "AA:BB:CC:DD:EE:FF"
        
        # Generating random RSSI values from -40 (close) to -90 (far)
        rssi_a = random.randint(-90, -40)
        rssi_b = random.randint(-90, -40)
        rssi_c = random.randint(-90, -40)
        
        # This represents the raw string that will come from the real Serial port
        serial_string = f"MAC:{fake_mac}|A:{rssi_a},B:{rssi_b},C:{rssi_c}"
        
        print(f"[SERIAL RX MOCK] Received from USB: {serial_string}")
        
        # TODO IN THE FUTURE:
        # 1. Parse the incoming string
        # 2. Calculate X, Y coordinates using NumPy (Trilateration)
        # 3. Save the results to Redis / PostgreSQL

@app.on_event("startup")
async def startup_event():
    """
    Starts the background hardware simulator immediately after server startup 
    if the real hardware is not connected.
    """
    if not HARDWARE_CONNECTED:
        asyncio.create_task(hardware_simulator())


# --- 2. REST API ENDPOINTS FOR ODOO ---

@app.post("/api/locate/{mac_address}")
async def locate_package(mac_address: str):
    """
    Endpoint triggered by the warehouse worker from the Odoo interface.
    """
    # This is the command format that will be sent via USB to the real XIAO
    command_to_send = f"LOCATE:{mac_address}\n"
    
    if not HARDWARE_CONNECTED:
        print(f"[SERIAL TX MOCK] Sent via USB: {command_to_send.strip()}")
        return {
            "status": "success", 
            "message": f"Locate command sent to simulator for MAC: {mac_address}"
        }
    else:
        # Future hardware code: 
        # serial_port.write(command_to_send.encode())
        pass
        
    return {"status": "success", "message": "Command sent to physical hardware"}

@app.get("/api/packages/{mac_address}/position")
async def get_position(mac_address: str):
    """
    Endpoint to retrieve the current calculated package position (for the Odoo map).
    """
    # Returning mock data for now. 
    # Eventually, this will be fetched from PostgreSQL/Redis.
    return {
        "mac": mac_address,
        "x": 2.5,
        "y": 4.1,
        "timestamp": "2026-10-26T14:30:00Z"
    }