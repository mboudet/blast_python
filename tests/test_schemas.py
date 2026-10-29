import pytest
from pydantic import ValidationError

from app.schemas import BlastRequest


def _base():
    return {
        "program": "blastn",
        "blastnType": "blastn",
        "pastedSeq": ">seq\nACGTACGTACGT",
        "dbPath": "/db/some/bank",
    }


def test_valid_request():
    req = BlastRequest(**_base())
    assert req.program == "blastn"
    assert req.has_query_sequence()
    assert not req.is_perso_db()


def test_missing_sequence_raises():
    data = _base()
    data["pastedSeq"] = ""
    with pytest.raises(ValidationError):
        BlastRequest(**data)


def test_paste_and_upload_conflict():
    data = _base()
    data["fileSeq"] = "input.fasta"
    with pytest.raises(ValidationError):
        BlastRequest(**data)


def test_invalid_program():
    data = _base()
    data["program"] = "nope"
    with pytest.raises(ValidationError):
        BlastRequest(**data)


def test_perso_db_requires_file():
    data = _base()
    data["bankTypeNuc"] = "persodb"
    with pytest.raises(ValidationError):
        BlastRequest(**data)


def test_perso_db_with_file():
    data = _base()
    data["bankTypeNuc"] = "persodb"
    data["persoBankFile"] = "uploadedDB.fasta"
    req = BlastRequest(**data)
    assert req.is_perso_db()


def test_invalid_email():
    data = _base()
    data["email"] = "not-an-email"
    with pytest.raises(ValidationError):
        BlastRequest(**data)


def test_valid_email():
    data = _base()
    data["email"] = "user@example.com"
    assert BlastRequest(**data).email == "user@example.com"


def test_psi_requires_sequence_or_pssm():
    data = _base()
    data["program"] = "blastp"
    data["blastpType"] = "psiblast"
    data["pastedSeq"] = ""
    with pytest.raises(ValidationError):
        BlastRequest(**data)
