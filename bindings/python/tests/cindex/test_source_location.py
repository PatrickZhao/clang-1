from clang.cindex import File
from clang.cindex import Index
from clang.cindex import SourceLocation
from clang.cindex import TranslationUnit
from nose.tools import eq_
from nose.tools import raises

def get_tu():
    index = Index.create()
    return index.parse('t.c', unsaved_files=[('t.c', 'int i;')])

@raises(ValueError)
def test_invalid_arguments():
    """Ensure ValueError is raised when no arguments given."""
    SourceLocation()

@raises(Exception)
def test_invalid_source_type():
    """Ensure invalid source argument type is detected."""
    SourceLocation(source=[0], tu=get_tu(), line=1, column=1)

@raises(ValueError)
def test_source_without_tu():
    """Ensure source argument without tu raises."""
    SourceLocation(source='t.c', line=1, column=1)

@raises(Exception)
def test_missing_column_argument():
    """Ensure missing column argument raises."""
    SourceLocation(source='t.c', line=1, tu=tu)

def test_valid_constructor():
    """Ensure proper constructor use works."""

    SourceLocation(source='t.c', line=1, column=1, tu=get_tu())
    SourceLocation(source='t.c', offset=2, tu=get_tu())

def test_properties():
    """Ensure properties work as expected."""

    loc = SourceLocation(source='t.c', line=1, column=1, tu=get_tu())

    eq_(loc.line, 1)
    eq_(loc.column, 1)
    eq_(loc.offset, 0)

def test_invalid_location():
    """Ensure locations past end of input get adjusted."""

    loc = SourceLocation(source='t.c', tu=get_tu(), line=5, column=2)

    eq_(loc.line, 1)
    eq_(loc.column, 6)
    eq_(loc.offset, 5)

def test_repr():
    """Ensure repr format is proper."""

    loc = SourceLocation(source='t.c', tu=get_tu(), line=1, column=1)
    r = repr(loc)

    eq_(r, "<SourceLocation file 't.c', line 1, column 1>")

def test_flavor_access():
    """Ensure different SourceLocation flavors work properly."""
    source = """
#define foo bar

int foo = 2;
"""

    index = Index.create()
    tu = index.parse('t.c', unsaved_files=[('t.c', source)])
    loc = SourceLocation(source='t.c', tu=tu, line=3, column=4)

    expansion = loc.expansion_location
    assert len(expansion) == 4
    assert isinstance(expansion[0], File)
    assert isinstance(expansion[1], int)
    assert isinstance(expansion[2], int)
    assert isinstance(expansion[3], int)

    assert expansion[0].name == 't.c'
    assert expansion[1] == 3
    assert expansion[2] == 1
    assert expansion[3] == 17

    spelling = loc.spelling_location
    assert len(spelling) == 4
    assert isinstance(spelling[0], File)
    assert isinstance(spelling[1], int)
    assert isinstance(spelling[2], int)
    assert isinstance(spelling[3], int)

    assert spelling[0].name == 't.c'
    assert spelling[1] == 3
    assert spelling[2] == 1
    assert spelling[3] == 17

def test_presumed_location():
    """Ensure the presumed location property works."""
    source = """
#100 "t.c" 1

int i;
"""

    index = Index.create()
    tu = index.parse('t.c', unsaved_files=[('t.c', source)])
    loc = SourceLocation(source='t.c', tu=tu, line=3, column=1)
    presumed = loc.presumed_location

    assert len(presumed) == 3
    assert isinstance(presumed[0], File)
    assert isinstance(presumed[1], int)
    assert isinstance(presumed[2], int)

    assert presumed[1] == 100
    assert loc.line == 3
