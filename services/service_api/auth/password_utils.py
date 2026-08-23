"""Password hashing for ALFR3D user accounts.

Standardized on werkzeug's pbkdf2:sha256 (via werkzeug.security), not bcrypt/argon2, because the
`user` table's `password_hash` column already has one pre-existing hash in exactly this format
(user id=1, seeded in setup/createTables.sql) -- reusing it avoids introducing a second hashing
scheme with no migration story for that row.

The method is passed explicitly, not left to generate_password_hash()'s default -- verified
against werkzeug 3.1.6 (the version actually pinned in requirements.txt) that the default changed
to `scrypt`, whose output (~200+ chars) doesn't fit `user.password_hash`'s `VARCHAR(128)` column
and fails the UPDATE/INSERT outright. Found by testing Phase 5's claim/change-password/
admin-reset-password paths against a real deployment -- every one of them would have hit this.
pbkdf2:sha256's output comfortably fits the existing column (~104 chars), so no migration needed,
just pinning the method werkzeug used to default to.
"""

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(plain_password):
    return generate_password_hash(plain_password, method="pbkdf2:sha256")


def verify_password(plain_password, password_hash):
    if not password_hash:
        return False
    return check_password_hash(password_hash, plain_password)
