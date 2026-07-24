"""Rock Eternal Church Life Group prayer platform.

Run this file from PyCharm, then visit http://localhost:8000.
Set ROCK_ETERNAL_ADMIN_PASSWORD before public deployment.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hmac
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
from threading import Lock
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4


PROJECT_DIRECTORY = Path(__file__).parent
DATA_DIRECTORY = PROJECT_DIRECTORY / "data"
DATABASE_FILE = DATA_DIRECTORY / "prayer_platform.db"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ROCK_ETERNAL_ADMIN_PASSWORD", "change-me")
SESSION_COOKIE = "rock_eternal_leader"
SESSION_TTL_SECONDS = 60 * 60 * 12
VALID_STATUSES = ("pending", "published", "answered", "archived")
VALID_CATEGORIES = ("health", "family", "urgent", "praise", "other")

SESSIONS: dict[str, float] = {}
SESSION_LOCK = Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def database_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database() -> None:
    DATA_DIRECTORY.mkdir(exist_ok=True)
    with database_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS prayer_requests (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                show_name INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                prayer_count INTEGER NOT NULL DEFAULT 0,
                submitted_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS prayer_status_submitted ON prayer_requests(status, submitted_at DESC)"
        )


def serialise_prayer(row: sqlite3.Row, public: bool = False) -> dict[str, object]:
    visible_name = row["name"] if row["show_name"] and row["name"] else "Anonymous"
    result: dict[str, object] = {
        "id": row["id"],
        "name": visible_name if public else row["name"],
        "message": row["message"],
        "category": row["category"],
        "status": row["status"],
        "prayerCount": row["prayer_count"],
        "submittedAt": row["submitted_at"],
    }
    if not public:
        result["showName"] = bool(row["show_name"])
        result["updatedAt"] = row["updated_at"]
    return result


def read_public_prayers(status: str) -> list[dict[str, object]]:
    allowed_status = "answered" if status == "answered" else "published"
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM prayer_requests WHERE status = ? ORDER BY submitted_at DESC",
            (allowed_status,),
        ).fetchall()
    return [serialise_prayer(row, public=True) for row in rows]


def read_admin_prayers(status: str) -> list[dict[str, object]]:
    with database_connection() as connection:
        if status in VALID_STATUSES:
            rows = connection.execute(
                "SELECT * FROM prayer_requests WHERE status = ? ORDER BY submitted_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM prayer_requests ORDER BY submitted_at DESC").fetchall()
    return [serialise_prayer(row) for row in rows]


def get_prayer(prayer_id: str) -> sqlite3.Row | None:
    with database_connection() as connection:
        return connection.execute("SELECT * FROM prayer_requests WHERE id = ?", (prayer_id,)).fetchone()


def valid_id(prayer_id: str) -> bool:
    return len(prayer_id) == 32 and all(character in "0123456789abcdef" for character in prayer_id)


class PrayerRequestHandler(SimpleHTTPRequestHandler):
    def send_json(
        self,
        status: int,
        payload: object,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, object] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 6000:
                return None
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            return payload if isinstance(payload, dict) else None
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def request_session(self) -> str | None:
        cookie_header = self.headers.get("Cookie", "")
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        token = cookies.get(SESSION_COOKIE)
        return token.value if token else None

    def is_leader(self) -> bool:
        token = self.request_session()
        if not token:
            return False
        with SESSION_LOCK:
            expires_at = SESSIONS.get(token, 0)
            if expires_at <= time.time():
                SESSIONS.pop(token, None)
                return False
        return True

    def require_leader(self) -> bool:
        if self.is_leader():
            return True
        self.send_json(401, {"error": "Leader sign-in is required."})
        return False

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        with SESSION_LOCK:
            SESSIONS[token] = time.time() + SESSION_TTL_SECONDS
        return token

    def clear_session(self) -> None:
        token = self.request_session()
        if token:
            with SESSION_LOCK:
                SESSIONS.pop(token, None)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/prayers":
            requested_status = query.get("status", ["published"])[0]
            self.send_json(200, read_public_prayers(requested_status))
            return

        if path == "/api/admin/session":
            if not self.require_leader():
                return
            self.send_json(200, {"authenticated": True})
            return

        if path == "/api/admin/requests":
            if not self.require_leader():
                return
            requested_status = query.get("status", ["all"])[0]
            self.send_json(200, read_admin_prayers(requested_status))
            return

        if path == "/api/admin/summary":
            if not self.require_leader():
                return
            with database_connection() as connection:
                rows = connection.execute(
                    "SELECT status, COUNT(*) AS total FROM prayer_requests GROUP BY status"
                ).fetchall()
            summary = {status: 0 for status in VALID_STATUSES}
            summary.update({row["status"]: row["total"] for row in rows})
            self.send_json(200, summary)
            return

        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/admin/login":
            payload = self.read_json() or {}
            password = str(payload.get("password", ""))
            if not hmac.compare_digest(password, ADMIN_PASSWORD):
                self.send_json(401, {"error": "That password is not correct."})
                return
            token = self.create_session()
            cookie = (
                f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; "
                f"Max-Age={SESSION_TTL_SECONDS}"
            )
            self.send_json(200, {"authenticated": True}, {"Set-Cookie": cookie})
            return

        if path == "/api/admin/logout":
            self.clear_session()
            expired_cookie = f"{SESSION_COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
            self.send_json(200, {"authenticated": False}, {"Set-Cookie": expired_cookie})
            return

        if path == "/api/prayers":
            payload = self.read_json()
            if not payload:
                self.send_json(400, {"error": "Invalid prayer request."})
                return

            name = str(payload.get("name", "")).strip()[:70]
            message = str(payload.get("message", "")).strip()[:1200]
            category = str(payload.get("category", "other")).lower()
            shared_with_group = payload.get("shareWithGroup") is True
            show_name = payload.get("showName") is True and bool(name)
            if not message:
                self.send_json(400, {"error": "A prayer request is required."})
                return
            if not shared_with_group:
                self.send_json(400, {"error": "Please confirm that your Life Group can pray for this request."})
                return
            if category not in VALID_CATEGORIES:
                category = "other"

            prayer_id = uuid4().hex
            timestamp = now()
            with database_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO prayer_requests
                      (id, name, message, category, show_name, status, prayer_count, submitted_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                    """,
                    (prayer_id, name, message, category, int(show_name), timestamp, timestamp),
                )
            row = get_prayer(prayer_id)
            self.send_json(201, serialise_prayer(row) if row else {"id": prayer_id})
            return

        if path.startswith("/api/prayers/") and path.endswith("/pray"):
            prayer_id = path.removeprefix("/api/prayers/").removesuffix("/pray").strip("/")
            if not valid_id(prayer_id):
                self.send_json(404, {"error": "Prayer request not found."})
                return
            with database_connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE prayer_requests
                    SET prayer_count = prayer_count + 1, updated_at = ?
                    WHERE id = ? AND status IN ('published', 'answered')
                    """,
                    (now(), prayer_id),
                )
            if not cursor.rowcount:
                self.send_json(404, {"error": "Prayer request not found."})
                return
            row = get_prayer(prayer_id)
            self.send_json(200, serialise_prayer(row, public=True) if row else {"id": prayer_id})
            return

        self.send_json(404, {"error": "Not found."})

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/admin/requests/"):
            self.send_json(404, {"error": "Not found."})
            return
        if not self.require_leader():
            return
        prayer_id = path.removeprefix("/api/admin/requests/").strip("/")
        if not valid_id(prayer_id):
            self.send_json(404, {"error": "Prayer request not found."})
            return
        payload = self.read_json()
        if not payload:
            self.send_json(400, {"error": "No updates were received."})
            return

        changes: list[str] = []
        values: list[object] = []
        if "name" in payload:
            changes.append("name = ?")
            values.append(str(payload["name"]).strip()[:70])
        if "message" in payload:
            message = str(payload["message"]).strip()[:1200]
            if not message:
                self.send_json(400, {"error": "A prayer request cannot be empty."})
                return
            changes.append("message = ?")
            values.append(message)
        if "category" in payload:
            category = str(payload["category"]).lower()
            if category not in VALID_CATEGORIES:
                self.send_json(400, {"error": "Please choose a valid category."})
                return
            changes.append("category = ?")
            values.append(category)
        if "showName" in payload:
            changes.append("show_name = ?")
            values.append(int(payload["showName"] is True))
        if "status" in payload:
            status = str(payload["status"]).lower()
            if status not in VALID_STATUSES:
                self.send_json(400, {"error": "Please choose a valid status."})
                return
            changes.append("status = ?")
            values.append(status)
        if not changes:
            self.send_json(400, {"error": "No valid updates were received."})
            return

        changes.append("updated_at = ?")
        values.extend([now(), prayer_id])
        with database_connection() as connection:
            cursor = connection.execute(
                f"UPDATE prayer_requests SET {', '.join(changes)} WHERE id = ?", values
            )
        if not cursor.rowcount:
            self.send_json(404, {"error": "Prayer request not found."})
            return
        row = get_prayer(prayer_id)
        self.send_json(200, serialise_prayer(row) if row else {"id": prayer_id})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/admin/requests/"):
            self.send_json(404, {"error": "Not found."})
            return
        if not self.require_leader():
            return
        prayer_id = path.removeprefix("/api/admin/requests/").strip("/")
        if not valid_id(prayer_id):
            self.send_json(404, {"error": "Prayer request not found."})
            return
        with database_connection() as connection:
            cursor = connection.execute("DELETE FROM prayer_requests WHERE id = ?", (prayer_id,))
        if not cursor.rowcount:
            self.send_json(404, {"error": "Prayer request not found."})
            return
        self.send_json(200, {"deleted": True})


def main() -> None:
    initialise_database()
    os.chdir(PROJECT_DIRECTORY)
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), PrayerRequestHandler)
    print(f"\nPrayer platform is running at: http://localhost:{PORT}\n")
    if ADMIN_PASSWORD == "change-me":
        print("Leader Dashboard password: change-me")
        print("Change it before sharing the website publicly.\n")
    else:
        print("Leader Dashboard password: set from ROCK_ETERNAL_ADMIN_PASSWORD\n")
    print("Keep this window open while using the website. Press Ctrl+C to stop it.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
