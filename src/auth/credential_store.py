"""Secure credential vault for storing portal login/registration credentials in SQLite.

Stores credentials per portal/platform so they can be reused across sessions.
Passwords are encrypted with Fernet (symmetric encryption).
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.config.logging import get_logger

logger = get_logger(__name__)


class CredentialStore:
    """Store and retrieve portal credentials using SQLite with encryption."""

    def __init__(self, db_path: Optional[Path] = None, encryption_key: Optional[str] = None):
        """Initialize credential store.

        Args:
            db_path: Path to SQLite database file
            encryption_key: Fernet encryption key. If not provided, uses default from settings.
        """
        # Default path: data/credentials.db
        if db_path is None:
            db_path = Path("data") / "credentials.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Use provided key or generate/persist one
        if encryption_key:
            self.key = encryption_key.encode()
        else:
            self.key = self._load_or_create_key()

        self.cipher = Fernet(self.key)
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _load_or_create_key(self) -> bytes:
        """Load existing encryption key or create and persist a new one."""
        key_file = self.db_path.parent / ".credentials_key"
        if key_file.exists():
            return key_file.read_bytes()

        key = Fernet.generate_key()
        key_file.write_bytes(key)
        # Set restrictive permissions on key file
        try:
            key_file.chmod(0o600)
        except Exception:
            pass
        logger.info("Generated new encryption key", path=str(key_file))
        return key

    def _connect(self) -> None:
        """Connect to SQLite and create schema."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal TEXT NOT NULL,           -- e.g., 'linkedin', 'naukri', 'workday'
                username TEXT NOT NULL,          -- email or username
                password_encrypted TEXT NOT NULL,  -- Fernet-encrypted password
                extra_data TEXT,                 -- JSON dict of additional fields (phone, etc.)
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_used_at TEXT,
                status TEXT DEFAULT 'active',    -- active, disabled, expired
                notes TEXT,
                UNIQUE(portal, username)
            );

            CREATE INDEX IF NOT EXISTS idx_credentials_portal
            ON credentials(portal);
        """)
        self._conn.commit()

    def save_credentials(
        self,
        portal: str,
        username: str,
        password: str,
        extra_data: Optional[dict] = None,
        notes: str = "",
    ) -> int:
        """Save or update credentials for a portal.

        Args:
            portal: Portal name (e.g., 'linkedin', 'workday')
            username: Username/email
            password: Plain-text password (will be encrypted before storing)
            extra_data: Additional fields to store (e.g., phone, security_question)
            notes: Optional notes

        Returns:
            credential ID
        """
        if not self._conn:
            self._connect()

        now = datetime.now(timezone.utc).isoformat()
        encrypted_pw = self._encrypt(password)
        extra_json = json.dumps(extra_data) if extra_data else None

        # Check if exists
        row = self._conn.execute(
            "SELECT id FROM credentials WHERE portal = ? AND username = ?",
            (portal.lower(), username.lower()),
        ).fetchone()

        if row:
            # Update existing
            self._conn.execute(
                """UPDATE credentials
                   SET password_encrypted = ?, extra_data = ?, updated_at = ?, notes = ?
                   WHERE id = ?""",
                (encrypted_pw, extra_json, now, notes, row["id"]),
            )
            cred_id = row["id"]
        else:
            # Insert new
            cursor = self._conn.execute(
                """INSERT INTO credentials (
                    portal, username, password_encrypted, extra_data,
                    created_at, updated_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (portal.lower(), username.lower(), encrypted_pw, extra_json, now, now, notes),
            )
            cred_id = cursor.lastrowid

        self._conn.commit()
        logger.info("Credentials saved", portal=portal, username=username, id=cred_id)
        return cred_id

    def get_credentials(self, portal: str, username: Optional[str] = None) -> Optional[dict]:
        """Retrieve credentials for a portal.

        Args:
            portal: Portal name
            username: Optional username filter (if None, returns most recent)

        Returns:
            Dict with keys: portal, username, password, extra_data, notes
            Returns None if no credentials found
        """
        if not self._conn:
            self._connect()

        if username:
            row = self._conn.execute(
                """SELECT * FROM credentials
                   WHERE portal = ? AND username = ? AND status = 'active'
                   ORDER BY updated_at DESC LIMIT 1""",
                (portal.lower(), username.lower()),
            ).fetchone()
        else:
            row = self._conn.execute(
                """SELECT * FROM credentials
                   WHERE portal = ? AND status = 'active'
                   ORDER BY updated_at DESC LIMIT 1""",
                (portal.lower(),),
            ).fetchone()

        if not row:
            logger.debug("No credentials found", portal=portal)
            return None

        try:
            decrypted_pw = self._decrypt(row["password_encrypted"])
        except InvalidToken:
            logger.error("Failed to decrypt password - key mismatch", portal=portal)
            return None

        extra = json.loads(row["extra_data"]) if row["extra_data"] else {}

        # Update last_used_at
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE credentials SET last_used_at = ? WHERE id = ?",
            (now, row["id"]),
        )
        self._conn.commit()

        return {
            "portal": row["portal"],
            "username": row["username"],
            "password": decrypted_pw,
            "extra_data": extra,
            "notes": row["notes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_used_at": row["last_used_at"],
        }

    def get_all_portals(self) -> list[str]:
        """Get all portals that have stored credentials."""
        if not self._conn:
            self._connect()

        rows = self._conn.execute(
            "SELECT DISTINCT portal FROM credentials WHERE status = 'active'"
        ).fetchall()
        return [row["portal"] for row in rows]

    def list_credentials(self, portal: Optional[str] = None) -> list[dict]:
        """List all stored credentials (without passwords).

        Args:
            portal: Filter by portal name

        Returns:
            List of credential metadata (no passwords)
        """
        if not self._conn:
            self._connect()

        if portal:
            rows = self._conn.execute(
                "SELECT id, portal, username, created_at, updated_at, last_used_at, status, notes FROM credentials WHERE portal = ?",
                (portal.lower(),),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, portal, username, created_at, updated_at, last_used_at, status, notes FROM credentials"
            ).fetchall()

        return [dict(row) for row in rows]

    def delete_credentials(self, portal: str, username: Optional[str] = None) -> bool:
        """Delete credentials for a portal."""
        if not self._conn:
            self._connect()

        if username:
            cursor = self._conn.execute(
                "DELETE FROM credentials WHERE portal = ? AND username = ?",
                (portal.lower(), username.lower()),
            )
        else:
            cursor = self._conn.execute(
                "DELETE FROM credentials WHERE portal = ?",
                (portal.lower(),),
            )

        self._conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Credentials deleted", portal=portal, username=username)
        return deleted

    def update_credentials(
        self,
        portal: str,
        username: str,
        password: Optional[str] = None,
        extra_data: Optional[dict] = None,
        status: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update credentials for a portal."""
        if not self._conn:
            self._connect()

        now = datetime.now(timezone.utc).isoformat()
        updates = ["updated_at = ?"]
        params: list = [now]

        if password is not None:
            updates.append("password_encrypted = ?")
            params.append(self._encrypt(password))

        if extra_data is not None:
            updates.append("extra_data = ?")
            params.append(json.dumps(extra_data))

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)

        params.extend([portal.lower(), username.lower()])

        cursor = self._conn.execute(
            f"UPDATE credentials SET {', '.join(updates)} WHERE portal = ? AND username = ?",
            params,
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def has_credentials(self, portal: str) -> bool:
        """Check if credentials exist for a portal."""
        if not self._conn:
            self._connect()

        row = self._conn.execute(
            "SELECT 1 FROM credentials WHERE portal = ? AND status = 'active'",
            (portal.lower(),),
        ).fetchone()
        return row is not None

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a password."""
        return self.cipher.encrypt(plaintext.encode()).decode()

    def _decrypt(self, encrypted: str) -> str:
        """Decrypt a stored password."""
        return self.cipher.decrypt(encrypted.encode()).decode()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()


# Singleton instance helper
def get_credential_store() -> CredentialStore:
    """Get a singleton CredentialStore instance."""
    if not hasattr(get_credential_store, "_instance"):
        get_credential_store._instance = CredentialStore()
    return get_credential_store._instance