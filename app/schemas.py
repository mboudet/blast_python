"""Blast request model and validation (mirrors the legacy BlastRequest entity)."""
import re

from pydantic import BaseModel, field_validator, model_validator

from . import forms

# Conservative address check: the first character must be alphanumeric (so the
# value can never be read as a command-line option) and shell metacharacters
# (quotes, $, backticks, ;, |, &, parentheses, ...) are rejected outright.
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9_%+][A-Za-z0-9._%+-]*@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$"
)
MAX_EMAIL_LEN = 254
MAX_TITLE_LEN = 255
# Control characters (including CR/LF, which would allow mail header injection).
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

NUCLEIC_PROGRAMS = ("blastn", "tblastn")
PROTEIN_PROGRAMS = ("blastp", "blastx")


def _values(choices):
    """Allowed values of a ``forms`` choice list (plain strings or (value, label))."""
    return frozenset(c[0] if isinstance(c, (tuple, list)) else c for c in choices)


# Every field that ends up on the blast command line is checked against the
# same list that is used to render the corresponding <select> in the form.
ALLOWED_CHOICES = {
    "program": _values(forms.PROGRAM_CHOICES),
    "blastnType": _values(forms.BLASTN_TYPE_CHOICES),
    "blastpType": _values(forms.BLASTP_TYPE_CHOICES),
    "bankTypeNuc": _values(forms.BANK_TYPE_CHOICES),
    "bankTypeProt": _values(forms.BANK_TYPE_CHOICES),
    "queryCode": _values(forms.GENETIC_CODE_CHOICES),
    "dbCode": _values(forms.GENETIC_CODE_CHOICES),
    "maxTargetSequences": _values(forms.MAX_TARGET_CHOICES),
    "expect": _values(forms.EXPECT_CHOICES),
    "wordSizesProt": _values(forms.PROT_WORD_SIZE_CHOICES),
    "wordSizesBlastn": _values(forms.BLASTN_WORD_SIZE_CHOICES),
    "wordSizesMegablast": _values(forms.MEGABLAST_WORD_SIZE_CHOICES),
    "wordSizesDcMegablast": _values(forms.DC_MEGABLAST_WORD_SIZE_CHOICES),
    "matricesNuc": _values(forms.NUC_MATRIX_CHOICES),
    "matricesMegablast": _values(forms.NUC_MATRIX_CHOICES),
    "matricesProt": _values(forms.PROT_MATRIX_CHOICES),
    "gapCostsBlastn": _values(forms.BLASTN_GAP_COST_CHOICES),
    "gapCostsProt": _values(forms.PROT_GAP_COST_CHOICES),
    "templateTypes": _values(forms.TEMPLATE_TYPE_CHOICES),
    "templateLengths": _values(forms.TEMPLATE_LENGTH_CHOICES),
    "compositionalAdjustments": _values(forms.COMPOSITIONAL_ADJUSTMENT_CHOICES),
    "compositionalAdjustmentsDelta": _values(forms.COMPOSITIONAL_ADJUSTMENT_DELTA_CHOICES),
}


class BlastRequest(BaseModel):
    title: str = ""
    email: str = ""
    program: str = "blastn"
    blastnType: str = "blastn"
    blastpType: str = "blastp"
    pastedSeq: str = ""
    queryCode: str = "1"
    dbCode: str = "1"
    bankTypeNuc: str = "pubdb"
    bankTypeProt: str = "pubdb"
    dbPath: str = ""
    maxTargetSequences: str = "100"
    expect: str = "0.1"
    wordSizesProt: str = "3"
    wordSizesBlastn: str = "11"
    wordSizesMegablast: str = "28"
    wordSizesDcMegablast: str = "11"
    matricesNuc: str = "2,-3"
    matricesMegablast: str = "1,-2"
    matricesProt: str = "BLOSUM62"
    gapCostsBlastn: str = "5,2"
    gapCostsProt: str = "11,1"
    templateTypes: str = "coding"
    templateLengths: str = "18"
    compositionalAdjustments: str = "2"
    compositionalAdjustmentsDelta: str = "1"
    lowComplex: bool = True
    softMasking: bool = True
    lowerCase: bool = False
    psiThreshold: float = 0.005
    deltaThreshold: float = 0.05
    psiIterationNb: int = 10
    psiPseudoCount: int = 0

    # Uploaded files are handled separately (paths set after saving to disk).
    fileSeq: str = ""
    persoBankFile: str = ""
    psiPSSM: str = ""
    phiPattern: str = ""

    # ---- helpers ----------------------------------------------------------
    def is_perso_db(self) -> bool:
        if self.program in NUCLEIC_PROGRAMS:
            return self.bankTypeNuc == "persodb"
        return self.bankTypeProt == "persodb"

    def has_query_sequence(self) -> bool:
        return bool(self.pastedSeq or self.fileSeq)

    def has_pssm(self) -> bool:
        return bool(self.psiPSSM)

    @property
    def blastp_types(self):
        choices = dict(forms.BLASTP_TYPE_CHOICES)
        return list(choices.keys())

    # ---- validation -------------------------------------------------------
    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        # The title is shown in e-mails: drop control characters (header
        # injection) and keep it within the database column size.
        return _CTRL_RE.sub(" ", v).strip()[:MAX_TITLE_LEN]

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        if v and (len(v) > MAX_EMAIL_LEN or not EMAIL_RE.fullmatch(v)):
            raise ValueError("Please enter a valid email address")
        return v

    @field_validator(*ALLOWED_CHOICES)
    @classmethod
    def _check_choice(cls, v: str, info) -> str:
        if v not in ALLOWED_CHOICES[info.field_name]:
            raise ValueError("The value you selected is not a valid choice")
        return v

    @field_validator("dbPath")
    @classmethod
    def _check_db_path(cls, v: str) -> str:
        # The real allow-list is the configured banks (checked in main.py);
        # here we only refuse anything that could not be a plain path.
        if v and (_CTRL_RE.search(v) or len(v) > 1024):
            raise ValueError("The value you selected is not a valid choice")
        return v

    @field_validator("psiThreshold", "deltaThreshold")
    @classmethod
    def _check_threshold(cls, v: float) -> float:
        if not 0 <= v <= 1000:
            raise ValueError("Value must be between 0 and 1000")
        return v

    @field_validator("psiIterationNb", "psiPseudoCount")
    @classmethod
    def _check_int(cls, v: int) -> int:
        if not 0 <= v <= 1000:
            raise ValueError("Value must be between 0 and 1000")
        return v

    @model_validator(mode="after")
    def _check_sequences(self) -> "BlastRequest":
        is_psi = self.program == "blastp" and self.blastpType == "psiblast"

        if is_psi:
            if not (self.pastedSeq or self.fileSeq or self.psiPSSM):
                raise ValueError(
                    "Please paste or upload a query sequence, or upload a PSSM"
                )
            chosen = sum([bool(self.pastedSeq), bool(self.fileSeq), bool(self.psiPSSM)])
            if chosen != 1:
                raise ValueError(
                    "You have to choose between pasting a query sequence, "
                    "uploading it, or uploading a PSSM"
                )
        else:
            if not (self.pastedSeq or self.fileSeq):
                raise ValueError("Please paste or upload a query sequence")
            if self.pastedSeq and self.fileSeq:
                raise ValueError(
                    "You have to choose between pasting or uploading a query sequence"
                )

        if self.is_perso_db():
            if not self.persoBankFile:
                raise ValueError(
                    "Please upload a personal databank, or choose a public one"
                )
        elif not self.dbPath:
            raise ValueError(
                "Please upload a personal databank, or choose a public one"
            )

        return self
