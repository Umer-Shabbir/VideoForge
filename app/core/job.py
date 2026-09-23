"""
Job model: wraps a Project for queue management purposes.
Tracks queue state, retry count, timing, and dependencies.
"""

from __future__ import annotations
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class Job:
    project_id: str
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: JobState = JobState.PENDING
    priority: int = 0          # Higher = processed first
    retry_count: int = 0
    max_retries: int = 2
    progress: float = 0.0      # 0.0 – 100.0
    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: str = ""
    log_lines: list[str] = field(default_factory=list)
    ffmpeg_pid: Optional[int] = None

    def elapsed_time(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return end - self.started_at

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries and self.state == JobState.FAILED

    def reset_for_retry(self):
        self.state = JobState.RETRYING
        self.retry_count += 1
        self.progress = 0.0
        self.error = ""
        self.started_at = None
        self.finished_at = None

    @property
    def state_display(self) -> str:
        return self.state.value.capitalize()

    @property
    def is_terminal(self) -> bool:
        return self.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "job_id": self.job_id,
            "state": self.state.value,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "progress": self.progress,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        j = cls(project_id=d["project_id"])
        j.job_id = d.get("job_id", j.job_id)
        j.state = JobState(d.get("state", JobState.PENDING.value))
        j.priority = d.get("priority", 0)
        j.retry_count = d.get("retry_count", 0)
        j.max_retries = d.get("max_retries", 2)
        j.progress = d.get("progress", 0.0)
        j.queued_at = d.get("queued_at", time.time())
        j.started_at = d.get("started_at")
        j.finished_at = d.get("finished_at")
        j.error = d.get("error", "")
        return j
