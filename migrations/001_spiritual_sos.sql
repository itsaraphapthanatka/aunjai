-- Migration 001: Spiritual SOS Tables
-- Created for TASK-001 Integration — Spiritual SOS Classifier

-- spiritual_states table: tracks user's spiritual journey C-stage
CREATE TABLE IF NOT EXISTS spiritual_states (
    line_uid VARCHAR(100) PRIMARY KEY,
    c_stage VARCHAR(2),
    believed_at TIMESTAMP,
    c4_follow_up_due_at TIMESTAMP,
    c4_follow_up_count INT DEFAULT 0,
    context_window JSONB DEFAULT '[]',
    updated_at TIMESTAMP DEFAULT NOW()
);

-- sos_cases table (unified physical + spiritual)
CREATE TABLE IF NOT EXISTS sos_cases (
    id SERIAL PRIMARY KEY,
    line_uid VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL DEFAULT 'physical',
    level VARCHAR(20),
    c_stage VARCHAR(2),
    trigger_message TEXT,
    confidence FLOAT,
    status VARCHAR(20) DEFAULT 'open',
    claimed_by VARCHAR(100),
    claimed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_sos_cases_type ON sos_cases(type);
CREATE INDEX IF NOT EXISTS idx_sos_cases_status ON sos_cases(status);
CREATE INDEX IF NOT EXISTS idx_sos_cases_line_uid ON sos_cases(line_uid);
