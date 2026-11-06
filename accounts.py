
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().with_name("accounts.db")
VERIFICATION_CODE_TTL = timedelta(minutes=15)
MAX_VERIFICATION_ATTEMPTS = 5


def _new_verification_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _new_verification_generation():
    return secrets.token_hex(16)


def _verification_expiration():
    return (datetime.now(timezone.utc) + VERIFICATION_CODE_TTL).isoformat()


def initialize_database():
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_verifications (
                user_id INTEGER PRIMARY KEY,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_registrations (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                verification_code_hash TEXT NOT NULL,
                verification_generation TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                delivery_confirmed INTEGER NOT NULL DEFAULT 0,
                UNIQUE (username COLLATE NOCASE),
                UNIQUE (email COLLATE NOCASE)
            )
        """)

        connection.commit()
    finally:
        connection.close()


def create_pending_registration(connection, username, email, password):
    password_hash = generate_password_hash(password)
    code = _new_verification_code()
    code_hash = generate_password_hash(code)
    generation = _new_verification_generation()
    cursor = connection.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    try:
        cursor.execute("""
            SELECT 1 FROM users
            WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
            UNION ALL
            SELECT 1 FROM pending_registrations
            WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
            LIMIT 1
        """, (username, email, username, email))
        if cursor.fetchone():
            raise sqlite3.IntegrityError("Username or email already exists")

        cursor.execute("""
            INSERT INTO pending_registrations
            (username, email, password_hash, verification_code_hash,
             verification_generation, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            username,
            email,
            password_hash,
            code_hash,
            generation,
            _verification_expiration(),
        ))
        pending_id = cursor.lastrowid
        connection.commit()
        return pending_id, code, generation
    except Exception:
        connection.rollback()
        raise


def confirm_pending_registration_delivery(connection, pending_id, generation):
    cursor = connection.cursor()
    cursor.execute("""
        UPDATE pending_registrations
        SET delivery_confirmed = 1
        WHERE id = ? AND verification_generation = ?
    """, (pending_id, generation))
    connection.commit()
    return cursor.rowcount == 1


def delete_pending_registration(connection, pending_id, generation):
    cursor = connection.cursor()
    cursor.execute("""
        DELETE FROM pending_registrations
        WHERE id = ? AND verification_generation = ?
    """, (pending_id, generation))
    connection.commit()


def resend_pending_verification(connection, email):
    cursor = connection.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    try:
        cursor.execute("""
            SELECT id FROM pending_registrations
            WHERE email = ? COLLATE NOCASE
        """, (email,))
        result = cursor.fetchone()
        if result is None:
            connection.commit()
            return None

        pending_id = result[0]
        code = _new_verification_code()
        code_hash = generate_password_hash(code)
        generation = _new_verification_generation()
        cursor.execute("""
            UPDATE pending_registrations
            SET verification_code_hash = ?,
                verification_generation = ?,
                expires_at = ?,
                attempts = 0,
                delivery_confirmed = 0
            WHERE id = ?
        """, (
            code_hash,
            generation,
            _verification_expiration(),
            pending_id,
        ))
        connection.commit()
        return pending_id, code, generation
    except Exception:
        connection.rollback()
        raise


def verify_pending_registration(connection, email, code):
    cursor = connection.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    try:
        cursor.execute("""
            SELECT id, username, email, password_hash, verification_code_hash,
                   expires_at, attempts, delivery_confirmed
            FROM pending_registrations
            WHERE email = ? COLLATE NOCASE
        """, (email,))
        pending = cursor.fetchone()
        if pending is None:
            connection.commit()
            return "not_found"

        (
            pending_id,
            username,
            pending_email,
            password_hash,
            code_hash,
            expires_at,
            attempts,
            delivery_confirmed,
        ) = pending

        if not delivery_confirmed:
            connection.commit()
            return "delivery_pending"

        if attempts >= MAX_VERIFICATION_ATTEMPTS:
            connection.commit()
            return "locked"

        if datetime.now(timezone.utc) > datetime.fromisoformat(expires_at):
            connection.commit()
            return "expired"

        if not check_password_hash(code_hash, code):
            attempts += 1
            cursor.execute("""
                UPDATE pending_registrations
                SET attempts = ?
                WHERE id = ?
            """, (attempts, pending_id))
            connection.commit()
            return "locked" if attempts >= MAX_VERIFICATION_ATTEMPTS else "invalid"

        cursor.execute("""
            INSERT INTO users (username, email, password_hash, email_verified)
            VALUES (?, ?, ?, 1)
        """, (username, pending_email, password_hash))
        cursor.execute(
            "DELETE FROM pending_registrations WHERE id = ?",
            (pending_id,),
        )
        connection.commit()
        return "verified"
    except Exception:
        connection.rollback()
        raise


def verify_email_token(connection, token, email=None):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cursor = connection.cursor()

    if email is None:
        cursor.execute("""
            SELECT user_id, expires_at
            FROM email_verifications
            WHERE token_hash = ?
        """, (token_hash,))
    else:
        cursor.execute("""
            SELECT email_verifications.user_id, email_verifications.expires_at
            FROM email_verifications
            JOIN users ON users.id = email_verifications.user_id
            WHERE email_verifications.token_hash = ? AND users.email = ?
        """, (token_hash, email))

    result = cursor.fetchone()

    if result is None:
        return False

    user_id, expires_at = result
    expiration = datetime.fromisoformat(expires_at)

    if datetime.now(timezone.utc) > expiration:
        return False

    cursor.execute("""
        UPDATE users
        SET email_verified = 1
        WHERE id = ?
    """, (user_id,))

    cursor.execute("""
        DELETE FROM email_verifications
        WHERE user_id = ?
    """, (user_id,))

    connection.commit()
    return True


def authenticate_user(connection, email, password):
    if not isinstance(email, str) or not isinstance(password, str):
        return None

    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, username, password_hash
        FROM users
        WHERE email = ? COLLATE NOCASE AND email_verified = 1
    """, (email.strip(),))
    user = cursor.fetchone()

    if user is None or not check_password_hash(user[2], password):
        return None

    return user[0], user[1]


def create_verification_token(connection, user_id):
    token = _new_verification_code()
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    expires_at = _verification_expiration()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO email_verifications
        (user_id, token_hash, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, token_hash, expires_at))

    connection.commit()

    return token


def get_user_by_email(connection, email):
    cursor = connection.cursor()

    cursor.execute(
        "SELECT id, email_verified FROM users WHERE email = ? COLLATE NOCASE",
        (email,)
    )

    return cursor.fetchone()


# This section runs ONLY when accounts.py is executed directly.
if __name__ == "__main__":
    initialize_database()
    print("Database connected!")
