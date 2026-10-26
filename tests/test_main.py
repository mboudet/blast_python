from app.models import Job, ResultFile


def _post(client, **overrides):
    data = {
        "program": "blastn",
        "pastedSeq": ">seq\nACGTACGTACGT",
        "dbPath": "/db/some/bank",
        "bankTypeNuc": "pubdb",
    }
    data.update(overrides)
    return client.post("/", data=data, follow_redirects=False)


def test_index_renders_form(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200
    assert 'name="blast"' in r.text
    assert "nucleicBanks" in r.text


def test_submit_valid_redirects_to_status(client):
    c, _ = client
    r = _post(c)
    assert r.status_code == 303
    assert "/job/status/" in r.headers["location"]


def test_submit_missing_sequence_shows_error(client):
    c, _ = client
    r = _post(c, pastedSeq="")
    assert r.status_code == 200
    assert "query sequence" in r.text


def test_submit_invalid_db_path_shows_error(client):
    c, _ = client
    r = _post(c, dbPath="/nonexistent/xyz")
    assert r.status_code == 200
    assert "valid choice" in r.text


def test_submit_creates_job_with_result_files(client, db_session):
    c, fake = client
    r = _post(c)
    assert r.status_code == 303
    uid = r.headers["location"].rsplit("/", 1)[-1]
    job = db_session.get(Job, uid)
    assert job is not None
    assert job.scheduler_job_id == fake.job_id
    names = [f.display_name for f in job.result_files]
    assert "HTML blast output" in names
    assert "Executed command" in names


def test_status_unknown_job(client):
    c, _ = client
    r = c.get("/job/status/nope")
    assert r.status_code == 404


def test_result_file_served(client, db_session):
    c, fake = client
    r = _post(c)
    uid = r.headers["location"].rsplit("/", 1)[-1]
    job = db_session.get(Job, uid)
    # plant a fake result file
    from app.config import get_settings
    import os

    work_dir = fake.get_work_dir(job)
    with open(os.path.join(work_dir, "blast_command.txt"), "w") as fh:
        fh.write("blastn")
    resp = c.get(f"/tmp/{job.program_name}/{uid}/blast_command.txt")
    assert resp.status_code == 200
    assert resp.text == "blastn"
