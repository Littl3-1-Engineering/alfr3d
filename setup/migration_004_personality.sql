-- Migration: Personality Matrix
-- Adds personality traits, mood context, and LLM configuration

-- Increase config.value size for API keys
ALTER TABLE config MODIFY COLUMN value VARCHAR(512);

-- Add LLM config entries
INSERT INTO config (name, value) VALUES ('llm_api_key', '');
INSERT INTO config (name, value) VALUES ('llm_usage_limit', '10');

-- Create personality table
CREATE TABLE IF NOT EXISTS personality (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64),
    type ENUM('preset', 'current') DEFAULT 'preset',
    environment_id INT NULL,

    sarcasm FLOAT DEFAULT 0.0,
    formality FLOAT DEFAULT 0.5,
    warmth FLOAT DEFAULT 0.5,
    patience FLOAT DEFAULT 1.0,

    linguistic_style VARCHAR(256),
    forbidden_words VARCHAR(512),
    verbal_tics VARCHAR(512),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Create context table
CREATE TABLE IF NOT EXISTS context (
    id INT AUTO_INCREMENT PRIMARY KEY,
    environment_id INT UNIQUE,

    repeat_count INT DEFAULT 0,
    hour INT DEFAULT 12,
    weather VARCHAR(64),
    mood VARCHAR(32) DEFAULT 'neutral',
    last_error_count INT DEFAULT 0,
    llm_calls_today INT DEFAULT 0,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Seed personality presets
INSERT INTO personality (name, type, sarcasm, formality, warmth, patience, linguistic_style, forbidden_words, verbal_tics) VALUES
('Butler', 'preset', 0.3, 1.0, 0.4, 0.8, 'Archaic Butler', 'stupid,dumb,idiot', 'I presume,Your Grace'),
('Maid', 'preset', 0.1, 0.8, 0.9, 0.9, 'Polite Maid', 'stupid,dumb', 'Of course,Right away'),
('Snarky', 'preset', 1.0, 0.2, 0.1, 0.2, 'Dry wit', '', 'Groundbreaking,Shocking truly'),
('Friendly', 'preset', 0.1, 0.3, 1.0, 0.9, 'Casual pal', '', 'Hey buddy,You rock');

-- Create initial current personality (copies Butler by default)
INSERT INTO personality (name, type)
SELECT 'Current', 'current' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM personality WHERE type = 'current');

-- Create initial context for first environment
INSERT INTO context (environment_id)
SELECT id FROM environment LIMIT 1
ON DUPLICATE KEY UPDATE environment_id = environment_id;
