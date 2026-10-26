# Blast server (FastAPI rewrite)

A rewrite of the legacy Symfony `docker-sf-blast` web application. It keeps the
blast web parameters and the `banks.yml` / `links.yml` configuration files, and
submits jobs through either the DRMAA library or the Slurm REST API (JWT auth).

## Layout

```
blast_python/
├── app/
│   ├── main.py          # FastAPI app, routes
│   ├── config.py        # Settings (pydantic-settings)
│   ├── database.py      # SQLAlchemy engine / session
│   ├── models.py        # Job, ResultFile, ResultViewer
│   ├── dbprovider.py    # Databank provider (banks.yml)
│   ├── forms.py         # Web form field choices
│   ├── schemas.py       # BlastRequest model + validation
│   ├── command.py       # blast command builder
│   ├── scheduler.py     # DRMAA + Slurm REST backends
│   ├── mail.py          # result email (smtp or mail binary)
│   ├── templates/       # Jinja2 templates
│   └── static/          # css/js/images
├── bin/                 # blast_links.py, xml2gff3.py
├── config/              # banks.yml, links.yml
├── requirements.txt
└── .env.example
```

## Run

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The form is served at `/` and the API docs at `/docs`.

## Tests

```bash
pip install -r requirements.txt pytest httpx
pytest
```

The tests use a fake scheduler (no cluster required) and an in-memory SQLite
database. They cover request validation (`tests/test_schemas.py`), the blast
command builder (`tests/test_command.py`), databank loading
(`tests/test_dbprovider.py`) and the HTTP routes (`tests/test_main.py`).

## Container

```bash
docker build -t blast-server .
docker compose up
```

The image installs the NCBI BLAST tools (needed to run the jobs) alongside the
FastAPI server. See `docker-compose.yml` for the env vars; the Slurm JWT can be
mounted as a secret via `SLURM_JWT_FILE`.

## Configuration

See `.env.example` for all options. Key settings:

- `JOBS_METHOD`: `slurm` (default) or `drmaa`.
- `SLURM_REST_URL`, `SLURM_API_VERSION`, `SLURM_JWT` (or `SLURM_JWT_FILE`):
  Slurm REST API endpoint and JWT token sent via `X-SLURM-USER-TOKEN`.
- `DATABASE_URL`: SQLAlchemy URL (SQLite/Postgres/MySQL). If empty, the legacy
  `DB_*` variables are used.
- `BANKS_CONFIG`, `LINKS_CONFIG`: paths to the `banks.yml` / `links.yml` files.
- `CDD_DELTA_PATH`: path to the CDD database (needed for DELTA-BLAST).
- `SMTP_*`: SMTP settings for result emails (falls back to the `mail` binary).

## Scheduler backends

`Scheduler` subclasses implement `execute`, `get_status`, `get_status_as_text`,
`kill` and `is_finished`. `SlurmScheduler` talks to the Slurm REST API
(`POST /slurm/<version>/job/submit` with a `#SBATCH`-prefixed script, then polls
`GET .../job/<id>` and deletes to kill). `DrmaaScheduler` uses the `drmaa`
Python library. `get_scheduler()` selects the backend from `JOBS_METHOD`.
