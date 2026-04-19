from simtest.funnel import compare, version


def test_compare():
    assert compare() is True


def test_version():
    v = version()
    assert isinstance(v, str)
    assert len(v) > 0
