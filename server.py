"""Rock Eternal Church Life Group prayer platform backed by Google Sheets.

Run this file from PyCharm after completing GOOGLE_SHEETS_SETUP.md.
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
from threading import Lock
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4


PROJECT_DIRECTORY = Path(__file__).parent
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ROCK_ETERNAL_ADMIN_PASSWORD", "change-me")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE = Path(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", PROJECT_DIRECTORY / "google-service-account.json")
)
GOOGLE_SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB", "Prayer Requests")
SESSION_COOKIE = "rock_eternal_leader"
SESSION_TTL_SECONDS = 60 * 60 * 12
VALID_STATUSES = ("pending", "published", "answered", "archived")
VALID_CATEGORIES = ("health", "family", "urgent", "praise", "other")
SHEET_HEADERS = (
    "ID",
    "Name",
    "Message",
    "Category",
    "Show Name",
    "Status",
    "Prayer Count",
    "Submitted At",
    "Updated At",
)

SESSIONS: dict[str, float] = {}
SESSION_LOCK = Lock()
STORAGE_LOCK = Lock()
STORE: GoogleSheetStore | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoogleSheetStore:
    """Keeps prayer data in one private Google Sheet tab."""

    def __init__(self, spreadsheet_id: str, credential_path: Path, tab_name: str) -> None:
        if not spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID is missing. See GOOGLE_SHEETS_SETUP.md.")
        if not credential_path.is_file():
            raise RuntimeError(
                "The Google service-account key file is missing. See GOOGLE_SHEETS_SETUP.md."
            )
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as error:
            raise RuntimeError("Install dependencies first: pip install -r requirements.txt") from error

        credentials = Credentials.from_service_account_file(
            str(credential_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self.client = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self.spreadsheet_id = spreadsheet_id
        self.tab_name = tab_name
        self._ensure_tab_and_headers()

    def _range(self, cells: str) -> str:
        escaped_tab = self.tab_name.replace("'", "''")
        return f"'{escaped_tab}'!{cells}"

    def _ensure_tab_and_headers(self) -> None:
        spreadsheet = self.client.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            fields="sheets.properties",
        ).execute()
        tabs = {sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])}
        if self.tab_name not in tabs:
            self.client.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": self.tab_name}}}]},
            ).execute()

        header_response = self.client.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self._range("A1:I1"),
        ).execute()
        existing = (header_response.get("values") or [[]])[0]
        if not existing:
            self.client.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=self._range("A1:I1"),
                valueInputOption="RAW",
                body={"values": [list(SHEET_HEADERS)]},
            ).execute()
        elif tuple(existing) != SHEET_HEADERS:
            raise RuntimeError(
                f"The '{self.tab_name}' tab has different columns. Use a new blank tab or the expected headers."
            )

    def _read_rows(self) -> list[tuple[int, dict[str, object]]]:
        response = self.client.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=self._range("A2:I"),
        ).execute()
        rows: list[tuple[int, dict[str, object]]] = []
        for row_number, raw_row in enumerate(response.get("values", []), start=2):
            if not raw_row or not raw_row[0]:
                continue
            values = (raw_row + [""] * len(SHEET_HEADERS))[: len(SHEET_HEADERS)]
            try:
                prayer_count = int(values[6] or 0)
            except ValueError:
                prayer_count = 0
            rows.append(
                (
                    row_number,
                    {
                        "id": values[0],
                        "name": values[1],
                        "message": values[2],
                        "category": values[3] if values[3] in VALID_CATEGORIES else "other",
                        "showName": values[4].strip().lower() == "true",
                        "status": values[5] if values[5] in VALID_STATUSES else "pending",
                        "prayerCount": prayer_count,
                        "submittedAt": values[7],
                        "updatedAt": values[8],
                    },
                )
            )
        return rows

    @staticmethod
    def _public(prayer: dict[str, object]) -> dict[str, object]:
        return {
            "id": prayer["id"],
            "name": prayer["name"] if prayer["showName"] and prayer["name"] else "Anonymous",
            "message": prayer["message"],
            "category": prayer["category"],
            "status": prayer["status"],
            "prayerCount": prayer["prayerCount"],
            "submittedAt": prayer["submittedAt"],
        }

    @staticmethod
    def _sheet_values(prayer: dict[str, object]) -> list[object]:
        return [
            prayer["id"],
            prayer["name"],
            prayer["message"],
            prayer["category"],
            "TRUE" if prayer["showName"] else "FALSE",
            prayer["status"],
            prayer["prayerCount"],
            prayer["submittedAt"],
            prayer["updatedAt"],
        ]

    def all_for_leader(self, status: str = "all") -> list[dict[str, object]]:
        rows = [prayer for _, prayer in self._read_rows()]
        if status in VALID_STATUSES:
            rows = [prayer for prayer in rows if prayer["status"] == status]
        return sorted(rows, key=lambda prayer: str(prayer["submittedAt"]), reverse=True)

    def all_for_group(self, status: str) -> list[dict[str, object]]:
        allowed_status = "answered" if status == "answered" else "published"
        prayers = [
            self._public(prayer)
            for _, prayer in self._read_rows()
            if prayer["status"] == allowed_status
        ]
        return sorted(prayers, key=lambda prayer: str(prayer["submittedAt"]), reverse=True)

    def get(self, prayer_id: str) -> tuple[int, dict[str, object]] | None:
        for row_number, prayer in self._read_rows():
            if prayer["id"] == prayer_id:
                return row_number, prayer
        return None

    def create(self, prayer: dict[str, object]) -> dict[str, object]:
        self.client.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=self._range("A:I"),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [self._sheet_values(prayer)]},
        ).execute()
        return prayer

    def update(self, row_number: int, prayer: dict[str, object]) -> dict[str, object]:
        self.client.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=self._range(f"A{row_number}:I{row_number}"),
            valueInputOption="RAW",
            body={"values": [self._sheet_values(prayer)]},
        ).execute()
        return prayer

    def delete(self, row_number: int) -> None:
        self.client.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=self._range(f"A{row_number}:I{row_number}"),
            body={},
        ).execute()

    def summary(self) -> dict[str, int]:
        result = {status: 0 for status in VALID_STATUSES}
        for _, prayer in self._read_rows():
            result[str(prayer["status"])] += 1
        return result


def storage() -> GoogleSheetStore:
    if STORE is None:
        raise RuntimeError("Google Sheets storage is not ready.")
    return STORE


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
        cookies = SimpleCookie()
        cookies.load(self.headers.get("Cookie", ""))
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

    def storage_error(self) -> None:
        self.send_json(
            503,
            {"error": "Google Sheets is unavailable right now. Please try again shortly."},
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/api/prayers":
                requested_status = query.get("status", ["published"])[0]
                with STORAGE_LOCK:
                    self.send_json(200, storage().all_for_group(requested_status))
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
                with STORAGE_LOCK:
                    self.send_json(200, storage().all_for_leader(requested_status))
                return

            if path == "/api/admin/summary":
                if not self.require_leader():
                    return
                with STORAGE_LOCK:
                    self.send_json(200, storage().summary())
                return
        except Exception:
            self.storage_error()
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

            timestamp = now()
            prayer = {
                "id": uuid4().hex,
                "name": name,
                "message": message,
                "category": category,
                "showName": show_name,
                "status": "pending",
                "prayerCount": 0,
                "submittedAt": timestamp,
                "updatedAt": timestamp,
            }
            try:
                with STORAGE_LOCK:
                    self.send_json(201, storage().create(prayer))
            except Exception:
                self.storage_error()
            return

        if path.startswith("/api/prayers/") and path.endswith("/pray"):
            prayer_id = path.removeprefix("/api/prayers/").removesuffix("/pray").strip("/")
            if not valid_id(prayer_id):
                self.send_json(404, {"error": "Prayer request not found."})
                return
            try:
                with STORAGE_LOCK:
                    found = storage().get(prayer_id)
                    if not found or found[1]["status"] not in ("published", "answered"):
                        self.send_json(404, {"error": "Prayer request not found."})
                        return
                    row_number, prayer = found
                    prayer["prayerCount"] = int(prayer["prayerCount"]) + 1
                    prayer["updatedAt"] = now()
                    storage().update(row_number, prayer)
                    self.send_json(200, storage()._public(prayer))
            except Exception:
                self.storage_error()
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
        try:
            with STORAGE_LOCK:
                found = storage().get(prayer_id)
                if not found:
                    self.send_json(404, {"error": "Prayer request not found."})
                    return
                row_number, prayer = found
                if "name" in payload:
                    prayer["name"] = str(payload["name"]).strip()[:70]
                if "message" in payload:
                    message = str(payload["message"]).strip()[:1200]
                    if not message:
                        self.send_json(400, {"error": "A prayer request cannot be empty."})
                        return
                    prayer["message"] = message
                if "category" in payload:
                    category = str(payload["category"]).lower()
                    if category not in VALID_CATEGORIES:
                        self.send_json(400, {"error": "Please choose a valid category."})
                        return
                    prayer["category"] = category
                if "showName" in payload:
                    prayer["showName"] = payload["showName"] is True
                if "status" in payload:
                    status = str(payload["status"]).lower()
                    if status not in VALID_STATUSES:
                        self.send_json(400, {"error": "Please choose a valid status."})
                        return
                    prayer["status"] = status
                prayer["updatedAt"] = now()
                self.send_json(200, storage().update(row_number, prayer))
        except Exception:
            self.storage_error()

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
        try:
            with STORAGE_LOCK:
                found = storage().get(prayer_id)
                if not found:
                    self.send_json(404, {"error": "Prayer request not found."})
                    return
                storage().delete(found[0])
                self.send_json(200, {"deleted": True})
        except Exception:
            self.storage_error()


def main() -> None:
    global STORE
    try:
        STORE = GoogleSheetStore(GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHEET_TAB)
    except RuntimeError as error:
        print(f"\nSetup needed: {error}\n")
        print("Open GOOGLE_SHEETS_SETUP.md and complete the Google Sheets connection steps.\n")
        return

    os.chdir(PROJECT_DIRECTORY)
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((HOST, PORT), PrayerRequestHandler)
    print(f"\nPrayer platform is running at: http://localhost:{PORT}\n")
    if ADMIN_PASSWORD == "change-me":
        print("Leader Dashboard password: change-me")
        print("Change it before sharing the website publicly.\n")
    else:
        print("Leader Dashboard password: set from ROCK_ETERNAL_ADMIN_PASSWORD\n")
    print(f"Saving every request to Google Sheet tab: {GOOGLE_SHEET_TAB}\n")
    print("Keep this window open while using the website. Press Ctrl+C to stop it.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
