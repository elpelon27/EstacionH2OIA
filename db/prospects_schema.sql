-- ============================================================
-- PROSPECTS DB — Capa bruta de prospección B2B (compartible entre dominios)
-- Regla de Oro: los DATOS nunca se mezclan entre dominios (h2o/trading/agro);
-- cada fila lleva su dominio y las herramientas futuras filtran SIEMPRE por él.
-- Nombres comunes y estables para que skills futuros (ej. publicidad/
-- marketing por rutas) lean estas tablas sin romperse.
-- Convención: prospección = "prospect_*", un registro = 1 negocio geolocalizado.
-- ============================================================

-- Metadatos de la fuente/campaña de scrapeo (Google Maps Scraper, etc.)
CREATE TABLE IF NOT EXISTS prospect_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool TEXT NOT NULL,               -- 'google_maps_scraper', 'manual', 'agent_reach', ...
    query TEXT,                       -- término buscado ej. 'farmacias Caracas'
    dominio TEXT NOT NULL CHECK(dominio IN ('h2o','trading','agro','compartido')),
    run_started_at TEXT NOT NULL,
    notes TEXT
);

-- Tabla principal: 1 fila = 1 negocio prospecto
CREATE TABLE IF NOT EXISTS prospects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES prospect_sources(id),
    dominio TEXT NOT NULL CHECK(dominio IN ('h2o','trading','agro','compartido')),
    -- Identidad del negocio
    business_name TEXT NOT NULL,
    business_category TEXT,           -- 'farmacia', 'condominio', 'restaurante'...
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT DEFAULT 'Venezuela',
    postal_code TEXT,
    -- Geolocalización (clave para skills de rutas/publicidad por zona)
    latitude REAL,
    longitude REAL,
    -- Contacto
    phone TEXT,
    website TEXT,
    email TEXT,
    -- Google Maps specifics
    gmaps_place_id TEXT UNIQUE,       -- id estable de Google para dedupe
    gmaps_url TEXT,
    rating REAL,
    review_count INTEGER,
    -- Clasificación comercial (para el skill de publicidad)
    estimated_size TEXT,              -- 'small','medium','large'
    prospect_status TEXT DEFAULT 'new'
        CHECK(prospect_status IN ('new','qualified','contacted','converted','discarded')),
    priority REAL DEFAULT 0.0,        -- score de prioridad asignable por otros skills
    -- Auditoría
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_prospects_dominio ON prospects(dominio);
CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(prospect_status);
CREATE INDEX IF NOT EXISTS idx_prospects_category ON prospects(business_category);
CREATE INDEX IF NOT EXISTS idx_prospects_city ON prospects(city);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prospects_dedupe
    ON prospects(gmaps_place_id) WHERE gmaps_place_id IS NOT NULL;

-- Historial de observaciones del scraper (cambios de rating, teléfonos, etc.)
CREATE TABLE IF NOT EXISTS prospect_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    visited_at TEXT NOT NULL DEFAULT (datetime('now')),
    observed_rating REAL,
    observed_review_count INTEGER,
    observed_phone TEXT,
    raw_data_json TEXT,               -- snapshot crudo completo de esa corrida
    source_id INTEGER REFERENCES prospect_sources(id)
);
CREATE INDEX IF NOT EXISTS idx_visits_prospect ON prospect_visits(prospect_id);

-- Bitácora de acciones comerciales (la usará el skill de publicidad futuro)
CREATE TABLE IF NOT EXISTS prospect_outreach_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id),
    action TEXT NOT NULL,             -- 'whatsapp_sent','odoo_sync','call','visit'
    channel TEXT,                      -- 'waha','odoo_crm','manual'
    performed_by TEXT DEFAULT 'system',
    performed_at TEXT NOT NULL DEFAULT (datetime('now')),
    result TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_outreach_prospect ON prospect_outreach_log(prospect_id);
