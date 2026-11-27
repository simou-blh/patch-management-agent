"""Per-tenant state with strict isolation and purge-on-deactivation."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3

TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class TenantStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.root / "tenants.sqlite"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY, directory TEXT NOT NULL,
                key_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                activated_at TEXT NOT NULL, config TEXT NOT NULL)""")
        try:
            self.database.chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _directory_name(self, tenant_id):
        return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:32]

    def directory(self, tenant_id):
        path = (self.root / "tenants" / self._directory_name(tenant_id)).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("tenant directory escaped the data root")
        return path

    def activate(self, tenant_id, api_key, config):
        if not isinstance(tenant_id, str) or not TENANT_RE.fullmatch(tenant_id):
            raise ValueError("invalid tenant id")
        if not isinstance(api_key, str) or not api_key or len(api_key) > 512:
            raise ValueError("invalid tenant api key")
        if not isinstance(config, dict):
            raise ValueError("config must be an object")

        directory = self.directory(tenant_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        now = _now()
        document = {"tenant_id": tenant_id, "api_key": api_key,
                    "config": config, "activated_at": now}
        path = directory / "tenant.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)

        with self.connect() as db:
            existing = db.execute("SELECT created_at FROM tenants WHERE tenant_id=?",
                                  (tenant_id,)).fetchone()
            created = existing[0] if existing else now
            db.execute("""INSERT INTO tenants VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET directory=excluded.directory,
                key_sha256=excluded.key_sha256, activated_at=excluded.activated_at,
                config=excluded.config""",
                (tenant_id, str(directory), _key_hash(api_key), created, now,
                 json.dumps(config, sort_keys=True)))
        return document

    def deactivate(self, tenant_id):
        directory = self.directory(tenant_id)
        with self.connect() as db:
            db.execute("DELETE FROM tenants WHERE tenant_id=?", (tenant_id,))
        purged = False
        if directory.exists():
            shutil.rmtree(directory)
            purged = True
        return purged

    def get(self, tenant_id):
        if not isinstance(tenant_id, str) or not TENANT_RE.fullmatch(tenant_id):
            return None
        with self.connect() as db:
            row = db.execute("""SELECT tenant_id, directory, key_sha256, created_at,
                activated_at, config FROM tenants WHERE tenant_id=?""", (tenant_id,)).fetchone()
        if row is None:
            return None
        document = {"tenant_id": row[0], "directory": row[1], "key_sha256": row[2],
                    "created_at": row[3], "activated_at": row[4],
                    "config": json.loads(row[5])}
        try:
            local = json.loads((Path(row[1]) / "tenant.json").read_text(encoding="utf-8"))
            document["api_key"] = local.get("api_key")
        except (OSError, ValueError):
            document["api_key"] = None
        return document

    def validate_key(self, tenant_id, api_key):
        tenant = self.get(tenant_id)
        if tenant is None or not api_key:
            return False
        return hmac.compare_digest(tenant["key_sha256"], _key_hash(api_key))

    def path(self, tenant_id, *parts):
        directory = self.directory(tenant_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def write_json(self, tenant_id, name, value):
        path = self.path(tenant_id, name)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
        return path

    def read_json(self, tenant_id, name):
        path = self.directory(tenant_id) / name
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def has(self, tenant_id, name):
        return (self.directory(tenant_id) / name).is_file()

    def status(self, tenant_id):
        tenant = self.get(tenant_id)
        if tenant is None:
            return None
        assessment = self.read_json(tenant_id, "assessment.json") or {}
        return {
            "state": "running",
            "activated_at": tenant["activated_at"],
            "last_assessment_at": assessment.get("assessed_at"),
            "execution_enabled": False,
        }
