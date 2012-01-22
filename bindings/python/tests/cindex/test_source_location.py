from clang.cindex import Cursor
from clang.cindex import File
from clang.cindex import SourceLocation
from nose.tools import raises
from .util import get_cursor
from .util import get_tu

default_input = 'int one;\nint two;\n'

@raises(ValueError)
def test_invalid_arguments():
    """Ensure ValueError is raised when no arguments given."""
    SourceLocation()

@raises(Exception)
def test_invalid_source_type():
    """Ensure invalid source argument type is detected."""
    SourceLocation(source=[0], tu=get_tu(default_input), line=1, column=1)

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

    SourceLocation(source='t.c', line=1, column=1, tu=get_tu(default_input))
    SourceLocation(source='t.c', offset=2, tu=get_tu(default_input))

def test_properties():
    """Ensure properties work as expected."""

    loc = SourceLocation(source='t.c', line=1, column=1,
            tu=get_tu(default_input))

    assert loc.line == 1
    assert loc.column == 1
    assert loc.offset == 0

def test_invalid_location():
    """Ensure locations past end of input get adjusted."""

    loc = SourceLocation(source='t.c', tu=get_tu('int i;'), line=5, column=2)

    assert loc.line == 1
    assert loc.column == 6
    assert loc.offset == 5

def test_repr():
    """Ensure repr format is proper."""

    loc = SourceLocation(source='t.c', tu=get_tu(default_input), line=1, column=1)
    r = repr(loc)

    assert r == "<SourceLocation file 't.c', line 1, column 1>"

def test_flavor_access():
    """Ensure different SourceLocation flavors work properly."""
    source = """
#define foo bar

int foo = 2;
"""

    tu = get_tu(source)
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

    tu = get_tu(source)
    loc = SourceLocation(source='t.c', tu=tu, line=3, column=1)
    presumed = loc.presumed_location

    assert len(presumed) == 3
    assert isinstance(presumed[0], File)
    assert isinstance(presumed[1], int)
    assert isinstance(presumed[2], int)

    assert presumed[1] == 100
    assert loc.line == 3

def assert_location(loc, line, column, offset):
    assert loc.line == line
    assert loc.column == column
    assert loc.offset == offset

def test_location_from_cursor():
    tu = get_tu(default_input)

    one = get_cursor(tu, 'one')
    two = get_cursor(tu, 'two')

    assert one is not None
    assert two is not None

    assert_location(one.location,line=1,column=5,offset=4)
    assert_location(two.location,line=2,column=5,offset=13)

    # adding a linebreak at top should keep columns same
    tu = get_tu('\n' + default_input)
    one = get_cursor(tu, 'one')
    two = get_cursor(tu, 'two')

    assert one is not None
    assert two is not None

    assert_location(one.location,line=2,column=5,offset=5)
    assert_location(two.location,line=3,column=5,offset=14)

    # adding a space should affect column on first line only
    tu = get_tu(' ' + default_input)
    one = get_cursor(tu, 'one')
    two = get_cursor(tu, 'two')

    assert_location(one.location,line=1,column=6,offset=5)
    assert_location(two.location,line=2,column=5,offset=14)

    # define the expected location ourselves and see if it matches
    # the returned location
    tu = get_tu(default_input)

    file = File(filename='t.c', tu=tu)
    location = SourceLocation.from_position(tu, file, 1, 5)
    cursor = Cursor.from_location(tu, location)

    one = get_cursor(tu, 'one')
    assert one is not None
    assert one == cursor

    # Ensure locations referring to the same entity are equivalent.
    location2 = SourceLocation.from_position(tu, file, 1, 5)
    assert location == location2
    location3 = SourceLocation.from_position(tu, file, 1, 4)
    assert location2 != location3

    offset_location = SourceLocation.from_offset(tu, file, 5)
    cursor = Cursor.from_location(tu, offset_location)
    for n in [n for n in tu.cursor.get_children() if n.spelling == 'one']:
        assert n == cursor
