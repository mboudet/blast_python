import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from app import main as main_module  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models import Job  # noqa: E402


class FakeScheduler:
    """Deterministic scheduler for tests (no real cluster)."""

    def __init__(self):
        self.finished = False
        self.job_id = "sched-1"

    def get_work_dir(self, job):
        work_dir = os.path.join("/tmp", job.program_name, job.job_uid)
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        return work_dir

    def get_result_url(self, job):
        return f"/tmp/{job.program_name}/{job.job_uid}/"

    def execute(self, job):
        job.scheduler_job_id = self.job_id
        return job

    def get_status(self, job, db=None):
        return "COMPLETED" if self.finished else "PENDING"

    def get_status_as_text(self, status):
        return "finished" if self.finished else "waiting"

    def is_finished(self, job, db=None):
        return self.finished

    def kill(self, job):
        return True


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session, monkeypatch):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    main_module.app.dependency_overrides[get_db] = override_get_db
    fake = FakeScheduler()
    monkeypatch.setattr(main_module, "get_scheduler", lambda: fake)
    with TestClient(main_module.app) as c:
        yield c, fake
    main_module.app.dependency_overrides.clear()


@pytest.fixture()
def banks():
    from app.config import get_settings
    from app.dbprovider import load_db_provider

    return load_db_provider(get_settings().banks_config)
