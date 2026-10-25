
import sqlite3
from werkzeug.security import generate_password_hash
import secrets
import hashlib
from datetime import datetime, timedelta, timezone


def verify_email_token(connection, token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT user_id, expires_at
        FROM email_verifications
        WHERE token_hash = ?
    """, (token_hash,))

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

def create_user(connection, username, email, password):
    cursor = connection.cursor()

    # Hash the password before storing it.
    password_hash = generate_password_hash(password)

    # Create the account in SQLite.
    cursor.execute("""
        INSERT INTO users (username, email, password_hash)
        VALUES (?, ?, ?)
    """, (username, email, password_hash))

    # Save the account permanently.
    connection.commit()

    # Return the newly created user's ID.
    return cursor.lastrowid

    

def create_verification_token(connection, user_id):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=15)
    ).isoformat()

    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO email_verifications
        (user_id, token_hash, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, token_hash, expires_at))

    connection.commit()

    return token
# This section runs ONLY when accounts.py is executed directly.
if __name__ == "__main__":

    # Open the local SQLite database.
    connection = sqlite3.connect("accounts.db")
    cursor = connection.cursor()

    # Create the users table.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email_verified INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Insert a sample account.
    username = "text user"
    email = "text@example.com"
    password = "temporary_test_password"
    password_hash = generate_password_hash(password)

    cursor.execute("""
        INSERT OR IGNORE INTO users
        (username, email, password_hash)
        VALUES (?, ?, ?)
    """, (username, email, password_hash))

    # Create the email verification table.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            user_id INTEGER PRIMARY KEY,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    connection.commit()
    print("Database connected!")

    cursor.execute("""
        SELECT id, username, email, email_verified
        FROM users
    """)

    users = cursor.fetchall()

    for user in users:
        print(user)

    # Generate a verification token.
    verification_token = secrets.token_urlsafe(32)
    print("Verification token Generated")

    token_hash = hashlib.sha256(
        verification_token.encode()
    ).hexdigest()

    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=15)
    ).isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO email_verifications
        (user_id, token_hash, expires_at)
        VALUES (?, ?, ?) 
    """, (1, token_hash, expires_at))

    connection.commit()
    print("Verification token saved!")

    cursor.execute("""
        SELECT username, email_verified
        FROM users
        WHERE id = 1
    """)

    print(cursor.fetchone())

    connection.close()
