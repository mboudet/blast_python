"""Blast request model and validation (mirrors the legacy BlastRequest entity)."""
import re

from pydantic import BaseModel, field_validator, model_validator

from . import forms

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

NUCLEIC_PROGRAMS = ("blastn", "tblastn")
PROTEIN_PROGRAMS = ("blastp", "blastx")


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
    compositionalAdjustmentsDelta: str = "2"
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
    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        if v and not EMAIL_RE.match(v):
            raise ValueError("Please enter a valid email address")
        return v

    @field_validator("program", "blastnType", "blastpType")
    @classmethod
    def _check_choice(cls, v: str, info) -> str:
        field = info.field_name
        allowed = {
            "program": [c[0] for c in forms.PROGRAM_CHOICES],
            "blastnType": [c[0] for c in forms.BLASTN_TYPE_CHOICES],
            "blastpType": [c[0] for c in forms.BLASTP_TYPE_CHOICES],
        }[field]
        if v not in allowed:
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
