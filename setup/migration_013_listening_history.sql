-- Listening history for the ALFR3D music recommender.
CREATE TABLE IF NOT EXISTS listening_history (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    track_id VARCHAR(64) NOT NULL,
    track_name VARCHAR(255) DEFAULT NULL,
    album VARCHAR(255) DEFAULT NULL,
    artist VARCHAR(255) DEFAULT NULL,
    played_at DATETIME NOT NULL,
    context VARCHAR(32) DEFAULT NULL COMMENT 'time of day: morning/day/evening/night',
    source VARCHAR(32) DEFAULT 'spotify',
    INDEX idx_listening_track (track_id),
    INDEX idx_listening_played_at (played_at),
    INDEX idx_listening_artist (artist)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
