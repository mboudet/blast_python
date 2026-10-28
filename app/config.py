"""Application configuration.

All settings are read from environment variables, with sane defaults. A local
SQLite file is used by default, but any SQLAlchemy database URL (e.g. a remote
PostgreSQL or MySQL instance) can be provided through ``DATABASE_URL``.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Web / app ---------------------------------------------------------
    app_title: str = "Blast server (v2.2.29+)"
    base_url_path: str = ""
    secret_key: str = "change-me"
    upload_limit: int = 100  # MiB

    # --- Database ----------------------------------------------------------
    # Either a full SQLAlchemy URL (sqlite:///..., postgresql://..., mysql://...)
    # or leave empty to build one from the DB_* variables below.
    database_url: str = ""

    # Legacy style connection parameters (used when database_url is empty).
    db_driver: str = "sqlite"  # sqlite, pgsql, mysql, ...
    db_host: str = ""
    db_port: str = ""
    db_name: str = ""
    db_user: str = ""
    db_pass: str = ""

    # --- Slurm REST API -----------------------------------------------------
    slurm_rest_url: str = "http://slurmctld:6820"
    slurm_api_version: str = "v0.0.40"
    slurm_verify_tls: bool = True  # set False to skip TLS verification
    slurm_jwt: str = ""            # the JWT token
    slurm_jwt_file: str = ""       # optional file containing the JWT token
    slurm_user: str = ""           # submit jobs as this user (X-SLURM-USER-NAME)
    slurm_partition: str = ""
    slurm_qos: str = ""
    slurm_account: str = ""
    slurm_native: str = ""         # extra sbatch option string
    # Once a job has been inactive for longer than this many seconds, poll the
    # slurmdb endpoint instead of the (live-cluster) slurm endpoint.
    slurm_inactive_timeout: int = 600

    # --- Jobs ---------------------------------------------------------------
    jobs_method: str = "slurm"     # only "slurm" is supported in this rewrite
    jobs_work_dir: str = str(Path("/tmp/"))
    jobs_sched_name: str = "blast"
    result_url_host: str = ""      # e.g. https://my.server/ (empty = same host)
    cdd_delta_path: str = ""
    pre_command: str = ""
    link_command: str = (
        "python3  ./bin/blast_links.py"
        "--config ./bin/links.yml --gff-url $GFF3_URL"
    )

    # --- Blast databank -----------------------------------------------------
    banks_config: str = str(PROJECT_DIR / "config" / "banks.yml")
    links_config: str = str(PROJECT_DIR / "config" / "links.yml")
    # --- Mail ---------------------------------------------------------------
    admin_email: str = "admin@blast-server"
    admin_name: str = "Blast admin"
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_use_tls: bool = False

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.db_driver == "sqlite":
            # A local sqlite file next to the project
            path = self.db_name or (PROJECT_DIR / "blast.db")
            return f"sqlite:///{path}"
        driver_map = {
            "pgsql": "postgresql+psycopg2",
            "mysql": "mysql+pymysql",
        }
        driver = driver_map.get(self.db_driver, self.db_driver)
        auth = ""
        if self.db_user:
            auth = self.db_user
            if self.db_pass:
                auth += f":{self.db_pass}"
            auth += "@"
        host = self.db_host
        if self.db_port:
            host = f"{host}:{self.db_port}"
        return f"{driver}://{auth}{host}/{self.db_name}"

    @property
    def slurm_token(self) -> str:
        if self.slurm_jwt:
            return self.slurm_jwt
        if self.slurm_jwt_file:
            return Path(self.slurm_jwt_file).read_text().strip()
        return ""

    @property
    def result_url(self) -> str:
        return f"{self.result_url_host}{self.base_url_path}tmp/"


@lru_cache
def get_settings() -> Settings:
    return Settings()
