-- Migration 022: Auth + RBAC -- refresh_tokens table
--
-- Opaque JWT refresh tokens (access tokens are stateless and never stored). Only a SHA-256 hash
-- of the token is stored, never the raw value, so a DB read alone can't be replayed.
-- See todo/todo_auth_rbac.md.

CREATE TABLE `refresh_tokens` (
  `id` INTEGER UNIQUE AUTO_INCREMENT,
  `user_id` INTEGER NOT NULL,
  `token_hash` VARCHAR(64) NOT NULL,
  `issued_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `expires_at` DATETIME NOT NULL,
  `revoked_at` DATETIME NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_token_hash` (`token_hash`)
);

ALTER TABLE `refresh_tokens` ADD FOREIGN KEY (user_id) REFERENCES `user` (`id`);

-- Data fix: the seed row for user id=1 (`athos`) was inserted with the surrounding quote
-- characters from a copy-pasted Python repr() included as part of the string value itself
-- (MySQL's `\'...\'` escaping makes them literal content, not just delimiters), so
-- werkzeug.security.check_password_hash() would never match it against the real password.
-- Only touches the row if it still has exactly that erroneous value -- a no-op if the
-- password's already been reset through a real flow since.
UPDATE `user`
SET `password_hash` = 'pbkdf2:sha256:260000$EVLamhqzR2ib572V$29ecaf8e9ef809496eebf2cc1dafc1c865e0efa0184a89dcca63492ced5290bf'
WHERE `id` = 1
  AND `password_hash` = '\'pbkdf2:sha256:260000$EVLamhqzR2ib572V$29ecaf8e9ef809496eebf2cc1dafc1c865e0efa0184a89dcca63492ced5290bf\'';
