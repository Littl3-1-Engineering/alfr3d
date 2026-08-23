-- Migration 021: Widen secret-bearing columns for Fernet ciphertext overhead
--
-- config.value is VARCHAR(512), sized for plaintext API keys. Fernet ciphertext
-- (base64 of version+timestamp+IV+padded-ciphertext+HMAC) adds real overhead -- a long
-- HA long-lived-access-token could land close to or over 512 once encrypted. Widen to TEXT.
-- esphome_nodes.psk (VARCHAR(255)) gets the same encryption treatment; widen for headroom too.
-- See todo/todo_encrypt_secrets_at_rest.md.

ALTER TABLE `config` MODIFY `value` TEXT NULL DEFAULT NULL;
ALTER TABLE `esphome_nodes` MODIFY `psk` VARCHAR(512) NULL DEFAULT NULL;
