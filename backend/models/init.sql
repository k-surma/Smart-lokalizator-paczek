DROP TABLE IF EXISTS location_history CASCADE;
DROP TABLE IF EXISTS gateways CASCADE;
DROP TABLE IF EXISTS packages CASCADE;

CREATE TABLE packages (
    id SERIAL PRIMARY KEY,
    mac_address VARCHAR(17) UNIQUE NOT NULL,
    package_code VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'IDLE',
    battery_level INTEGER DEFAULT 100,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_packages_mac ON packages(mac_address);

INSERT INTO packages (mac_address, package_code, status) VALUES
('AA:BB:CC:DD:EE:FF', 'PKG-2026-001', 'IDLE');