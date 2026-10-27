-- Clean up existing tables if re-initializing
DROP TABLE IF EXISTS location_history CASCADE;
DROP TABLE IF EXISTS packages CASCADE;
DROP TABLE IF EXISTS gateways CASCADE;

-- 1. Gateways table (Reference points for trilateration)
CREATE TABLE gateways (
    id VARCHAR(10) PRIMARY KEY,            -- 'A', 'B', 'C'
    name VARCHAR(50) NOT NULL,
    pos_x FLOAT NOT NULL,                  -- X coordinate in meters
    pos_y FLOAT NOT NULL,                  -- Y coordinate in meters
    is_aggregator BOOLEAN DEFAULT FALSE,   -- True for Gateway A (USB connected)
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Packages table (Active BLE Tags)
CREATE TABLE packages (
    id SERIAL PRIMARY KEY,
    mac_address VARCHAR(17) UNIQUE NOT NULL, -- Format: AA:BB:CC:DD:EE:FF
    package_code VARCHAR(50) UNIQUE NOT NULL, -- Odoo Parcel Barcode / ID
    status VARCHAR(20) DEFAULT 'IDLE',       -- IDLE, LOCATING, FOUND, MISSING
    last_x FLOAT,                            -- Last calculated X position (m)
    last_y FLOAT,                            -- Last calculated Y position (m)
    battery_level INTEGER DEFAULT 100,       -- Percentage (0-100)
    last_seen TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Location History table (Audit log & movement tracking)
CREATE TABLE location_history (
    id SERIAL PRIMARY KEY,
    package_id INTEGER REFERENCES packages(id) ON DELETE CASCADE,
    pos_x FLOAT NOT NULL,
    pos_y FLOAT NOT NULL,
    rssi_a INTEGER,
    rssi_b INTEGER,
    rssi_c INTEGER,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries from FastAPI / Odoo
CREATE INDEX idx_packages_mac ON packages(mac_address);
CREATE INDEX idx_packages_code ON packages(package_code);
CREATE INDEX idx_history_package_time ON location_history(package_id, recorded_at DESC);

-- Seed initial reference data for 3 XIAO Gateways (Assuming a 10m x 10m room)
INSERT INTO gateways (id, name, pos_x, pos_y, is_aggregator) VALUES
('A', 'Gateway A (Aggregator USB)', 0.0, 0.0, TRUE),
('B', 'Gateway B (Wall Corner 1)', 10.0, 0.0, FALSE),
('C', 'Gateway C (Wall Corner 2)', 5.0, 10.0, FALSE);

-- Seed a test package for the simulator
INSERT INTO packages (mac_address, package_code, status, last_x, last_y, last_seen) VALUES
('AA:BB:CC:DD:EE:FF', 'PKG-2026-001', 'IDLE', 2.5, 4.1, CURRENT_TIMESTAMP);