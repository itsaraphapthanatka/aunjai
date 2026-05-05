-- YouTube Channel Monitoring
CREATE TABLE IF NOT EXISTS monitored_channels (
    id SERIAL PRIMARY KEY,
    channel_url TEXT UNIQUE NOT NULL,
    channel_name VARCHAR(255),
    interval_minutes INT DEFAULT 60,
    last_video_id VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_monitored_channels_active ON monitored_channels(is_active);
