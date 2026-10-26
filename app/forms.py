"""Blast web form field definitions and allowed choices.

These mirror the legacy Symfony BlastRequest label/choice methods so the web
parameters behave identically.
"""

PROGRAM_CHOICES = [
    ("blastn", "blastn (nucleotide vs nucleotide)"),
    ("blastp", "blastp (protein vs protein)"),
    ("blastx", "blastx (nucleotide vs protein)"),
    ("tblastn", "tblastn (protein vs nucleotide)"),
    ("tblastx", "tblastx (nucleotide vs nucleotide, but at protein level)"),
]

BLASTN_TYPE_CHOICES = [
    ("megablast", "Highly similar sequences (megablast)"),
    ("dc-megablast", "More dissimilar sequences (discontiguous megablast)"),
    ("blastn", "Somewhat similar sequences (blastn)"),
]

BLASTP_TYPE_CHOICES = [
    ("blastp", "Normal blastp"),
    ("psiblast", "PSI-BLAST (Position-Specific Iterated BLAST)"),
    ("phiblast", "PHI-BLAST (Pattern Hit Initiated BLAST)"),
    ("deltablast", "DELTA-BLAST (Domain Enhanced Lookup Time Accelerated BLAST)"),
]

BANK_TYPE_CHOICES = [
    ("pubdb", "Public databank"),
    ("persodb", "Personal databank"),
]

EXPECT_CHOICES = [
    "1e-20", "1e-10", "0.0001", "0.01", "0.1", "1", "10", "100", "1000",
]

NUC_MATRIX_CHOICES = ["1,-2", "1,-3", "1,-4", "2,-3", "4,-5", "1,-1"]

PROT_MATRIX_CHOICES = ["PAM30", "PAM70", "BLOSUM80", "BLOSUM62", "BLOSUM45"]

GENETIC_CODE_CHOICES = [
    ("1", "Standard"),
    ("2", "Vertebrate Mitochondrial"),
    ("3", "Yeast Mitochondrial"),
    ("4", "Mold Mitochondrial; ..."),
    ("5", "Invertebrate Mitochondrial"),
    ("6", "Ciliate Nuclear; ..."),
    ("9", "Echinoderm Mitochondrial"),
    ("10", "Euplotid Nuclear"),
    ("11", "Bacteria and Archaea"),
    ("12", "Alternative Yeast Nuclear"),
    ("13", "Ascidian Mitochondrial"),
    ("14", "Flatworm Mitochondrial"),
    ("15", "Blepharisma Macrouclear"),
]

MAX_TARGET_CHOICES = ["10", "50", "100", "250", "500", "1000", "5000", "10000", "20000"]

PROT_WORD_SIZE_CHOICES = ["2", "3"]
BLASTN_WORD_SIZE_CHOICES = ["7", "11", "15"]
MEGABLAST_WORD_SIZE_CHOICES = ["16", "20", "24", "28", "32", "48", "64", "128", "256"]
DC_MEGABLAST_WORD_SIZE_CHOICES = ["11", "12"]

BLASTN_GAP_COST_CHOICES = [
    "12,8", "6,5", "5,5", "4,5", "3,5", "4,4", "2,4", "0,4", "3,3", "6,2",
    "5,2", "4,2", "3,2", "2,2", "1,2", "0,2", "4,1", "3,1", "2,1", "1,1",
]

PROT_GAP_COST_CHOICES = [
    "13,3", "12,3", "11,3", "10,3", "15,2", "14,2", "13,2", "12,2", "9,2",
    "8,2", "7,2", "6,2", "5,2", "19,1", "18,1", "17,1", "16,1", "12,1",
    "11,1", "10,1", "9,1", "8,1",
]

TEMPLATE_TYPE_CHOICES = [
    ("coding", "Coding"),
    ("optimal", "Maximal"),
    ("coding_and_optimal", "Two templates"),
]

TEMPLATE_LENGTH_CHOICES = [("0", "None"), ("16", "16"), ("18", "18"), ("21", "21")]

COMPOSITIONAL_ADJUSTMENT_CHOICES = [
    ("0", "No adjustment"),
    ("1", "Composition-based statistics"),
    ("2", "Conditional compositional score matrix adjustment"),
    ("3", "Universal compositional score matrix adjustment"),
]

COMPOSITIONAL_ADJUSTMENT_DELTA_CHOICES = [
    ("0", "No adjustment"),
    ("1", "Composition-based statistics"),
]
