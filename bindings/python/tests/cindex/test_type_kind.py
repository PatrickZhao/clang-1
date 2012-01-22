from clang.cindex import TypeKind
from nose.tools import eq_
from nose.tools import ok_
from nose.tools import raises

def test_constructor():
    """Ensure TokenKind constructor works as expected."""

    t = TypeKind(5, 'foo')

    eq_(t.value, 5)
    eq_(t.name, 'foo')

@raises(ValueError)
def test_bad_register():
    """Ensure a duplicate value is rejected for registration."""

    TypeKind.register(2, 'foo')

@raises(ValueError)
def test_unknown_value():
    """Ensure trying to fetch an unknown value raises."""

    TypeKind.from_value(-1)

def test_registration():
    """Ensure that items registered appear as class attributes."""
    ok_(hasattr(TypeKind, 'VOID'))
    void = TypeKind.VOID

    ok_(isinstance(void, TypeKind))

def test_from_value():
    """Ensure registered values can be obtained from from_value()."""
    t = TypeKind.from_value(2)
    ok_(isinstance(t, TypeKind))
    eq_(t, TypeKind.VOID)

def test_repr():
    """Ensure repr() works."""

    r = repr(TypeKind.VOID)
    eq_(r, 'TypeKind.VOID')

def test_spelling():
    """Ensure spelling property works."""
    eq_(TypeKind.VOID.spelling, 'Void')
