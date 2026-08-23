"""Password hashing for ALFR3D user accounts.

Standardized on werkzeug's pbkdf2:sha256 (via werkzeug.security), not bcrypt/argon2, because the
`user` table's `password_hash` column already has one pre-existing hash in exactly this format
(user id=1, seeded in setup/createTables.sql) -- reusing it avoids introducing a second hashing
scheme with no migration story for that row.
"""

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(plain_password):
    return generate_password_hash(plain_password)


def verify_password(plain_password, password_hash):
    if not password_hash:
        return False
    return check_password_hash(password_hash, plain_password)
