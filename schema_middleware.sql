-- Refined Database Schema for Nong Unjai Middleware
-- Based on MAAC OpenAPI (cresclaben.apib)

-- 1. Contacts & Profiles
CREATE TABLE IF NOT EXISTS contacts (
    line_uid VARCHAR(33) PRIMARY KEY,
    line_display_name VARCHAR(255),
    display_name VARCHAR(255),
    email VARCHAR(255),
    mobile VARCHAR(50),
    customer_id VARCHAR(100),
    gender VARCHAR(10),
    birthday DATE,
    status VARCHAR(20), -- follow, auth, unfollow
    tags JSONB, -- list of tag names
    tags_detail JSONB, -- list of objects {name, tagged_at}
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tags
CREATE TABLE IF NOT EXISTS tags (
    tag_id INT PRIMARY KEY,
    tag_name VARCHAR(100) UNIQUE,
    available_days INT
);

-- 3. Contact-Tag Mapping (Many-to-Many)
CREATE TABLE IF NOT EXISTS contact_tags (
    line_uid VARCHAR(33) REFERENCES contacts(line_uid),
    tag_id INT REFERENCES tags(tag_id),
    tagged_at TIMESTAMP,
    expired_at TIMESTAMP,
    PRIMARY KEY (line_uid, tag_id)
);

-- 4. Message Events (Campaigns)
CREATE TABLE IF NOT EXISTS message_events (
    event_id INT PRIMARY KEY,
    name VARCHAR(255),
    created_at TIMESTAMP,
    last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Performance Report (Total Metrics)
CREATE TABLE IF NOT EXISTS event_performance_total (
    id SERIAL PRIMARY KEY,
    event_id INT REFERENCES message_events(event_id),
    report_start_date DATE,
    report_end_date DATE,
    opens INT DEFAULT 0,
    clicks INT DEFAULT 0,
    unique_clicks INT DEFAULT 0,
    adds_to_cart INT DEFAULT 0,
    transactions INT DEFAULT 0,
    transaction_revenue DECIMAL(15, 2) DEFAULT 0.00,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Link-Level Performance (URLs)
CREATE TABLE IF NOT EXISTS event_performance_urls (
    url_id INT PRIMARY KEY,
    event_id INT REFERENCES message_events(event_id),
    link_index INT,
    destination_url TEXT,
    utm_campaign VARCHAR(100),
    utm_source VARCHAR(100),
    utm_medium VARCHAR(100),
    utm_content VARCHAR(100),
    clicks INT DEFAULT 0,
    unique_clicks INT DEFAULT 0,
    adds_to_cart INT DEFAULT 0,
    transactions INT DEFAULT 0,
    transaction_revenue DECIMAL(15, 2) DEFAULT 0.00
);

-- 7. Message Bubbles Performance
CREATE TABLE IF NOT EXISTS event_performance_bubbles (
    bubble_id INT PRIMARY KEY,
    event_id INT REFERENCES message_events(event_id),
    message_label TEXT,
    clicks INT DEFAULT 0
);
