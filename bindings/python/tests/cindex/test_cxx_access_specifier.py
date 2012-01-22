from clang.cindex import CXXAccessSpecifier
from nose.tools import raises

@raises(ValueError)
def test_bad_registration():
    """Ensure that registering a redundant value raises."""
    CXXAccessSpecifier.register(1, 'foo')

def test_from_value():
    a = CXXAccessSpecifier.from_value(0)
    assert a is not None

    assert a == CXXAccessSpecifier.INVALID

@raises(ValueError)
def test_from_invalid_value():
    CXXAccessSpecifier.from_value(8)

def test_fields():
    a = CXXAccessSpecifier.from_value(1)

    assert str(a) == 'public'
    assert repr(a) == 'CXXAccessSpecifier.PUBLIC'
