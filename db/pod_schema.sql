-- Esquema POD (Proof of Delivery) — Bloque 2 Fase 2.1
-- Tabla principal de notas de entrega digital.
CREATE TABLE IF NOT EXISTS pod_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id INTEGER NOT NULL,
    client_phone TEXT,
    client_name TEXT,
    client_cedula TEXT,
    signature_canvas TEXT,            -- base64 PNG de la firma
    photo_proof TEXT,                 -- path a archivo o base64
    product_details_json TEXT,        -- recargas, hielo, precios, total
    empty_bottles_received INTEGER DEFAULT 0,  -- swap de vacíos
    caps_received INTEGER DEFAULT 0,           -- tapas devueltas
    previous_balance_eur REAL,       -- saldo anterior si cliente con crédito
    total_eur REAL,
    total_ves REAL,                   -- total en Bs a tasa del día
    signed_at TEXT,                   -- ISO8601
    synced_to_odoo INTEGER DEFAULT 0,
    synced_at TEXT,
    offline_created INTEGER DEFAULT 0,
    vehicle_id INTEGER,
    pod_status TEXT DEFAULT 'pending',  -- pending/signed/photo_only/refused
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (delivery_id) REFERENCES deliveries(id)
);
CREATE INDEX IF NOT EXISTS idx_pod_delivery ON pod_records(delivery_id);
CREATE INDEX IF NOT EXISTS idx_pod_status ON pod_records(pod_status);
CREATE INDEX IF NOT EXISTS idx_pod_synced ON pod_records(synced_to_odoo);
