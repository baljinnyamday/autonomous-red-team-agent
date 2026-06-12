from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.targets.local_probe import LocalHostProbe, probe_local_host
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import (
    AttemptRecord,
    CredentialFinding,
    DefenseFinding,
    EngagementTopology,
    HostSeed,
    ServiceFinding,
    Transport,
    normalize_transport_value,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS engagements (
    engagement_id TEXT PRIMARY KEY,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS hosts (
    engagement_id TEXT NOT NULL,
    host_id TEXT NOT NULL,
    transport TEXT NOT NULL,
    address TEXT,
    user TEXT,
    via_json TEXT NOT NULL DEFAULT '[]',
    discovered_from TEXT,
    runner_endpoint TEXT,
    runner_ready_announced INTEGER NOT NULL DEFAULT 0,
    os TEXT,
    hostname TEXT,
    arch TEXT,
    PRIMARY KEY (engagement_id, host_id)
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL,
    host_id TEXT NOT NULL,
    port INTEGER,
    protocol TEXT,
    product TEXT,
    url TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL,
    host_id TEXT NOT NULL,
    username TEXT,
    secret TEXT,
    cred_type TEXT,
    source TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS host_tags (
    engagement_id TEXT NOT NULL,
    host_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (engagement_id, host_id, tag)
);

CREATE TABLE IF NOT EXISTS host_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL,
    host_id TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS defenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL,
    host_id TEXT NOT NULL,
    category TEXT,
    name TEXT,
    present INTEGER NOT NULL DEFAULT 1,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id TEXT NOT NULL,
    technique TEXT NOT NULL,
    target TEXT,
    outcome TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_hosts_engagement_address
    ON hosts (engagement_id, address) WHERE address IS NOT NULL;
"""


class EngagementStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(hosts)")}
        if "discovered_from" not in columns:
            self._conn.execute("ALTER TABLE hosts ADD COLUMN discovered_from TEXT")
            self._conn.commit()

    @classmethod
    def connect(cls, path: Path) -> EngagementStore:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        return cls(connection)

    def close(self) -> None:
        self._conn.close()

    def ensure_local_host(
        self,
        engagement_id: str,
        *,
        probe: LocalHostProbe | None = None,
    ) -> None:
        local = probe or probe_local_host()
        self._conn.execute(
            """
            INSERT OR IGNORE INTO hosts (
                engagement_id, host_id, transport, via_json, runner_ready_announced
            ) VALUES (?, 'operator', ?, '[]', 0)
            """,
            (engagement_id, Transport.LOCAL.value),
        )
        self._conn.execute(
            """
            UPDATE hosts SET
                os = COALESCE(os, ?),
                hostname = COALESCE(hostname, ?),
                arch = COALESCE(arch, ?),
                user = COALESCE(user, ?)
            WHERE engagement_id = ? AND host_id = 'operator'
            """,
            (local.os, local.hostname, local.arch, local.user, engagement_id),
        )
        self.add_tags(engagement_id, "operator", ["operator", "local"])
        self._conn.commit()

    def set_engagement_notes(self, engagement_id: str, notes: str | None) -> None:
        self._conn.execute(
            """
            INSERT INTO engagements (engagement_id, notes) VALUES (?, ?)
            ON CONFLICT(engagement_id) DO UPDATE SET notes = excluded.notes
            """,
            (engagement_id, notes),
        )
        self._conn.commit()

    def seed_from_topology(self, topology: EngagementTopology, *, engagement_id: str) -> None:
        if topology.notes:
            row = self._conn.execute(
                "SELECT notes FROM engagements WHERE engagement_id = ?",
                (engagement_id,),
            ).fetchone()
            if row is None or row["notes"] is None:
                self.set_engagement_notes(engagement_id, topology.notes)

        for seed in topology.hosts:
            if self._host_exists(engagement_id, seed.id):
                continue
            self._insert_seed_host(engagement_id, seed)

        self._conn.commit()

    def load_state(self, engagement_id: str) -> EngagementState:
        notes_row = self._conn.execute(
            "SELECT notes FROM engagements WHERE engagement_id = ?",
            (engagement_id,),
        ).fetchone()
        notes = notes_row["notes"] if notes_row else None

        host_rows = self._conn.execute(
            "SELECT * FROM hosts WHERE engagement_id = ? ORDER BY host_id",
            (engagement_id,),
        ).fetchall()

        hosts: dict[str, HostRuntime] = {}
        for row in host_rows:
            host_id = row["host_id"]
            hosts[host_id] = HostRuntime(
                transport=Transport(normalize_transport_value(row["transport"])),
                address=row["address"],
                user=row["user"],
                via=json.loads(row["via_json"]),
                discovered_from=row["discovered_from"],
                os=row["os"],
                hostname=row["hostname"],
                arch=row["arch"],
                tags=self._load_tags(engagement_id, host_id),
                services=self._load_services(engagement_id, host_id),
                credentials=self._load_credentials(engagement_id, host_id),
                defenses=self._load_defenses(engagement_id, host_id),
                notes=self._load_notes(engagement_id, host_id),
            )

        return EngagementState(engagement_id=engagement_id, hosts=hosts, notes=notes)

    def find_host_id_by_address(self, engagement_id: str, address: str) -> str | None:
        row = self._conn.execute(
            "SELECT host_id FROM hosts WHERE engagement_id = ? AND address = ?",
            (engagement_id, address),
        ).fetchone()
        return row["host_id"] if row is not None else None

    def fill_missing_host_fields(
        self,
        engagement_id: str,
        host_id: str,
        *,
        transport: Transport | None = None,
        address: str | None = None,
        user: str | None = None,
        via: list[str] | None = None,
        discovered_from: str | None = None,
        os: str | None = None,
        hostname: str | None = None,
        arch: str | None = None,
    ) -> None:
        row = self._conn.execute(
            "SELECT * FROM hosts WHERE engagement_id = ? AND host_id = ?",
            (engagement_id, host_id),
        ).fetchone()
        if row is None:
            msg = f"Unknown host {host_id!r}. Use a host id from the engagement topology."
            raise ConfigurationError(msg)

        updates: list[str] = []
        values: list[object] = []

        def add_if_missing(
            column: str,
            new_value: object | None,
            current_value: object | None,
        ) -> None:
            if new_value is None:
                return
            if current_value not in (None, ""):
                return
            updates.append(f"{column} = ?")
            values.append(new_value)

        current_via = json.loads(row["via_json"])
        add_if_missing("transport", transport.value if transport else None, row["transport"])
        add_if_missing("address", address, row["address"])
        add_if_missing("user", user, row["user"])
        if via is not None and not current_via:
            updates.append("via_json = ?")
            values.append(json.dumps(via))
        add_if_missing("discovered_from", discovered_from, row["discovered_from"])
        add_if_missing("os", os, row["os"])
        add_if_missing("hostname", hostname, row["hostname"])
        add_if_missing("arch", arch, row["arch"])

        if not updates:
            return

        values.extend([engagement_id, host_id])
        sql = f"UPDATE hosts SET {', '.join(updates)} WHERE engagement_id = ? AND host_id = ?"
        self._conn.execute(sql, values)
        self._conn.commit()

    def upsert_host(
        self,
        engagement_id: str,
        host_id: str,
        *,
        transport: Transport | None = None,
        address: str | None = None,
        user: str | None = None,
        via: list[str] | None = None,
        discovered_from: str | None = None,
        os: str | None = None,
        hostname: str | None = None,
        arch: str | None = None,
    ) -> None:
        if self._host_exists(engagement_id, host_id):
            updates: list[str] = []
            values: list[object] = []
            if transport is not None:
                updates.append("transport = ?")
                values.append(transport.value)
            if address is not None:
                updates.append("address = ?")
                values.append(address)
            if user is not None:
                updates.append("user = ?")
                values.append(user)
            if via is not None:
                updates.append("via_json = ?")
                values.append(json.dumps(via))
            if discovered_from is not None:
                updates.append("discovered_from = ?")
                values.append(discovered_from)
            if os is not None:
                updates.append("os = ?")
                values.append(os)
            if hostname is not None:
                updates.append("hostname = ?")
                values.append(hostname)
            if arch is not None:
                updates.append("arch = ?")
                values.append(arch)
            if updates:
                values.extend([engagement_id, host_id])
                sql = (
                    f"UPDATE hosts SET {', '.join(updates)} WHERE engagement_id = ? AND host_id = ?"
                )
                self._conn.execute(sql, values)
        else:
            resolved_transport = (transport or Transport.REMOTE).value
            self._conn.execute(
                """
                INSERT INTO hosts (
                    engagement_id, host_id, transport, address, user, via_json,
                    discovered_from, runner_endpoint, runner_ready_announced,
                    os, hostname, arch
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?)
                """,
                (
                    engagement_id,
                    host_id,
                    resolved_transport,
                    address,
                    user,
                    json.dumps(via or []),
                    discovered_from,
                    os,
                    hostname,
                    arch,
                ),
            )
        self._conn.commit()

    def add_services(
        self,
        engagement_id: str,
        host_id: str,
        services: list[ServiceFinding],
    ) -> None:
        existing = {
            _service_identity(service) for service in self._load_services(engagement_id, host_id)
        }
        inserted = False
        for service in services:
            identity = _service_identity(service)
            if identity in existing:
                continue
            existing.add(identity)
            inserted = True
            self._conn.execute(
                """
                INSERT INTO services (
                    engagement_id, host_id, port, protocol, product, url, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    engagement_id,
                    host_id,
                    service.port,
                    service.protocol,
                    service.product,
                    service.url,
                    service.notes,
                ),
            )
        if inserted:
            self._conn.commit()

    def add_credentials(
        self,
        engagement_id: str,
        host_id: str,
        credentials: list[CredentialFinding],
    ) -> None:
        for credential in credentials:
            self._conn.execute(
                """
                INSERT INTO credentials (
                    engagement_id, host_id, username, secret, cred_type, source, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    engagement_id,
                    host_id,
                    credential.username,
                    credential.secret,
                    credential.type,
                    credential.source,
                    credential.notes,
                ),
            )
        self._conn.commit()

    def add_tags(self, engagement_id: str, host_id: str, tags: list[str]) -> None:
        for tag in tags:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO host_tags (engagement_id, host_id, tag)
                VALUES (?, ?, ?)
                """,
                (engagement_id, host_id, tag),
            )
        self._conn.commit()

    def add_defenses(
        self,
        engagement_id: str,
        host_id: str,
        defenses: list[DefenseFinding],
    ) -> None:
        for defense in defenses:
            self._conn.execute(
                """
                INSERT INTO defenses (engagement_id, host_id, category, name, present, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    engagement_id,
                    host_id,
                    defense.category,
                    defense.name,
                    1 if defense.present else 0,
                    defense.detail,
                ),
            )
        self._conn.commit()

    def replace_defenses(
        self,
        engagement_id: str,
        host_id: str,
        defenses: list[DefenseFinding],
    ) -> None:
        """Overwrite a host's defenses with a fresh observation snapshot."""
        self._conn.execute(
            "DELETE FROM defenses WHERE engagement_id = ? AND host_id = ?",
            (engagement_id, host_id),
        )
        self.add_defenses(engagement_id, host_id, defenses)

    def add_attempt(self, engagement_id: str, attempt: AttemptRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO attempts (engagement_id, technique, target, outcome, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                engagement_id,
                attempt.technique,
                attempt.target,
                attempt.outcome,
                attempt.detail,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()

    def list_attempts(self, engagement_id: str) -> list[AttemptRecord]:
        rows = self._conn.execute(
            """
            SELECT technique, target, outcome, detail, created_at
            FROM attempts WHERE engagement_id = ? ORDER BY id
            """,
            (engagement_id,),
        ).fetchall()
        return [
            AttemptRecord(
                technique=row["technique"],
                target=row["target"],
                outcome=row["outcome"],
                detail=row["detail"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add_note(self, engagement_id: str, host_id: str, note: str) -> None:
        self._conn.execute(
            """
            INSERT INTO host_notes (engagement_id, host_id, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (engagement_id, host_id, note, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def save_host_runtime(self, engagement_id: str, host_id: str, host: HostRuntime) -> None:
        """Persist connection fields only."""
        if not self._host_exists(engagement_id, host_id):
            self.upsert_host(
                engagement_id,
                host_id,
                transport=host.transport,
                address=host.address,
                user=host.user,
                via=list(host.via),
                discovered_from=host.discovered_from,
                os=host.os,
                hostname=host.hostname,
                arch=host.arch,
            )
        else:
            self._conn.execute(
                """
                UPDATE hosts SET
                    transport = ?, address = ?, user = ?, via_json = ?,
                    discovered_from = ?, os = ?, hostname = ?, arch = ?
                WHERE engagement_id = ? AND host_id = ?
                """,
                (
                    host.transport.value,
                    host.address,
                    host.user,
                    json.dumps(host.via),
                    host.discovered_from,
                    host.os,
                    host.hostname,
                    host.arch,
                    engagement_id,
                    host_id,
                ),
            )
        self._conn.commit()

    def save_state(self, state: EngagementState) -> None:
        if state.notes is not None:
            self.set_engagement_notes(state.engagement_id, state.notes)
        for host_id, host in state.hosts.items():
            self.save_host_runtime(state.engagement_id, host_id, host)

    def host_exists(self, engagement_id: str, host_id: str) -> bool:
        return self._host_exists(engagement_id, host_id)

    def _host_exists(self, engagement_id: str, host_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM hosts WHERE engagement_id = ? AND host_id = ?",
            (engagement_id, host_id),
        ).fetchone()
        return row is not None

    def _insert_seed_host(self, engagement_id: str, seed: HostSeed) -> None:
        self._conn.execute(
            """
            INSERT INTO hosts (
                engagement_id, host_id, transport, address, user, via_json,
                discovered_from, runner_endpoint, runner_ready_announced,
                os, hostname, arch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?)
            """,
            (
                engagement_id,
                seed.id,
                seed.transport.value,
                seed.address,
                seed.user,
                json.dumps(seed.via),
                seed.discovered_from,
                seed.os,
                seed.hostname,
                seed.arch,
            ),
        )
        if seed.tags:
            self.add_tags(engagement_id, seed.id, seed.tags)
        if seed.services:
            self.add_services(engagement_id, seed.id, seed.services)
        if seed.credentials:
            self.add_credentials(engagement_id, seed.id, seed.credentials)
        if seed.defenses:
            self.add_defenses(engagement_id, seed.id, seed.defenses)
        for note in seed.notes:
            self.add_note(engagement_id, seed.id, note)

    def _load_tags(self, engagement_id: str, host_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT tag FROM host_tags WHERE engagement_id = ? AND host_id = ? ORDER BY tag",
            (engagement_id, host_id),
        ).fetchall()
        return [row["tag"] for row in rows]

    def _load_services(self, engagement_id: str, host_id: str) -> list[ServiceFinding]:
        rows = self._conn.execute(
            """
            SELECT port, protocol, product, url, notes
            FROM services WHERE engagement_id = ? AND host_id = ?
            ORDER BY id
            """,
            (engagement_id, host_id),
        ).fetchall()
        return [
            ServiceFinding(
                port=row["port"],
                protocol=row["protocol"],
                product=row["product"],
                url=row["url"],
                notes=row["notes"],
            )
            for row in rows
        ]

    def _load_credentials(self, engagement_id: str, host_id: str) -> list[CredentialFinding]:
        rows = self._conn.execute(
            """
            SELECT username, secret, cred_type, source, notes
            FROM credentials WHERE engagement_id = ? AND host_id = ?
            ORDER BY id
            """,
            (engagement_id, host_id),
        ).fetchall()
        return [
            CredentialFinding(
                username=row["username"],
                secret=row["secret"],
                type=row["cred_type"],
                source=row["source"],
                notes=row["notes"],
            )
            for row in rows
        ]

    def _load_defenses(self, engagement_id: str, host_id: str) -> list[DefenseFinding]:
        rows = self._conn.execute(
            """
            SELECT category, name, present, detail
            FROM defenses WHERE engagement_id = ? AND host_id = ?
            ORDER BY id
            """,
            (engagement_id, host_id),
        ).fetchall()
        return [
            DefenseFinding(
                category=row["category"],
                name=row["name"],
                present=bool(row["present"]),
                detail=row["detail"],
            )
            for row in rows
        ]

    def _load_notes(self, engagement_id: str, host_id: str) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT note FROM host_notes WHERE engagement_id = ? AND host_id = ?
            ORDER BY id
            """,
            (engagement_id, host_id),
        ).fetchall()
        return [row["note"] for row in rows]


def _service_identity(
    service: ServiceFinding,
) -> tuple[int | None, str | None, str | None, str | None]:
    return (service.port, service.protocol, service.product, service.url)
