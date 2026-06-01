CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    plan TEXT NOT NULL DEFAULT 'free',
    texts_limit INTEGER NOT NULL DEFAULT 30,
    texts_used INTEGER NOT NULL DEFAULT 0,
    free_limit INTEGER NOT NULL DEFAULT 30,
    free_used INTEGER NOT NULL DEFAULT 0,
    paid_balance INTEGER NOT NULL DEFAULT 0,
    last_free_reset_month TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
    id BIGSERIAL PRIMARY KEY,
    public_id TEXT UNIQUE NOT NULL,
    user_id BIGINT NOT NULL,
    request_text TEXT NOT NULL,
    response_text TEXT,
    source_type TEXT,
    source_title TEXT,
    source_link TEXT,
    detected_links TEXT,
    detected_domains TEXT,
    verdict TEXT,
    from_cache BOOLEAN NOT NULL DEFAULT FALSE,
    publication_status TEXT NOT NULL DEFAULT 'pending',
    published_message_id BIGINT,
    result_json TEXT,
    is_publishable BOOLEAN NOT NULL DEFAULT TRUE,
    media_json TEXT,
    media_group_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_requests_publication_status ON requests(publication_status);

ALTER TABLE requests ADD COLUMN IF NOT EXISTS result_json TEXT;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS is_publishable BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS media_json TEXT;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS media_group_id TEXT;

CREATE TABLE IF NOT EXISTS cache (
    text_hash TEXT PRIMARY KEY,
    original_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    verdict TEXT,
    result_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE cache ADD COLUMN IF NOT EXISTS result_json TEXT;

CREATE TABLE IF NOT EXISTS feedback (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    feedback_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT UNIQUE NOT NULL,
    user_id BIGINT NOT NULL,
    package_id TEXT NOT NULL,
    package_title TEXT NOT NULL,
    checks_added INTEGER NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'UAH',
    status TEXT NOT NULL DEFAULT 'created',
    liqpay_order_id TEXT,
    raw_data TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

CREATE TABLE IF NOT EXISTS checks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    content_hash TEXT,
    semantic_hash TEXT,
    source_url TEXT,
    source_domain TEXT,
    verdict TEXT,
    summary TEXT,
    full_report TEXT,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    check_id BIGINT,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    credits_spent INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd NUMERIC(14, 8) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (check_id) REFERENCES checks(id)
);

CREATE TABLE IF NOT EXISTS sources (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'website',
    url TEXT,
    domain TEXT,
    true_count INTEGER NOT NULL DEFAULT 0,
    fake_count INTEGER NOT NULL DEFAULT 0,
    manipulation_count INTEGER NOT NULL DEFAULT 0,
    unverified_count INTEGER NOT NULL DEFAULT 0,
    stale_count INTEGER NOT NULL DEFAULT 0,
    reliability_score NUMERIC(5, 2) NOT NULL DEFAULT 50,
    political_bias TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_domain ON sources(domain) WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sources_score ON sources(reliability_score);

CREATE TABLE IF NOT EXISTS source_mentions (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL,
    check_id BIGINT,
    url TEXT,
    title TEXT,
    stance TEXT NOT NULL DEFAULT 'unclear',
    verdict TEXT NOT NULL DEFAULT 'непідтверджено',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id),
    FOREIGN KEY (check_id) REFERENCES checks(id)
);

CREATE TABLE IF NOT EXISTS content_history (
    id BIGSERIAL PRIMARY KEY,
    content_hash TEXT UNIQUE NOT NULL,
    semantic_hash TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    original_context TEXT,
    original_url TEXT,
    times_seen INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tracked_events (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,
    importance_score INTEGER NOT NULL DEFAULT 1,
    keywords TEXT,
    entities_json TEXT,
    event_date TIMESTAMPTZ,
    monitoring_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watch_sources (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'website',
    url TEXT,
    priority INTEGER NOT NULL DEFAULT 1,
    political_group TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channel_settings (
    chat_id BIGINT PRIMARY KEY,
    chat_title TEXT,
    chat_type TEXT NOT NULL DEFAULT 'channel',
    mode TEXT NOT NULL DEFAULT 'manual',
    enabled_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT channel_settings_mode_check CHECK (mode IN ('manual', 'auto'))
);

CREATE TABLE IF NOT EXISTS quick_checks (
    id BIGSERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    post_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    verdict TEXT,
    short_note TEXT,
    marker_message_id BIGINT,
    public_id TEXT,
    was_reply BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    UNIQUE (chat_id, source_message_id)
);

ALTER TABLE quick_checks ADD COLUMN IF NOT EXISTS public_id TEXT;

CREATE INDEX IF NOT EXISTS idx_quick_checks_created_at ON quick_checks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quick_checks_public_id ON quick_checks(public_id);


CREATE TABLE IF NOT EXISTS donation_intents (
    user_id BIGINT PRIMARY KEY,
    -- Legacy compatibility column: active intent is consumed by the next photo and does not expire by time.
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS donation_submissions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    first_name TEXT,
    file_id TEXT NOT NULL,
    file_unique_id TEXT,
    caption TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    checks_added INTEGER,
    reviewed_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ,
    CONSTRAINT donation_submissions_status_check CHECK (status IN ('pending', 'approved', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_donation_submissions_user_id ON donation_submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_donation_submissions_status ON donation_submissions(status);
CREATE INDEX IF NOT EXISTS idx_donation_submissions_created_at ON donation_submissions(created_at DESC);
