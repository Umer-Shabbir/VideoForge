"""
SQLite persistence layer.
Stores projects, jobs, render history, and app metadata.
"""

import sqlite3
import threading
import json
import time
import logging
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from app.core.project import Project, ProjectStatus
from app.core.job import Job, JobState

log = logging.getLogger("videoforge.database")

SCHEMA_VERSION = 3


class Database:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    timeout=30,
                )
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA foreign_keys=ON")
            return self._conn

    @contextmanager
    def _cursor(self):
        with self._lock:
            conn = self._get_conn()
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
            except Exception as e:
                conn.rollback()
                log.error(f"DB error: {e}")
                raise
            finally:
                cur.close()

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'discovered',
                    data_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    data_json TEXT NOT NULL,
                    queued_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS render_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    job_id TEXT,
                    output_path TEXT,
                    render_time REAL,
                    output_size INTEGER,
                    success INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_project ON render_history(project_id)
            """)
            # Check schema version
            cur.execute("SELECT value FROM meta WHERE key='schema_version'")
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),)
                )
            log.debug(f"Database initialized: {self.db_path}")

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ─── Project CRUD ─────────────────────────────────────────────────────────

    def save_project(self, project: Project):
        project.updated_at = time.time()
        data_json = json.dumps(project.to_dict())
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO projects (id, name, folder, status, data_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    folder=excluded.folder,
                    status=excluded.status,
                    data_json=excluded.data_json,
                    updated_at=excluded.updated_at
            """, (
                project.id, project.name, str(project.folder),
                project.status.value, data_json,
                project.created_at, project.updated_at,
            ))

    def load_project(self, project_id: str) -> Optional[Project]:
        with self._cursor() as cur:
            cur.execute("SELECT data_json FROM projects WHERE id=?", (project_id,))
            row = cur.fetchone()
            if row:
                return Project.from_dict(json.loads(row["data_json"]))
        return None

    def load_all_projects(self) -> list[Project]:
        with self._cursor() as cur:
            cur.execute("SELECT data_json FROM projects ORDER BY created_at DESC")
            rows = cur.fetchall()
        projects = []
        for row in rows:
            try:
                projects.append(Project.from_dict(json.loads(row["data_json"])))
            except Exception as e:
                log.error(f"Failed to deserialize project: {e}")
        return projects

    def delete_project(self, project_id: str):
        with self._cursor() as cur:
            cur.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def update_project_status(self, project_id: str, status: ProjectStatus):
        with self._cursor() as cur:
            cur.execute(
                "UPDATE projects SET status=?, updated_at=? WHERE id=?",
                (status.value, time.time(), project_id)
            )

    def get_project_count_by_status(self) -> dict:
        with self._cursor() as cur:
            cur.execute("SELECT status, COUNT(*) as cnt FROM projects GROUP BY status")
            return {row["status"]: row["cnt"] for row in cur.fetchall()}

    # ─── Job CRUD ─────────────────────────────────────────────────────────────

    def save_job(self, job: Job):
        data_json = json.dumps(job.to_dict())
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO jobs (job_id, project_id, state, priority, data_json, queued_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    state=excluded.state,
                    priority=excluded.priority,
                    data_json=excluded.data_json,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at
            """, (
                job.job_id, job.project_id, job.state.value, job.priority,
                data_json, job.queued_at, job.started_at, job.finished_at,
            ))

    def load_pending_jobs(self) -> list[Job]:
        with self._cursor() as cur:
            cur.execute("""
                SELECT data_json FROM jobs
                WHERE state IN ('pending', 'retrying')
                ORDER BY priority DESC, queued_at ASC
            """)
            rows = cur.fetchall()
        return [Job.from_dict(json.loads(r["data_json"])) for r in rows]

    def load_all_jobs(self) -> list[Job]:
        with self._cursor() as cur:
            cur.execute("SELECT data_json FROM jobs ORDER BY queued_at DESC")
            rows = cur.fetchall()
        return [Job.from_dict(json.loads(r["data_json"])) for r in rows]

    def delete_job(self, job_id: str):
        with self._cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))

    def delete_jobs_for_project(self, project_id: str):
        with self._cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE project_id=?", (project_id,))

    # ─── Render History ────────────────────────────────────────────────────────

    def add_render_history(
        self,
        project_id: str,
        job_id: Optional[str],
        output_path: Optional[str],
        render_time: Optional[float],
        output_size: int,
        success: bool,
        error: str = "",
    ):
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO render_history
                (project_id, job_id, output_path, render_time, output_size, success, error, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id, job_id, output_path, render_time,
                output_size, 1 if success else 0, error, time.time()
            ))

    def get_render_stats(self) -> dict:
        with self._cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(success) as success_count,
                    AVG(render_time) as avg_render_time,
                    SUM(output_size) as total_output_size,
                    MIN(timestamp) as first_render,
                    MAX(timestamp) as last_render
                FROM render_history
            """)
            row = cur.fetchone()
            return dict(row) if row else {}

    def get_history_for_project(self, project_id: str) -> list[dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM render_history WHERE project_id=? ORDER BY timestamp DESC",
                (project_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    # ─── App metadata ──────────────────────────────────────────────────────────

    def get_meta(self, key: str, default: str = "") -> str:
        with self._cursor() as cur:
            cur.execute("SELECT value FROM meta WHERE key=?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_meta(self, key: str, value: str):
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value)
            )
