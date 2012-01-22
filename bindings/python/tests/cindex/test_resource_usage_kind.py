from clang.cindex import ResourceUsageKind
from nose.tools import eq_
from nose.tools import ok_
from nose.tools import raises

def test_constructor():
    """Ensure ResourceUsageKind constructor works as expected."""

    r = ResourceUsageKind(5, 'foo')

    eq_(r.value, 5)
    eq_(r.name, 'foo')

@raises(ValueError)
def test_bad_register():
    """Ensure a duplicate value is rejected for registration."""

    ResourceUsageKind.register(2, 'foo')

@raises(ValueError)
def test_unknown_value():
    """Ensure trying to fetch an unknown value raises."""

    ResourceUsageKind.from_value(-1)

def test_registration():
    """Ensure that items registered appear as class attributes."""
    ok_(hasattr(ResourceUsageKind, 'AST'))
    ast = ResourceUsageKind.AST

    ok_(isinstance(ast, ResourceUsageKind))

def test_from_value():
    """Ensure registered values can be obtained from from_value()."""
    r = ResourceUsageKind.from_value(1)

    ok_(isinstance(r, ResourceUsageKind))
    eq_(r, ResourceUsageKind.AST)

def test_repr():
    """Ensure repr() works."""

    r = repr(ResourceUsageKind.AST)

    eq_(r, 'ResourceUsageKind.AST')
