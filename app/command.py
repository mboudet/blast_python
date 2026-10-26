"""Build the blast shell command from a BlastRequest.

Mirrors the legacy ``command.txt.twig`` template.
"""
from .schemas import BlastRequest


def build_blast_command(
    request: BlastRequest,
    work_dir: str,
    job_uid: str,
    result_url: str,
    cdd_delta: str = "",
    pre_command: str = "",
    link_command: str = "",
    link_config: str = "",
) -> str:
    """Return the full shell script that runs a blast job in ``work_dir``."""

    # ---- db path ----------------------------------------------------------
    if request.is_perso_db():
        db_path = f"{work_dir}uploadedDB"
        dbtype = "prot" if request.program in ("blastp", "blastx") else "nucl"
        make_db = (
            f"makeblastdb -in {work_dir}uploadedDB.fasta -dbtype {dbtype} "
            f"-out {work_dir}uploadedDB -title uploadedDB;"
        )
    else:
        db_path = request.dbPath
        make_db = ""

    # ---- blast command ----------------------------------------------------
    parts = []

    if request.program == "blastp" and request.blastpType in ("psiblast", "phiblast"):
        parts.append("psiblast")
    elif request.program == "blastp" and request.blastpType == "deltablast":
        parts.append("deltablast")
    else:
        bin = request.program
        if request.program == "blastn":
            bin += f" -task {request.blastnType}"
        elif request.program == "blastp":
            bin += f" -task {request.blastpType}"
        parts.append(bin)

    if request.fileSeq or request.pastedSeq:
        parts.append(f"-query {work_dir}input.fasta")

    parts.append(f"-db {db_path}")
    parts.append(f"-evalue {request.expect}")
    parts.append(f"-max_target_seqs {request.maxTargetSequences}")
    parts.append(f"-soft_masking {'true' if request.softMasking else 'false'}")

    if request.lowerCase:
        parts.append("-lcase_masking")

    if request.program == "blastn" and request.blastnType == "megablast":
        parts.append(f"-word_size {request.wordSizesMegablast}")
    elif request.program == "blastn" and request.blastnType == "dc-megablast":
        parts.append(f"-word_size {request.wordSizesDcMegablast}")
    elif request.program == "blastn":
        parts.append(f"-word_size {request.wordSizesBlastn}")
    else:
        parts.append(f"-word_size {request.wordSizesProt}")

    if (
        request.program == "blastn" and
        request.blastnType == "dc-megablast" and
        int(request.templateLengths) != 0
    ):
        parts.append(f"-template_length {request.templateLengths}")
        parts.append(f"-template_type {request.templateTypes}")

    if request.program in ("tblastx", "blastx"):
        parts.append(f"-query_gencode {request.queryCode}")
    if request.program in ("tblastx", "tblastn"):
        parts.append(f"-db_gencode {request.dbCode}")

    if request.program == "blastn":
        matrix = (
            request.matricesMegablast
            if request.blastnType == "megablast"
            else request.matricesNuc
        )
        reward, penalty = matrix.split(",")
        parts.append(f"-reward {reward}")
        parts.append(f"-penalty {penalty}")
    else:
        parts.append(f"-matrix {request.matricesProt}")

    if request.program != "tblastx":
        if request.program == "blastn":
            gap_open, gap_ext = request.gapCostsBlastn.split(",")
        else:
            gap_open, gap_ext = request.gapCostsProt.split(",")
        parts.append(f"-gapopen {gap_open}")
        parts.append(f"-gapextend {gap_ext}")

    if (request.program == "blastp" and request.blastpType != "deltablast") or (
        request.program == "tblastn"
    ):
        parts.append(f"-comp_based_stats {request.compositionalAdjustments}")
    elif request.program == "blastp" and request.blastpType == "deltablast":
        parts.append(f"-comp_based_stats {request.compositionalAdjustmentsDelta}")

    if request.program == "blastn":
        parts.append(f"-dust {'yes' if request.lowComplex else 'no'}")
    else:
        parts.append(f"-seg {'yes' if request.lowComplex else 'no'}")

    if request.program == "blastp" and request.blastpType in (
        "psiblast",
        "phiblast",
        "deltablast",
    ):
        parts.append(f"-inclusion_ethresh {request.psiThreshold}")
        parts.append(f"-num_iterations {request.psiIterationNb}")
        parts.append(f"-pseudocount {request.psiPseudoCount}")
        if request.blastpType in ("psiblast", "deltablast"):
            parts.append(f"-out_pssm {work_dir}{job_uid}.pssm")
            parts.append(f"-out_ascii_pssm {work_dir}{job_uid}.pssm.ascii")
        if request.blastpType == "psiblast" and request.psiPSSM:
            parts.append(f"-in_pssm {work_dir}input.pssm")
        if request.blastpType == "phiblast" and request.phiPattern:
            parts.append(f"-phi_pattern {work_dir}input.pattern")
        if request.blastpType == "deltablast":
            parts.append(f"-rpsdb {cdd_delta}")

    parts.append("-num_threads 4")

    if request.program == "blastp" and request.blastpType == "phiblast":
        parts.append(f"-outfmt 0 -html -out {work_dir}{job_uid}.html;")
    else:
        parts.append(f"-outfmt 11 -out {work_dir}{job_uid}.asn;")

    blast_command = " ".join(parts)

    # ---- script -----------------------------------------------------------
    lines = []
    lines.append(f"cd {work_dir}")
    lines.append("export PATH=./bin/:$PATH;")
    if pre_command:
        lines.append(pre_command)
    lines.append("")
    lines.append(f'echo "{blast_command}" > {work_dir}blast_command.txt;')
    lines.append("")
    if make_db:
        lines.append(make_db)
    lines.append("")
    lines.append(blast_command)
    lines.append("")

    if request.program != "blastp" or request.blastpType != "phiblast":
        lines += [
            f"blast_formatter -archive {work_dir}{job_uid}.asn -outfmt 5 -out {work_dir}{job_uid}.xml;",
            f"blast_formatter -archive {work_dir}{job_uid}.asn -outfmt 0 -html -out {work_dir}{job_uid}.html;",
            f"blast_formatter -archive {work_dir}{job_uid}.asn -outfmt 0 -out {work_dir}{job_uid}.txt;",
            f"blast_formatter -archive {work_dir}{job_uid}.asn -outfmt 6 -out {work_dir}{job_uid}.tsv;",
            f"blast_formatter -archive {work_dir}{job_uid}.asn -outfmt 10 -out {work_dir}{job_uid}.csv;",
            f"xml2gff3.py {work_dir}{job_uid}.xml > {work_dir}{job_uid}.gff3;",
        ]

    if link_command:
        gff3_url = f"{result_url}{job_uid}.gff3"
        lines.append("")
        lines.append(f"export GFF3_URL={gff3_url}")
        cmd = link_command.replace("{config}", link_config) if link_config else link_command
        lines.append(f"{cmd} {work_dir}{job_uid}.html > {work_dir}{job_uid}.htmllinked;")
        lines += [
            f"if [ -s {work_dir}{job_uid}.htmllinked ]",
            "then",
            f"    mv {work_dir}{job_uid}.html {work_dir}{job_uid}.htmlraw;",
            f"    mv {work_dir}{job_uid}.htmllinked {work_dir}{job_uid}.html;",
            "fi",
        ]

    return "\n".join(lines)
