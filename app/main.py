"""FastAPI application for the blast web form.

This is a rewrite of the legacy Symfony ``docker-sf-blast`` application,
keeping the blast web parameters and the ``banks.yml`` / ``links.yml``
configuration files.
"""
import os
import re
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import forms
from .command import build_blast_command
from .config import get_settings
from .database import get_db, init_db
from .dbprovider import load_db_provider
from .mail import build_mail_body
from .models import Job, ResultFile
from .scheduler import get_scheduler
from .schemas import BlastRequest

APP_DIR = Path(__file__).resolve().parent

settings = get_settings()

app = FastAPI(title=settings.app_title)
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

db_provider = load_db_provider(settings.banks_config)

DEFAULT_VALUES = {
    name: field.default for name, field in BlastRequest.model_fields.items()
}


def _static_url(request: Request, path: str) -> str:
    return f"{settings.base_url_path}/static/{path}"


# --------------------------------------------------------------------------
# Form / request helpers
# --------------------------------------------------------------------------

def _bool_from_form(value) -> bool:
    if isinstance(value, bool):
        return value
    return value is not None and str(value).lower() in ("on", "true", "1")


def _num(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _request_from_form(form_fields: dict, file_paths: dict) -> BlastRequest:
    data = {
        "title": form_fields.get("title") or "",
        "email": form_fields.get("email") or "",
        "program": form_fields.get("program") or "blastn",
        "blastnType": form_fields.get("blastnType") or "blastn",
        "blastpType": form_fields.get("blastpType") or "blastp",
        "pastedSeq": form_fields.get("pastedSeq") or "",
        "queryCode": form_fields.get("queryCode") or "1",
        "dbCode": form_fields.get("dbCode") or "1",
        "bankTypeNuc": form_fields.get("bankTypeNuc") or "pubdb",
        "bankTypeProt": form_fields.get("bankTypeProt") or "pubdb",
        "dbPath": form_fields.get("dbPath") or "",
        "maxTargetSequences": form_fields.get("maxTargetSequences") or "100",
        "expect": form_fields.get("expect") or "0.1",
        "wordSizesProt": form_fields.get("wordSizesProt") or "3",
        "wordSizesBlastn": form_fields.get("wordSizesBlastn") or "11",
        "wordSizesMegablast": form_fields.get("wordSizesMegablast") or "28",
        "wordSizesDcMegablast": form_fields.get("wordSizesDcMegablast") or "11",
        "matricesNuc": form_fields.get("matricesNuc") or "2,-3",
        "matricesMegablast": form_fields.get("matricesMegablast") or "1,-2",
        "matricesProt": form_fields.get("matricesProt") or "BLOSUM62",
        "gapCostsBlastn": form_fields.get("gapCostsBlastn") or "5,2",
        "gapCostsProt": form_fields.get("gapCostsProt") or "11,1",
        "templateTypes": form_fields.get("templateTypes") or "coding",
        "templateLengths": form_fields.get("templateLengths") or "18",
        "compositionalAdjustments": form_fields.get("compositionalAdjustments") or "2",
        "compositionalAdjustmentsDelta": form_fields.get("compositionalAdjustmentsDelta") or "2",
        "lowComplex": _bool_from_form(form_fields.get("lowComplex")),
        "softMasking": _bool_from_form(form_fields.get("softMasking")),
        "lowerCase": _bool_from_form(form_fields.get("lowerCase")),
        "psiThreshold": _num(form_fields.get("psiThreshold"), 0.005),
        "deltaThreshold": _num(form_fields.get("deltaThreshold"), 0.05),
        "psiIterationNb": int(_num(form_fields.get("psiIterationNb"), 10)),
        "psiPseudoCount": int(_num(form_fields.get("psiPseudoCount"), 0)),
    }
    data.update({k: v for k, v in file_paths.items() if v})
    return BlastRequest(**data)


def _validation_errors(exc: ValidationError) -> dict:
    """Map pydantic validation errors to form field names."""
    errors = {}
    for err in exc.errors():
        loc = err.get("loc", ())
        field = loc[0] if loc else ""
        msg = err.get("msg", "Invalid value")
        msg = msg.replace("Value error, ", "")
        # Sequence / db errors are reported on more visible fields.
        if field in ("pastedSeq", "fileSeq", "psiPSSM"):
            field = "pastedSeq"
        elif field in ("persoBankFile", "dbPath", "bankTypeNuc", "bankTypeProt"):
            field = "bankTypeNuc"
        errors[field] = msg
    return errors


def _render(request: Request, name: str, ctx: dict, status_code: int = 200):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _render_index(request: Request, values: dict = None, errors: dict = None):
    ctx = {
        "request": request,
        "static_url": lambda p: _static_url(request, p),
        "base_url_path": settings.base_url_path,
        "main_title": settings.app_title,
        "values": values or dict(DEFAULT_VALUES),
        "errors": errors or {},
        "programs": forms.PROGRAM_CHOICES,
        "blastn_types": forms.BLASTN_TYPE_CHOICES,
        "blastp_types": [
            (k, v) for k, v in forms.BLASTP_TYPE_CHOICES
            if not (k == "deltablast" and not settings.cdd_delta_path)
        ],
        "bank_types": forms.BANK_TYPE_CHOICES,
        "expects": forms.EXPECT_CHOICES,
        "nuc_matrices": forms.NUC_MATRIX_CHOICES,
        "prot_matrices": forms.PROT_MATRIX_CHOICES,
        "genetic_codes": forms.GENETIC_CODE_CHOICES,
        "max_targets": forms.MAX_TARGET_CHOICES,
        "prot_word_sizes": forms.PROT_WORD_SIZE_CHOICES,
        "blastn_word_sizes": forms.BLASTN_WORD_SIZE_CHOICES,
        "megablast_word_sizes": forms.MEGABLAST_WORD_SIZE_CHOICES,
        "dc_megablast_word_sizes": forms.DC_MEGABLAST_WORD_SIZE_CHOICES,
        "blastn_gap_costs": forms.BLASTN_GAP_COST_CHOICES,
        "prot_gap_costs": forms.PROT_GAP_COST_CHOICES,
        "template_types": forms.TEMPLATE_TYPE_CHOICES,
        "template_lengths": forms.TEMPLATE_LENGTH_CHOICES,
        "compositional_adjustments": forms.COMPOSITIONAL_ADJUSTMENT_CHOICES,
        "compositional_adjustments_delta": forms.COMPOSITIONAL_ADJUSTMENT_DELTA_CHOICES,
        "nucleic_banks": db_provider.get_nucleic_databanks(),
        "proteic_banks": db_provider.get_proteic_databanks(),
    }
    return _render(request, "index.html", ctx)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _render_index(request)


@app.post("/", response_class=HTMLResponse)
async def submit(
    request: Request,
    title: str = Form(""),
    email: str = Form(""),
    program: str = Form("blastn"),
    blastnType: str = Form("blastn"),
    blastpType: str = Form("blastp"),
    pastedSeq: str = Form(""),
    queryCode: str = Form("1"),
    dbCode: str = Form("1"),
    bankTypeNuc: str = Form("pubdb"),
    bankTypeProt: str = Form("pubdb"),
    dbPath: str = Form(""),
    maxTargetSequences: str = Form("100"),
    expect: str = Form("0.1"),
    wordSizesProt: str = Form("3"),
    wordSizesBlastn: str = Form("11"),
    wordSizesMegablast: str = Form("28"),
    wordSizesDcMegablast: str = Form("11"),
    matricesNuc: str = Form("2,-3"),
    matricesMegablast: str = Form("1,-2"),
    matricesProt: str = Form("BLOSUM62"),
    gapCostsBlastn: str = Form("5,2"),
    gapCostsProt: str = Form("11,1"),
    templateTypes: str = Form("coding"),
    templateLengths: str = Form("18"),
    compositionalAdjustments: str = Form("2"),
    compositionalAdjustmentsDelta: str = Form("2"),
    lowComplex: str = Form("on"),
    softMasking: str = Form("on"),
    lowerCase: str = Form(""),
    psiThreshold: str = Form("0.005"),
    deltaThreshold: str = Form("0.05"),
    psiIterationNb: str = Form("10"),
    psiPseudoCount: str = Form("0"),
    fileSeq: UploadFile | None = File(None),
    persoBankFile: UploadFile | None = File(None),
    psiPSSM: UploadFile | None = File(None),
    phiPattern: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    form_fields = {
        "title": title, "email": email, "program": program,
        "blastnType": blastnType, "blastpType": blastpType, "pastedSeq": pastedSeq,
        "queryCode": queryCode, "dbCode": dbCode, "bankTypeNuc": bankTypeNuc,
        "bankTypeProt": bankTypeProt, "dbPath": dbPath,
        "maxTargetSequences": maxTargetSequences, "expect": expect,
        "wordSizesProt": wordSizesProt, "wordSizesBlastn": wordSizesBlastn,
        "wordSizesMegablast": wordSizesMegablast, "wordSizesDcMegablast": wordSizesDcMegablast,
        "matricesNuc": matricesNuc, "matricesMegablast": matricesMegablast,
        "matricesProt": matricesProt, "gapCostsBlastn": gapCostsBlastn,
        "gapCostsProt": gapCostsProt, "templateTypes": templateTypes,
        "templateLengths": templateLengths, "compositionalAdjustments": compositionalAdjustments,
        "compositionalAdjustmentsDelta": compositionalAdjustmentsDelta,
        "lowComplex": lowComplex, "softMasking": softMasking, "lowerCase": lowerCase,
        "psiThreshold": psiThreshold, "deltaThreshold": deltaThreshold,
        "psiIterationNb": psiIterationNb, "psiPseudoCount": psiPseudoCount,
    }

    # Create the job and its working directory first.
    scheduler = get_scheduler()
    job = Job()
    job.program_name = settings.jobs_sched_name
    job.generate_job_uid()
    job.title = title
    job.email = email
    work_dir = scheduler.get_work_dir(job)

    def save_upload(upload: UploadFile | None, filename: str) -> str:
        if not upload or not upload.filename:
            return ""
        dest = os.path.join(work_dir, filename)
        with open(dest, "wb") as fh:
            fh.write(upload.file.read())
        return filename

    # Save uploaded files.
    file_paths = {}
    try:
        file_paths["persoBankFile"] = save_upload(persoBankFile, "uploadedDB.fasta")
        uploaded_file_seq = save_upload(fileSeq, "input.fasta")
        if pastedSeq:
            with open(os.path.join(work_dir, "input.fasta"), "w") as fh:
                fh.write(pastedSeq)
        elif uploaded_file_seq:
            file_paths["fileSeq"] = uploaded_file_seq
        file_paths["psiPSSM"] = save_upload(psiPSSM, "input.pssm")
        file_paths["phiPattern"] = save_upload(phiPattern, "input.pattern")
    except OSError as exc:
        return _render_index(request, dict(DEFAULT_VALUES, **form_fields), {"pastedSeq": f"Could not create file: {exc}"})

    # Build and validate the request.
    try:
        brequest = _request_from_form(form_fields, file_paths)
    except ValidationError as exc:
        return _render_index(request, dict(DEFAULT_VALUES, **form_fields), _validation_errors(exc))

    if not brequest.is_perso_db() and brequest.dbPath and not db_provider.is_valid_path(brequest.dbPath):
        return _render_index(request, dict(DEFAULT_VALUES, **form_fields), {"bankTypeNuc": "The value you selected is not a valid choice"})

    # Build the command script.
    result_url = scheduler.get_result_url(job)
    command = build_blast_command(
        brequest,
        work_dir=work_dir,
        job_uid=job.job_uid,
        result_url=result_url,
        cdd_delta=settings.cdd_delta_path,
        pre_command=settings.pre_command,
        link_command=settings.link_command,
        link_config=settings.links_config,
    )
    job.command = command

    # Declared result files.
    if brequest.program == "blastp" and brequest.blastpType == "phiblast":
        result_files = {"HTML blast output": f"{job.job_uid}.html", "Executed command": "blast_command.txt"}
    else:
        result_files = {
            "HTML blast output": f"{job.job_uid}.html",
            "GFF3 blast output": f"{job.job_uid}.gff3",
            "Text blast output": f"{job.job_uid}.txt",
            "Comma-separated blast output": f"{job.job_uid}.csv",
            "Tabular blast output": f"{job.job_uid}.tsv",
            "XML blast output": f"{job.job_uid}.xml",
            "ASN.1 archive blast output": f"{job.job_uid}.asn",
            "Executed command": "blast_command.txt",
        }
    if brequest.program == "blastp" and brequest.blastpType in ("psiblast", "deltablast"):
        result_files["PSSM"] = f"{job.job_uid}.pssm"
        result_files["PSSM ASCII"] = f"{job.job_uid}.pssm.ascii"

    for display_name, fs_name in result_files.items():
        job.result_files.append(ResultFile(display_name=display_name, fs_name=fs_name))

    # Back url = this form.
    back_url = str(request.base_url).rstrip("/") + settings.base_url_path + "/"
    job.back_url = back_url

    # Prepare the email body file.
    if job.has_valid_email():
        results_url = f"{settings.result_url_host}{settings.base_url_path}job/results/{job.job_uid}"
        body = build_mail_body(job, result_url, results_url, back_url)
        Path(work_dir, "mail_body.txt").write_text(body)

    # Launch the job.
    try:
        job = scheduler.execute(job)
    except Exception as exc:  # noqa: BLE001 - show a friendly error page
        return _render_error(request, job.job_uid, f"Submission failed: {exc}", job)

    db.add(job)
    db.commit()

    return RedirectResponse(
        f"{settings.base_url_path}/job/status/{job.job_uid}",
        status_code=303,
    )


# --------------------------------------------------------------------------
# Job status / results
# --------------------------------------------------------------------------

def _get_job(db: Session, uid: str):
    return db.get(Job, uid)


@app.get("/job/status/{uid}.js")
def job_status_js(uid: str, db: Session = Depends(get_db)):
    job = _get_job(db, uid)
    if not job or not job.scheduler_job_id:
        return JSONResponse({"status": "unknown", "shouldRedirect": False, "resultsUrl": ""})
    scheduler = get_scheduler()
    text_status = scheduler.get_status_as_text(scheduler.get_status(job, db=db))
    is_finished = scheduler.is_finished(job, db=db)
    return JSONResponse(
        {
            "status": text_status,
            "shouldRedirect": is_finished,
            "resultsUrl": f"{settings.base_url_path}/job/results/{job.job_uid}",
        }
    )


@app.get("/job/status/{uid}", response_class=HTMLResponse)
def job_status(request: Request, uid: str, db: Session = Depends(get_db)):
    job = _get_job(db, uid)
    if not job or not job.scheduler_job_id:
        return _render_error(request, uid, "Job %s is not available." % uid, job)
    scheduler = get_scheduler()
    text_status = scheduler.get_status_as_text(scheduler.get_status(job, db=db))
    if scheduler.is_finished(job, db=db):
        return RedirectResponse(f"{settings.base_url_path}/job/results/{job.job_uid}")
    return _render(request, "status.html", {
        "request": request,
        "static_url": lambda p: _static_url(request, p),
        "base_url_path": settings.base_url_path,
        "job": job,
        "status": text_status,
        "status_js_url": f"{settings.base_url_path}/job/status/{job.job_uid}.js",
    })


def _close_tags(html: str) -> str:
    """Repair an HTML snippet that was cut in the middle of a tag."""
    """Repair an HTML snippet that was cut in the middle of a tag."""
    last_lt = html.rfind("<")
    last_gt = html.rfind(">")
    if last_lt > last_gt:
        html = html[:last_lt]
    opened = re.findall(r"<([a-zA-Z]+)(?: .*)?(?<!/)>", html)
    closed = re.findall(r"</([a-zA-Z]+)>", html)
    if len(opened) == len(closed):
        return html
    for tag in reversed(opened):
        if tag in closed:
            closed.remove(tag)
        else:
            html += f"</{tag}>"
    return html


def _extract_preview(html_file: str):
    """Extract a truncated preview of the blast html output (legacy behaviour)."""
    if not html_file or not os.path.exists(html_file):
        return "", True, True
    size = os.path.getsize(html_file)
    if size <= 0:
        return "", True, True
    with open(html_file, "r", errors="replace") as fh:
        content = fh.read(400000)
    start_pre = content.find("<PRE>")
    end_pre = content.rfind("</BOD")
    if start_pre != -1 and end_pre > start_pre:
        preview = content[start_pre:end_pre]
        truncated = content.rfind("<PRE>") > end_pre
        if truncated:
            preview = _close_tags(preview)
        return preview, False, truncated
    if start_pre != -1:
        preview = _close_tags(content[start_pre:])
        return preview, False, True
    return "", True, False


@app.get("/job/results/{uid}", response_class=HTMLResponse)
def job_results(request: Request, uid: str, db: Session = Depends(get_db)):
    job = _get_job(db, uid)
    if not job or not job.scheduler_job_id:
        return _render_error(request, uid, "Job %s is not available." % uid, job)
    scheduler = get_scheduler()
    if not scheduler.is_finished(job, db=db):
        return RedirectResponse(f"{settings.base_url_path}/job/status/{job.job_uid}")
    text_status = scheduler.get_status_as_text(scheduler.get_status(job, db=db))
    result_url = scheduler.get_result_url(job)

    work_dir = scheduler.get_work_dir(job)
    html_file = ""
    for file in job.result_files:
        if file.display_name == "HTML blast output":
            html_file = os.path.join(work_dir, file.fs_name)

    preview_results, crashed, truncated = _extract_preview(html_file)

    return _render(request, "results.html", {
        "request": request,
        "static_url": lambda p: _static_url(request, p),
        "base_url_path": settings.base_url_path,
        "job": job,
        "status": text_status,
        "result_url": result_url,
        "blast_crashed": crashed,
        "preview_results": preview_results,
        "truncated_preview": truncated,
        "back_url": job.back_url,
    })


@app.get("/tmp/{program}/{uid}/{filename}")
def result_file(program: str, uid: str, filename: str, db: Session = Depends(get_db)):
    job = db.get(Job, uid)
    if not job or job.program_name != program:
        return HTMLResponse("Job not found", status_code=404)
    scheduler = get_scheduler()
    base = Path(scheduler.get_work_dir(job)).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base)) or not target.is_file():
        return HTMLResponse("File not found", status_code=404)
    return FileResponse(str(target))


def _render_error(request: Request, uid: str, message: str, job=None):
    return _render(request, "error.html", {
        "request": request,
        "static_url": lambda p: _static_url(request, p),
        "base_url_path": settings.base_url_path,
        "uid": uid,
        "error": message,
        "job": job,
    }, status_code=404)


@app.on_event("startup")
def startup() -> None:
    init_db()
