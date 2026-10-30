"""Regression tests for the security review findings."""
import importlib.util
import shlex
import stat
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import main as main_module
from app.command import build_blast_command
from app.models import Job
from app.scheduler import Scheduler
from app.schemas import BlastRequest

BASE = {"pastedSeq": ">s\nACGT", "dbPath": "/db/some/bank"}
PROJECT_DIR = Path(__file__).resolve().parent.parent

INJECTIONS = [
    "0.1; touch /tmp/PWNED #",
    "0.1 $(id)",
    "`id`",
    "1 -out /etc/cron.d/x",
    "1\n-remote",
]


# ---- 1. command injection ---------------------------------------------------

@pytest.mark.parametrize("field", [
    "expect", "maxTargetSequences", "wordSizesBlastn", "wordSizesProt",
    "wordSizesMegablast", "wordSizesDcMegablast", "matricesNuc",
    "matricesMegablast", "matricesProt", "gapCostsBlastn", "gapCostsProt",
    "templateTypes", "templateLengths", "queryCode", "dbCode",
    "compositionalAdjustments", "compositionalAdjustmentsDelta",
    "bankTypeNuc", "bankTypeProt",
])
@pytest.mark.parametrize("payload", INJECTIONS)
def test_free_text_choice_fields_rejected(field, payload):
    with pytest.raises(ValidationError):
        BlastRequest(**BASE, **{field: payload})


@pytest.mark.parametrize("email", [
    "a$(id)@b.com", "a`id`@b.com", 'a"b@b.com', "a;b@b.com", "a b@b.com",
    "-Sfoo=bar@b.com", "a@b.com\nBcc: x@y.z", "a@b",
])
def test_dangerous_emails_rejected(email):
    with pytest.raises(ValidationError):
        BlastRequest(**BASE, email=email)


@pytest.mark.parametrize("email", ["user@example.com", "first.last+tag@sub.example.org"])
def test_normal_emails_accepted(email):
    assert BlastRequest(**BASE, email=email).email == email


def test_title_control_chars_stripped():
    assert "\n" not in BlastRequest(**BASE, title="a\r\nBcc: x@y.z").title


def _stub_bin(work_dir: Path) -> Path:
    bindir = work_dir / "bin"
    bindir.mkdir(parents=True)
    for name in ("blastn", "makeblastdb", "blast_formatter", "xml2gff3.py"):
        f = bindir / name
        f.write_text('#!/bin/bash\nprintf "%s\\n" "$@" >> "$(dirname "$0")/../argv.log"\n')
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return bindir


@pytest.mark.parametrize("payload", INJECTIONS[:3])
def test_generated_script_never_executes_payload_even_if_validation_bypassed(tmp_path, payload):
    """Defence in depth: bypass the schema and run the script with bash."""
    work = tmp_path / "w"
    work.mkdir()
    _stub_bin(work)
    marker = tmp_path / "PWNED"
    evil = f"{payload.split(';')[0]}; touch {marker} ; $(touch {marker}) `touch {marker}`"
    req = BlastRequest.model_construct(**{**BlastRequest(**BASE).model_dump(), "expect": evil})
    script = build_blast_command(req, str(work) + "/", "uid1", "/tmp/blast/uid1/")
    subprocess.run(["bash", "-c", script], check=False, capture_output=True, timeout=20)
    assert not marker.exists(), "injected command was executed"
    # The value reached blastn as ONE literal argument.
    assert evil in (work / "argv.log").read_text().split("\n")


def test_workdir_with_spaces_and_quotes_is_safe(tmp_path):
    work = tmp_path / "we ird'dir"
    work.mkdir()
    _stub_bin(work)
    script = build_blast_command(BlastRequest(**BASE), str(work) + "/", "uid1", "/r/")
    r = subprocess.run(["bash", "-c", script], capture_output=True, timeout=20)
    assert (work / "argv.log").exists(), r.stderr


def test_mail_line_is_single_quoted():
    job = Job()
    job.program_name, job.job_uid, job.command = "blast", "blast-1", "true"
    job.title = 'x" $(touch /tmp/M) `id` \'; rm -rf / #'
    job.email = "a@b.com"
    script = Scheduler().build_job_script(job, "/tmp/w/")
    line = next(l for l in script.splitlines() if l.startswith("/bin/mail"))
    argv = shlex.split(line.split(" < ")[0])
    assert argv[:2] == ["/bin/mail", "-s"]
    assert argv[2] == job.mail_subject          # subject is ONE literal argument
    assert "$(touch" in argv[2]                 # ...and was not expanded
    assert argv[-2:] == ["--", "a@b.com"]


# ---- 4. job ids -------------------------------------------------------------

def test_job_uid_is_unguessable_and_unique():
    uids = set()
    for _ in range(200):
        j = Job(); j.program_name = "blast"
        uids.add(j.generate_job_uid())
    assert len(uids) == 200
    assert all(len(u) >= len("blast-") + 32 for u in uids)


# ---- 2. XSS -----------------------------------------------------------------

def test_preview_is_sanitized():
    dirty = (
        '<PRE><b>ok</b><script>alert(1)</script><img src=x onerror=alert(1)>'
        '<a href="javascript:alert(1)">x</a><a href="#hit1" onclick="evil()">y</a>'
        '<iframe src="//evil"></iframe></PRE>'
    )
    clean = main_module._sanitize_preview(dirty).lower()
    for bad in ("<script", "onerror", "javascript:", "onclick", "<iframe", "<img"):
        assert bad not in clean
    assert "<b>ok</b>" in clean and 'href="#hit1"' in clean


def test_results_page_does_not_render_script(client, db_session):
    c, fake = client
    r = c.post("/", data={"program": "blastn", "pastedSeq": ">s\nACGT", "dbPath": "/db/some/bank"},
               follow_redirects=False)
    uid = r.headers["location"].rsplit("/", 1)[-1]
    job = db_session.get(Job, uid)
    wd = fake.get_work_dir(job)
    html_name = next(f.fs_name for f in job.result_files if f.display_name == "HTML blast output")
    Path(wd, html_name).write_text("<PRE>Query= <script>alert(1)</script>hello</PRE></BODY>")
    fake.finished = True
    page = c.get(f"/job/results/{uid}")
    assert page.status_code == 200
    assert "<script>alert(1)" not in page.text and "hello" in page.text


# ---- 5. file serving --------------------------------------------------------

def _submit(c):
    r = c.post("/", data={"program": "blastn", "pastedSeq": ">s\nACGT", "dbPath": "/db/some/bank"},
               follow_redirects=False)
    return r.headers["location"].rsplit("/", 1)[-1]


def test_only_declared_result_files_are_served(client, db_session):
    c, fake = client
    uid = _submit(c)
    job = db_session.get(Job, uid)
    wd = fake.get_work_dir(job)
    for name in ("stdout.txt", "mail_body.txt", f"{uid}.sh", "uploadedDB.fasta"):
        Path(wd, name).write_text("secret")
        assert c.get(f"/tmp/{job.program_name}/{uid}/{name}").status_code == 404, name
    Path(wd, "blast_command.txt").write_text("ok")
    assert c.get(f"/tmp/{job.program_name}/{uid}/blast_command.txt").status_code == 200


def test_result_files_are_sandboxed(client, db_session):
    c, fake = client
    uid = _submit(c)
    job = db_session.get(Job, uid)
    Path(fake.get_work_dir(job), "blast_command.txt").write_text("x")
    r = c.get(f"/tmp/{job.program_name}/{uid}/blast_command.txt")
    assert "sandbox" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_sibling_job_prefix_not_reachable(client, db_session):
    c, fake = client
    uid = _submit(c)
    job = db_session.get(Job, uid)
    wd = Path(fake.get_work_dir(job))
    sibling = wd.parent / (uid + "9")
    sibling.mkdir()
    (sibling / "blast_command.txt").write_text("other job")
    r = c.get(f"/tmp/{job.program_name}/{uid}/..%2F{uid}9%2Fblast_command.txt")
    assert r.status_code == 404


# ---- 3. abuse limits --------------------------------------------------------

def test_security_headers_present(client):
    c, _ = client
    r = c.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_oversized_upload_rejected_and_cleaned_up(client, monkeypatch):
    c, fake = client
    monkeypatch.setattr(main_module, "MAX_UPLOAD_BYTES", 1024)
    r = c.post("/", data={"program": "blastn", "dbPath": "/db/some/bank"},
               files={"fileSeq": ("q.fa", b">s\n" + b"A" * 5000)})
    assert r.status_code == 200
    assert "too large" in r.text
    assert "location" not in r.headers


def test_oversized_pasted_sequence_rejected(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(main_module, "MAX_UPLOAD_BYTES", 100)
    r = c.post("/", data={"program": "blastn", "dbPath": "/db/some/bank",
                          "pastedSeq": ">s\n" + "A" * 500})
    assert "too large" in r.text


def test_huge_content_length_rejected(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(main_module, "MAX_BODY_BYTES", 10)
    r = c.post("/", data={"program": "blastn", "pastedSeq": ">s\nACGT", "dbPath": "/db/some/bank"})
    assert r.status_code == 413


def test_scheduler_error_not_leaked(client, monkeypatch):
    c, fake = client

    def boom(job):
        raise RuntimeError("http://slurmctld:6820 token=SECRET123")
    monkeypatch.setattr(fake, "execute", boom)
    r = c.post("/", data={"program": "blastn", "pastedSeq": ">s\nACGT", "dbPath": "/db/some/bank"})
    assert "SECRET123" not in r.text and "slurmctld" not in r.text


# ---- blast_links ------------------------------------------------------------

def test_blast_links_escapes_ids_and_uses_safe_yaml():
    spec = importlib.util.spec_from_file_location("blast_links", PROJECT_DIR / "bin" / "blast_links.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "yamlordereddictloader" not in (PROJECT_DIR / "bin" / "blast_links.py").read_text()
    li = mod.LinkInjector()
    li.args = type("A", (), {"gff_url": "http://x/y.gff3"})()
    li.links = [(".+", r"^(\s*>?)?(.+)$", '<a href="http://t/{id}">{id}</a>')]
    out = li.inject_link("db", '><img src=x onerror=alert(1)>')
    assert "<img" not in out and "&lt;img" in out
