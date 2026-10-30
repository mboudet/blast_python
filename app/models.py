"""Database models for blast jobs and their result files."""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Job(Base):
    __tablename__ = "job"

    job_uid: Mapped[str] = mapped_column(String(255), primary_key=True)
    scheduler_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Terminal scheduler state for finished jobs, stored so the status can be
    # served from the database once the job has left the live scheduler.
    scheduler_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Last time the job was observed in an active (non-terminal) state.
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    command: Mapped[str] = mapped_column(Text)
    program_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    back_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_page: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    result_files: Mapped[list["ResultFile"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    result_viewers: Mapped[list["ResultViewer"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    def has_result_files(self) -> bool:
        return len(self.result_files) > 0

    def has_result_viewers(self) -> bool:
        return len(self.result_viewers) > 0

    def has_valid_email(self) -> bool:
        return bool(self.email)

    @property
    def mail_subject(self) -> str:
        title = " ".join((self.title or "").split())
        if title:
            title = f"'{title}' ({self.job_uid})"
        else:
            title = self.job_uid
        return f"{self.program_name}: completion of job {title}"

    def generate_job_uid(self) -> str:
        import re
        import secrets

        # The uid is the only secret protecting a job's results and files, so
        # it must be unguessable: 128 bits from the OS CSPRNG (not ``random``).
        uid = f"{self.program_name}-{secrets.token_hex(16)}"
        uid = re.sub(r"\W", "-", uid)
        self.job_uid = uid.lower()
        return self.job_uid


class ResultFile(Base):
    __tablename__ = "result_file"

    file_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_uid: Mapped[str] = mapped_column(
        String(255), ForeignKey("job.job_uid", ondelete="CASCADE")
    )
    display_name: Mapped[str] = mapped_column(String(255))
    fs_name: Mapped[str] = mapped_column(String(255))

    job: Mapped["Job"] = relationship(back_populates="result_files")


class ResultViewer(Base):
    __tablename__ = "result_viewer"

    viewer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_uid: Mapped[str] = mapped_column(
        String(255), ForeignKey("job.job_uid", ondelete="CASCADE")
    )
    display_name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(255))

    job: Mapped["Job"] = relationship(back_populates="result_viewers")
