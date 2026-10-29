"""Databank providers.

Supports the same ``banks.yml`` layout as the original Symfony application:

    genouest_blast:
        db_provider:
            list:
                nucleic:  {'/db/nucl/bank': 'Nucleic bank 1'}
                proteic:  {'/db/prot/bank': 'Protein bank 1'}

Only the ``list`` provider is implemented in this rewrite (``biomaj`` and
``callback`` are not ported). A personal databank upload is still supported by
the application regardless of the configured public banks.
"""
from pathlib import Path

import yaml


class ListDbProvider:
    """A provider backed by a static list of databanks from a YAML file."""

    def __init__(self, nucleic: dict, proteic: dict):
        self.nucleic_banks = dict(nucleic or {})
        self.proteic_banks = dict(proteic or {})

    def get_nucleic_databanks(self) -> dict:
        return self.nucleic_banks

    def get_proteic_databanks(self) -> dict:
        return self.proteic_banks

    def get_all_databanks(self) -> dict:
        banks = dict(self.nucleic_banks)
        banks.update(self.proteic_banks)
        return banks

    def is_valid_path(self, path: str) -> bool:
        return path in self.get_all_databanks()


def load_db_provider(banks_config: str) -> ListDbProvider:
    path = Path(banks_config)
    if not path.exists():
        return ListDbProvider({}, {})
    data = yaml.safe_load(path.read_text())
    blast_cfg = (data or {}).get("genouest_blast", {})
    db_provider = blast_cfg.get("db_provider", {})
    list_cfg = db_provider.get("list", {}) if isinstance(db_provider, dict) else {}
    nucleic = list_cfg.get("nucleic") or {}
    proteic = list_cfg.get("proteic") or {}
    return ListDbProvider(nucleic, proteic)
