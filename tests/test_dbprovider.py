from app.dbprovider import ListDbProvider


def test_loads_banks(banks):
    nucleic = banks.get_nucleic_databanks()
    assert "/db/some/bank" in nucleic
    assert banks.is_valid_path("/db/some/bank")
    assert not banks.is_valid_path("/nonexistent/xyz")


def test_empty_provider():
    p = ListDbProvider({}, {})
    assert p.get_nucleic_databanks() == {}
    assert not p.is_valid_path("/anything")
