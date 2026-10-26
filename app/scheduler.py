"""Job schedulers.

Two backends are supported, selected through ``jobs_method``:

* ``drmaa`` -- submits jobs through the DRMAA C library (python ``drmaa``).
* ``slurm`` -- submits jobs through the Slurm REST API (with a JWT token).

Both share the same job script / working-directory conventions as the legacy
application.
"""
import os
from pathlib import Path

from .config import get_settings
from .models import Job


class Scheduler:
    """Base class defining the scheduler interface."""

    def execute(self, job: Job) -> Job:  # pragma: no cover - abstract
        raise NotImplementedError

    def get_status(self, job: Job):  # pragma: no cover - abstract
        raise NotImplementedError

    def get_status_as_text(self, status) -> str:
        raise NotImplementedError

    def is_finished(self, job: Job) -> bool:
        return False

    def get_work_dir(self, job: Job) -> str:
        settings = get_settings()
        work_dir = os.path.join(settings.jobs_work_dir, job.program_name, job.job_uid)
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        return work_dir

    def get_result_url(self, job: Job) -> str:
        settings = get_settings()
        prefix = f"{settings.result_url_host}{settings.base_url_path}tmp/"
        return f"{prefix}{job.program_name}/{job.job_uid}/"

    def build_job_script(self, job: Job, work_dir: str, lock_file: str = "") -> str:
        """Build the shell script that runs the job (and sends the email)."""
        script_dir = Path(__file__).resolve().parent

        email_part = ""
        if job.has_valid_email():
            mail = script_dir / "mail.py"
            email_part = (
                f'python3 {mail} --to "{job.email}" '
                f'--subject "{job.mail_subject}" '
                f'--body-file "{work_dir}mail_body.txt"'
            )

        lines = ["#!/bin/bash"]
        lines.append(f"exec 3> {work_dir}stdout.txt")
        lines.append(f"exec 4> {work_dir}stderr.txt")
        lines.append("(")
        lines.append(f"    if [ ! -d {work_dir} ]")
        lines.append("    then")
        lines.append(f"        mkdir -p {work_dir}")
        lines.append("    fi")
        for cl in job.command.splitlines():
            lines.append(f"    {cl}")
        lines.append(") 1>&3 2>&4")
        lines.append("")
        if email_part:
            lines.append(email_part)
        if lock_file:
            lines.append(f"rm {lock_file}")
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
        Path(job_file).write_text(script)
        os.chmod(job_file, 0o755)

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

    def get_status(self, job: Job):
        return self._status_code(job)

    def get_status_as_text(self, status) -> str:
        if status == self.STATE_UNDETERMINED:
            return self.TEXT_STATES[self.STATE_FINISHED]
        return self.TEXT_STATES.get(status, "unknown")

    def is_finished(self, job: Job) -> bool:
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
        self.headers = {}
        if settings.slurm_token:
            self.headers["X-SLURM-USER-TOKEN"] = settings.slurm_token

    def _url(self, path: str) -> str:
        return f"{self.base}/slurm/{self.version}/{path}"

    def execute(self, job: Job) -> Job:
        settings = get_settings()
        work_dir = self.get_work_dir(job)

        script = self.build_job_script(job, work_dir, lock_file="")
        job_file = os.path.join(work_dir, f"{job.job_uid}.sh")
        Path(job_file).write_text(script)
        os.chmod(job_file, 0o755)

        sbatch = []
        if settings.slurm_partition:
            sbatch.append(f"#SBATCH --partition={settings.slurm_partition}")
        if settings.slurm_qos:
            sbatch.append(f"#SBATCH --qos={settings.slurm_qos}")
        if settings.slurm_account:
            sbatch.append(f"#SBATCH --account={settings.slurm_account}")
        if settings.slurm_native:
            sbatch.append(f"#SBATCH {settings.slurm_native}")
        full_script = "\n".join(sbatch + [script])

        description = {
            "name": job.program_name,
            "script": full_script,
            "environment": [],
            "workdir": work_dir,
        }

        resp = self._httpx.post(
            self._url("job/submit"),
            json={"job": description},
            headers=self.headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        job_id = data.get("job_id")
        if job_id is None:
            raise RuntimeError(f"Slurm submit failed: {data}")
        job.scheduler_job_id = str(job_id)
        return job

    def get_status(self, job: Job):
        if not job.scheduler_job_id:
            return "UNKNOWN"
        try:
            resp = self._httpx.get(
                self._url(f"job/{job.scheduler_job_id}"),
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            jobs = resp.json().get("jobs") or []
            if not jobs:
                return "UNKNOWN"
            return jobs[0].get("job_state", "UNKNOWN")
        except Exception:
            return "UNKNOWN"

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

    def is_finished(self, job: Job) -> bool:
        status = self.get_status(job)
        return status.upper() in self.FINAL_STATES or status.upper() == "UNKNOWN" and bool(job.scheduler_job_id)


def get_scheduler() -> Scheduler:
    settings = get_settings()
    method = settings.jobs_method.lower()
    if method == "drmaa":
        return DrmaaScheduler()
    if method == "slurm":
        return SlurmScheduler()
    raise ValueError(f"Unsupported jobs_method: {settings.jobs_method!r}")
