-- Speaker groups for whole-home audio casting (Phase 3).
CREATE TABLE IF NOT EXISTS speaker_groups (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    entities JSON NOT NULL COMMENT 'array of HA media_player entity_ids',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_speaker_group_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
