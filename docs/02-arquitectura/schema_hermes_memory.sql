CREATE TABLE consolidation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sessions_processed INTEGER NOT NULL,
    chunks_read INTEGER NOT NULL,
    facts_extracted INTEGER NOT NULL,
    facts_certain INTEGER DEFAULT 0,
    facts_inferred INTEGER DEFAULT 0,
    facts_tentative INTEGER DEFAULT 0,
    conflicts_detected INTEGER DEFAULT 0,
    errors TEXT,
    duration_ms INTEGER
);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE traces_hot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    task_summary TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    tier TEXT CHECK(tier IN ('T1','T2','T3')),
    steps_count INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_traces_hot_session ON traces_hot(session_id);
CREATE INDEX idx_traces_hot_created ON traces_hot(created_at);
CREATE TABLE traces_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    compressed_summary TEXT NOT NULL,
    original_id INTEGER REFERENCES traces_hot(id),
    archived_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE cron_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_name TEXT NOT NULL,
    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN NOT NULL,
    duration_ms INTEGER,
    output_hash TEXT,
    error TEXT
);
CREATE INDEX idx_cron_runs_name_date ON cron_runs(cron_name, executed_at);
CREATE TABLE archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_qdrant_id TEXT,
    fact_markdown TEXT NOT NULL,
    relevance_at_archive REAL NOT NULL,
    archived_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    rationale TEXT
);
CREATE TABLE warming_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    chunks_prefetched INTEGER,
    cache_hits INTEGER,
    cache_misses INTEGER,
    miss_rate REAL,
    logged_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
