"""Job schedulers.

Two backends are supported, selected through ``jobs_method``:

* ``drmaa`` -- submits jobs through the DRMAA C library (python ``drmaa``).
* ``slurm`` -- submits jobs through the Slurm REST API (with a JWT token).

Both share the same job script / working-directory conventions as the legacy
application.
"""
import logging
import os
import shlex
import shutil
from datetime import datetime
from pathlib import Path

from .config import get_settings
from .models import Job

logger = logging.getLogger(__name__)


class Scheduler:
    """Base class defining the scheduler interface."""

    def execute(self, job: Job) -> Job:  # pragma: no cover - abstract
        raise NotImplementedError

    def get_status(self, job: Job, db=None):  # pragma: no cover - abstract
        raise NotImplementedError

    def get_status_as_text(self, status) -> str:
        raise NotImplementedError

    def is_finished(self, job: Job, db=None) -> bool:
        return False

    def get_work_dir(self, job: Job) -> str:
        settings = get_settings()
        work_dir = os.path.join(settings.jobs_work_dir, job.program_name, job.job_uid) + "/"
        # Not world-readable: the directory holds uploads, the submitter's
        # e-mail address and the job script.
        Path(work_dir).mkdir(mode=0o750, parents=True, exist_ok=True)
        return work_dir

    def get_result_url(self, job: Job) -> str:
        settings = get_settings()
        prefix = f"{settings.result_url_host}{settings.base_url_path}tmp/"
        return f"{prefix}{job.program_name}/{job.job_uid}/"

    def build_job_script(self, job: Job, work_dir: str, lock_file: str = "") -> str:
        """Build the shell script that runs the job (and sends the email)."""
        q = shlex.quote
        email_part = ""
        if job.has_valid_email():
            settings = get_settings()
            body_file = os.path.join(work_dir, "mail_body.txt")
            # Everything is single-quoted: no variable/command expansion, and
            # "--" ends option parsing so an address can never act as a flag.
            email_part = (
                f"/bin/mail -s {q(job.mail_subject)} "
                f"-r {q(settings.admin_email)} -- {q(job.email)} < {q(body_file)}"
            )

        wd = work_dir.rstrip("/")
        lines = []
        lines.append(f"exec 3> {q(wd + '/stdout.txt')}")
        lines.append(f"exec 4> {q(wd + '/stderr.txt')}")
        lines.append("(")
        lines.append(f"    if [ ! -d {q(wd)} ]")
        lines.append("    then")
        lines.append(f"        mkdir -p {q(wd)}")
        lines.append("    fi")
        for cl in job.command.splitlines():
            lines.append(f"    {cl}")
        lines.append(") 1>&3 2>&4")
        lines.append("")
        if email_part:
            lines.append(email_part)
        if lock_file:
            lines.append(f"rm {q(lock_file)}")
        return "\n".join(lines)


class DrmaaScheduler(Scheduler):
    """Submit jobs through the DRMAA library (e.g. against a Slurm/SGE cluster)."""

    STATE_UNDETERMINED = 0
    STATE_WAITING = 16
    STATE_RUNNING = 32
    STATE_SUSPENDED = 33
    STATE_FINISHED = 48
    STATE_FAILED = 64

    TEXT_STATES = {
        0: "unknown",
        16: "waiting",
        17: "waiting",
        18: "waiting",
        19: "waiting",
        32: "running",
        33: "suspended",
        34: "suspended",
        35: "suspended",
        48: "finished",
        64: "failed",
    }

    def _session(self):
        import drmaa

        return drmaa.Session()

    def execute(self, job: Job) -> Job:
        import drmaa

        settings = get_settings()
        work_dir = self.get_work_dir(job)
        lock_file = os.path.join(work_dir, f"{job.job_uid}.lock")
        Path(lock_file).touch()

        script = self.build_job_script(job, work_dir, lock_file="")
        job_file = os.path.join(work_dir, f"{job.job_uid}.sh")

        sbatch = ["#!/bin/bash"]
        if settings.slurm_partition:
            sbatch.append(f"#SBATCH --partition={settings.slurm_partition}")
        if settings.slurm_qos:
            sbatch.append(f"#SBATCH --qos={settings.slurm_qos}")
        if settings.slurm_account:
            sbatch.append(f"#SBATCH --account={settings.slurm_account}")
        if settings.slurm_native:
            sbatch.append(f"#SBATCH {settings.slurm_native}")
        full_script = "\n".join(sbatch + [script])

        Path(job_file).write_text(full_script)
        os.chmod(job_file, 0o755)

        # Copy bin folder also
        base_dir = Path(__file__).resolve().parent.parent
        src_dir = base_dir / "bin"

        bin_dir = Path(os.path.join(work_dir, "bin"))
        bin_dir.mkdir(parents=True, exist_ok=True)
        for item in src_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, bin_dir / item.name)
                os.chmod(bin_dir / item.name, 0o755)
        # Also add the 'links.yml' file
        shutil.copy2(settings.links_config, bin_dir / "links.yml")

        session = drmaa.Session()
        try:
            session.initialize()
            jt = session.createJobTemplate()
            jt.remoteCommand = job_file
            jt.jobName = job.program_name
            jt.workingDirectory = work_dir
            if settings.slurm_native:
                jt.nativeSpecification = settings.slurm_native
            job_id = session.runJob(jt)
            session.deleteJobTemplate(jt)
        finally:
            session.exit()

        job.scheduler_job_id = str(job_id)
        return job

    def _status_code(self, job: Job):
        import drmaa

        session = drmaa.Session()
        try:
            session.initialize()
            code = session.jobStatus(job.scheduler_job_id)
        finally:
            session.exit()
        return int(code)

    def get_status(self, job: Job, db=None):
        return self._status_code(job)

    def get_status_as_text(self, status) -> str:
        if status == self.STATE_UNDETERMINED:
            return self.TEXT_STATES[self.STATE_FINISHED]
        return self.TEXT_STATES.get(status, "unknown")

    def is_finished(self, job: Job, db=None) -> bool:
        status = self.get_status(job)
        return status in (self.STATE_UNDETERMINED, self.STATE_FINISHED, self.STATE_FAILED)


class SlurmScheduler(Scheduler):
    """Submit jobs through the Slurm REST API using a JWT token."""

    FINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "BOOT_FAIL", "OUT_OF_MEMORY", "DEADLINE", "REVOKED", "SPECIAL_EXIT"}

    def __init__(self):
        import httpx

        self._httpx = httpx
        settings = get_settings()
        self.base = settings.slurm_rest_url.rstrip("/")
        self.version = settings.slurm_api_version
        self.verify = settings.slurm_verify_tls
        self.headers = {}
        if settings.slurm_user:
            self.headers["X-SLURM-USER-NAME"] = settings.slurm_user

    def _headers(self) -> dict:
        # Read the JWT on every call so a rotated token file is picked up
        # without restarting the server (the file is not cached in memory).
        headers = dict(self.headers)
        token = get_settings().slurm_token
        if token:
            headers["X-SLURM-USER-TOKEN"] = token
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base}/slurm/{self.version}/{path}"

    def _dburl(self, path: str) -> str:
        return f"{self.base}/slurmdb/{self.version}/{path}"

    def execute(self, job: Job) -> Job:
        settings = get_settings()
        work_dir = self.get_work_dir(job)

        script = self.build_job_script(job, work_dir, lock_file="")

        # Copy bin folder also
        base_dir = Path(__file__).resolve().parent.parent
        src_dir = base_dir / "bin"

        bin_dir = Path(os.path.join(work_dir, "bin"))
        bin_dir.mkdir(parents=True, exist_ok=True)
        for item in src_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, bin_dir / item.name)
                os.chmod(bin_dir / item.name, 0o755)
        # Also add the 'links.yml' file
        shutil.copy2(settings.links_config, bin_dir / "links.yml")

        sbatch = ["#!/bin/bash"]
        full_script = "\n".join(sbatch + [script])

        job_file = os.path.join(work_dir, f"{job.job_uid}.sh")
        Path(job_file).write_text(full_script)
        os.chmod(job_file, 0o755)

        description = {
            "name": job.program_name,
            "script": full_script,
            "environment": ["PATH=/usr/local/bin:/usr/bin:/bin"],
            "current_working_directory": work_dir,
        }

        if settings.slurm_partition:
            description['partition'] = settings.slurm_partition
        if settings.slurm_qos:
            description['qos'] = settings.slurm_qos
        if settings.slurm_account:
            description['account'] = settings.slurm_account

        resp = self._httpx.post(
            self._url("job/submit"),
            json={"job": description},
            headers=self._headers(),
            verify=self.verify,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        job_id = data.get("job_id")
        if job_id is None:
            raise RuntimeError(f"Slurm submit failed: {data}")
        job.scheduler_job_id = str(job_id)
        return job

    def get_status(self, job: Job, db=None):
        if not job.scheduler_job_id:
            return "UNKNOWN"
        # Serve a terminal state stored in the database instead of polling the
        # scheduler for this job ID again.
        if job.scheduler_status:
            return job.scheduler_status

        use_db = self._should_use_db(job)
        try:
            data = self._query_status(job, use_db)
        except Exception:
            return "UNKNOWN"

        # The /slurm/ endpoint only knows active jobs. If it reports an invalid
        # job id (e.g. the job has left the live scheduler), fall back to the
        # slurmdb endpoint.
        if data.get("errors") and not use_db:
            use_db = True
            try:
                data = self._query_status(job, use_db)
            except Exception:
                return "UNKNOWN"

        state = self._extract_state(data, use_db)
        if state is None:
            return "UNKNOWN"

        if state.upper() in self.FINAL_STATES:
            # Persist the terminal state and serve it from the DB from now on.
            job.scheduler_status = state
            if db is not None:
                db.commit()
        else:
            job.last_active_at = datetime.utcnow()
            if db is not None:
                db.commit()
        return state

    def _query_status(self, job: Job, use_db: bool):
        url = (
            self._dburl(f"job/{job.scheduler_job_id}")
            if use_db
            else self._url(f"job/{job.scheduler_job_id}")
        )
        resp = self._httpx.get(
            url,
            headers=self._headers(),
            verify=self.verify,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_state(data, use_db: bool):
        jobs = data.get("jobs") or []
        if not jobs:
            return None
        job = jobs[0]
        if use_db:
            return job.get("state", {}).get("current", [None])[0]
        return job.get("job_state", [None])[0]

    def _should_use_db(self, job: Job) -> bool:
        last_active = job.last_active_at
        if last_active is None:
            return False
        settings = get_settings()
        age = (datetime.utcnow() - last_active).total_seconds()
        return age > settings.slurm_inactive_timeout

    def get_status_as_text(self, status) -> str:
        s = (status or "").upper()
        mapping = {
            "PENDING": "waiting",
            "RUNNING": "running",
            "COMPLETING": "running",
            "CONFIGURING": "running",
        }
        if s in mapping:
            return mapping[s]
        if s in self.FINAL_STATES:
            return "finished"
        if s == "FAILED":
            return "failed"
        if s in ("CANCELLED", "TIMEOUT", "NODE_FAIL", "BOOT_FAIL", "OUT_OF_MEMORY", "DEADLINE", "REVOKED", "SPECIAL_EXIT"):
            return "failed"
        return "unknown"

    def is_finished(self, job: Job, db=None) -> bool:
        status = self.get_status(job, db=db)
        return status.upper() in self.FINAL_STATES or status.upper() == "UNKNOWN" and bool(job.scheduler_job_id)


def get_scheduler() -> Scheduler:
    settings = get_settings()
    method = settings.jobs_method.lower()
    if method == "drmaa":
        return DrmaaScheduler()
    if method == "slurm":
        return SlurmScheduler()
    raise ValueError(f"Unsupported jobs_method: {settings.jobs_method!r}")
