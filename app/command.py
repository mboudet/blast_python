"""Build the blast shell command from a BlastRequest.

Mirrors the legacy ``command.txt.twig`` template.

Security note: the returned script is executed by a shell on the compute
nodes. Every value that originates from a request (or from a path derived from
one) is therefore passed through :func:`shlex.quote`, in addition to being
validated against allow-lists in :mod:`app.schemas`. ``pre_command`` and
``link_command`` come from the administrator's configuration and are inserted
as-is on purpose (they are shell snippets).
"""
import shlex

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

    q = shlex.quote
    wd = work_dir if work_dir.endswith("/") else work_dir + "/"

    def path(name: str) -> str:
        """Shell-quoted absolute path of a file inside the job directory."""
        return q(f"{wd}{name}")

    # ---- db path ----------------------------------------------------------
    if request.is_perso_db():
        db_path = f"{wd}uploadedDB"
        dbtype = "prot" if request.program in ("blastp", "blastx") else "nucl"
        make_db = shlex.join([
            "makeblastdb",
            "-in", f"{wd}uploadedDB.fasta",
            "-dbtype", dbtype,
            "-out", f"{wd}uploadedDB",
            "-title", "uploadedDB",
        ]) + ";"
    else:
        db_path = request.dbPath
        make_db = ""

    # ---- blast command (built as an argv list, never as a raw string) -----
    argv: list[str] = []

    if request.program == "blastp" and request.blastpType in ("psiblast", "phiblast"):
        argv.append("psiblast")
    elif request.program == "blastp" and request.blastpType == "deltablast":
        argv.append("deltablast")
    else:
        argv.append(request.program)
        if request.program == "blastn":
            argv += ["-task", request.blastnType]
        elif request.program == "blastp":
            argv += ["-task", request.blastpType]

    if request.fileSeq or request.pastedSeq:
        argv += ["-query", f"{wd}input.fasta"]

    argv += ["-db", db_path]
    argv += ["-evalue", request.expect]
    argv += ["-max_target_seqs", request.maxTargetSequences]
    argv += ["-soft_masking", "true" if request.softMasking else "false"]

    if request.lowerCase:
        argv.append("-lcase_masking")

    if request.program == "blastn" and request.blastnType == "megablast":
        argv += ["-word_size", request.wordSizesMegablast]
    elif request.program == "blastn" and request.blastnType == "dc-megablast":
        argv += ["-word_size", request.wordSizesDcMegablast]
    elif request.program == "blastn":
        argv += ["-word_size", request.wordSizesBlastn]
    else:
        argv += ["-word_size", request.wordSizesProt]

    if (
        request.program == "blastn" and
        request.blastnType == "dc-megablast" and
        int(request.templateLengths) != 0
    ):
        argv += ["-template_length", request.templateLengths]
        argv += ["-template_type", request.templateTypes]

    if request.program in ("tblastx", "blastx"):
        argv += ["-query_gencode", request.queryCode]
    if request.program in ("tblastx", "tblastn"):
        argv += ["-db_gencode", request.dbCode]

    if request.program == "blastn":
        matrix = (
            request.matricesMegablast
            if request.blastnType == "megablast"
            else request.matricesNuc
        )
        reward, penalty = matrix.split(",")
        argv += ["-reward", reward, "-penalty", penalty]
    else:
        argv += ["-matrix", request.matricesProt]

    if request.program != "tblastx":
        if request.program == "blastn":
            gap_open, gap_ext = request.gapCostsBlastn.split(",")
        else:
            gap_open, gap_ext = request.gapCostsProt.split(",")
        argv += ["-gapopen", gap_open, "-gapextend", gap_ext]

    if (request.program == "blastp" and request.blastpType != "deltablast") or (
        request.program == "tblastn"
    ):
        argv += ["-comp_based_stats", request.compositionalAdjustments]
    elif request.program == "blastp" and request.blastpType == "deltablast":
        argv += ["-comp_based_stats", request.compositionalAdjustmentsDelta]

    if request.program == "blastn":
        argv += ["-dust", "yes" if request.lowComplex else "no"]
    else:
        argv += ["-seg", "yes" if request.lowComplex else "no"]

    if request.program == "blastp" and request.blastpType in (
        "psiblast",
        "phiblast",
        "deltablast",
    ):
        argv += ["-inclusion_ethresh", str(request.psiThreshold)]
        argv += ["-num_iterations", str(request.psiIterationNb)]
        argv += ["-pseudocount", str(request.psiPseudoCount)]
        if request.blastpType in ("psiblast", "deltablast"):
            argv += ["-out_pssm", f"{wd}{job_uid}.pssm"]
            argv += ["-out_ascii_pssm", f"{wd}{job_uid}.pssm.ascii"]
        if request.blastpType == "psiblast" and request.psiPSSM:
            argv += ["-in_pssm", f"{wd}input.pssm"]
        if request.blastpType == "phiblast" and request.phiPattern:
            argv += ["-phi_pattern", f"{wd}input.pattern"]
        if request.blastpType == "deltablast":
            argv += ["-rpsdb", cdd_delta]

    argv += ["-num_threads", "4"]

    if request.program == "blastp" and request.blastpType == "phiblast":
        argv += ["-outfmt", "0", "-html", "-out", f"{wd}{job_uid}.html"]
    else:
        argv += ["-outfmt", "11", "-out", f"{wd}{job_uid}.asn"]

    blast_command = shlex.join(argv) + ";"

    # ---- script -----------------------------------------------------------
    lines = []
    lines.append(f"cd {q(wd)}")
    lines.append("export PATH=./bin/:$PATH;")
    if pre_command:
        lines.append(pre_command)
    lines.append("")
    # printf with a single-quoted argument: no expansion of the content.
    lines.append(f"printf '%s\\n' {q(blast_command)} > {path('blast_command.txt')};")
    lines.append("")
    if make_db:
        lines.append(make_db)
    lines.append("")
    lines.append(blast_command)
    lines.append("")

    if request.program != "blastp" or request.blastpType != "phiblast":
        asn, xml = path(f"{job_uid}.asn"), path(f"{job_uid}.xml")
        lines += [
            f"blast_formatter -archive {asn} -outfmt 5 -out {xml};",
            f"blast_formatter -archive {asn} -outfmt 0 -html -out {path(job_uid + '.html')};",
            f"blast_formatter -archive {asn} -outfmt 0 -out {path(job_uid + '.txt')};",
            f"blast_formatter -archive {asn} -outfmt 6 -out {path(job_uid + '.tsv')};",
            f"blast_formatter -archive {asn} -outfmt 10 -out {path(job_uid + '.csv')};",
            f"xml2gff3.py {xml} > {path(job_uid + '.gff3')};",
        ]

    if link_command:
        gff3_url = f"{result_url}{job_uid}.gff3"
        html, linked, raw = (
            path(f"{job_uid}.html"),
            path(f"{job_uid}.htmllinked"),
            path(f"{job_uid}.htmlraw"),
        )
        lines.append("")
        lines.append(f"export GFF3_URL={q(gff3_url)}")
        cmd = link_command.replace("{config}", q(link_config)) if link_config else link_command
        lines.append(f"{cmd} {html} > {linked};")
        lines += [
            f"if [ -s {linked} ]",
            "then",
            f"    mv {html} {raw};",
            f"    mv {linked} {html};",
            "fi",
        ]

    return "\n".join(lines)
