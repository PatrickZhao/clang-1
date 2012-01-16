from clang.cindex import CXXAccessSpecifier

def test_from_value():
    a = CXXAccessSpecifier.from_value(0)
    assert a is not None

    assert a == CXXAccessSpecifier.INVALID

def test_from_invalid_value():
    raised = False
    try:
        CXXAccessSpecifier.from_value(8)
    except ValueError:
        raised = True
    finally:
        assert raised

def test_fields():
    a = CXXAccessSpecifier.from_value(1)

    assert str(a) == 'public'
    assert repr(a) == 'CXXAccessSpecifier.PUBLIC'
