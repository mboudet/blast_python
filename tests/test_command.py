from app.command import build_blast_command
from app.schemas import BlastRequest

WORK_DIR = "/tmp/jobs/blastn/uid1/"
RESULT_URL = "/tmp/blastn/uid1/"


def _req(**overrides):
    data = {
        "program": "blastn",
        "blastnType": "blastn",
        "pastedSeq": ">seq\nACGTACGT",
        "dbPath": "/db/some/bank",
    }
    data.update(overrides)
    return BlastRequest(**data)


def test_uses_input_fasta_query():
    cmd = build_blast_command(_req(), WORK_DIR, "uid1", RESULT_URL)
    assert f"-query {WORK_DIR}input.fasta" in cmd


def test_public_db_path():
    cmd = build_blast_command(_req(), WORK_DIR, "uid1", RESULT_URL)
    assert "-db /db/some/bank" in cmd
    assert "makeblastdb" not in cmd


def test_perso_db_creates_makeblastdb():
    cmd = build_blast_command(
        _req(bankTypeNuc="persodb", persoBankFile="uploadedDB.fasta"),
        WORK_DIR,
        "uid1",
        RESULT_URL,
    )
    assert "makeblastdb" in cmd
    assert "-db " + WORK_DIR + "uploadedDB" in cmd


def test_megablast_word_size_and_matrix():
    cmd = build_blast_command(_req(blastnType="megablast"), WORK_DIR, "uid1", RESULT_URL)
    assert "-word_size 28" in cmd
    assert "-reward 1" in cmd
    assert "-penalty -2" in cmd


def test_blastp_uses_protein_options():
    req = _req(program="blastp", blastpType="blastp", matricesProt="BLOSUM62")
    cmd = build_blast_command(req, WORK_DIR, "uid1", RESULT_URL)
    assert "-matrix BLOSUM62" in cmd
    assert "-seg yes" in cmd


def test_deltablast_requires_cdd():
    req = _req(
        program="blastp",
        blastpType="deltablast",
        deltaThreshold=0.05,
        compositionalAdjustmentsDelta="0",
    )
    cmd = build_blast_command(req, WORK_DIR, "uid1", RESULT_URL, cdd_delta="/cdd")
    assert "-rpsdb /cdd" in cmd
    assert "-out_pssm" in cmd


def test_formatters_skipped_for_phiblast():
    req = _req(program="blastp", blastpType="phiblast")
    cmd = build_blast_command(req, WORK_DIR, "uid1", RESULT_URL)
    assert "blast_formatter" not in cmd
    assert "-outfmt 0 -html -out" in cmd


def test_link_command_substitutes_config():
    req = _req()
    cmd = build_blast_command(
        req,
        WORK_DIR,
        "uid1",
        RESULT_URL,
        link_command="python3 blast_links.py --config {config}",
        link_config="/cfg/links.yml",
    )
    assert "GFF3_URL=" in cmd
    assert "--config /cfg/links.yml" in cmd
