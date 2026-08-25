CREATE TABLE interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id TEXT NOT NULL,
    channel TEXT CHECK(channel IN ('whatsapp','telegram','inter_agent','r4','odoo','system')),
    message_hash TEXT UNIQUE NOT NULL,
    payload_preview TEXT,
    intent_detected TEXT,
    commitment_made TEXT,
    emotional_tag TEXT CHECK(emotional_tag IN ('frustrated','urgent','neutral','satisfied','unknown')),
    resolution_status TEXT CHECK(resolution_status IN ('pending','fulfilled','broken','escalated','expired')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    resolved_by TEXT
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE INDEX idx_interactions_actor ON interactions(actor_id);
CREATE INDEX idx_interactions_status ON interactions(resolution_status);
CREATE INDEX idx_interactions_pending ON interactions(resolution_status, created_at) WHERE resolution_status = 'pending';
CREATE TABLE conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    new_fact_qdrant_id TEXT NOT NULL,
    conflicting_fact_qdrant_id TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    new_fact_summary TEXT NOT NULL,
    conflicting_fact_summary TEXT NOT NULL,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved BOOLEAN DEFAULT 0,
    resolution TEXT,
    resolved_at DATETIME
);
CREATE INDEX idx_conflicts_unresolved ON conflicts(resolved) WHERE resolved = 0;
CREATE TABLE interactions_archive (
    id INTEGER PRIMARY KEY,
    actor_id TEXT,
    channel TEXT,
    message_hash TEXT,
    payload_preview TEXT,
    intent_detected TEXT,
    commitment_made TEXT,
    emotional_tag TEXT,
    resolution_status TEXT,
    created_at DATETIME,
    resolved_at DATETIME,
    archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
