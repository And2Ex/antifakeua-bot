-- AntiFakeUA lightweight analytics migration.
-- Safe to run multiple times in SQLite.

CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    content_hash TEXT,
    semantic_hash TEXT,
    source_url TEXT,
    source_domain TEXT,
    verdict TEXT,
    summary TEXT,
    full_report TEXT,
    is_public INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    check_id INTEGER,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    credits_spent INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (check_id) REFERENCES checks(id)
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'website',
    url TEXT,
    domain TEXT,
    true_count INTEGER DEFAULT 0,
    fake_count INTEGER DEFAULT 0,
    manipulation_count INTEGER DEFAULT 0,
    unverified_count INTEGER DEFAULT 0,
    stale_count INTEGER DEFAULT 0,
    reliability_score REAL DEFAULT 50,
    political_bias TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain) WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sources_score ON sources(reliability_score);

CREATE TABLE IF NOT EXISTS source_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    check_id INTEGER,
    url TEXT,
    title TEXT,
    stance TEXT DEFAULT 'unclear',
    verdict TEXT DEFAULT 'непідтверджено',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (check_id) REFERENCES checks(id)
);

CREATE TABLE IF NOT EXISTS content_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    semantic_hash TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    original_context TEXT,
    original_url TEXT,
    times_seen INTEGER DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_content_history_hash ON content_history(content_hash);

CREATE TABLE IF NOT EXISTS tracked_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    importance_score INTEGER DEFAULT 1,
    keywords TEXT,
    entities_json TEXT,
    event_date TEXT,
    monitoring_until TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watch_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'website',
    url TEXT,
    priority INTEGER DEFAULT 1,
    political_group TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);
