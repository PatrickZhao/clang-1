from clang.cindex import File
from clang.cindex import SourceLocation
from clang.cindex import SourceRange
from nose.tools import raises
from .util import get_cursor
from .util import get_tu

default_input = 'int one;\nint two;\n'

@raises(Exception)
def test_empty_constructor():
    """Ensure empty constructor raises."""
    SourceRange()

@raises(ValueError)
def test_missing_tu_with_struct():
    """Ensure missing tu when constructing from struct raises."""
    struct = SourceRange.CXSourceRange()

    SourceRange(structure=struct)

def test_start_end_properties():
    """Ensure start and end properties work."""

    tu = get_tu(default_input)
    start = SourceLocation(source='t.c', tu=tu, offset=0)
    end = SourceLocation(source='t.c', tu=tu, offset=4)

    r = SourceRange(start=start, end=end)

    # Perform twice to verify CachedProperty works.
    assert r.start == start
    assert r.start == start
    assert r.end == end
    assert r.end == end

def test_repr():
    """Ensure repr() format is proper."""
    tu = get_tu(default_input)

    start = SourceLocation(source='t.c', tu=tu, offset=0)
    end = SourceLocation(source='t.c', tu=tu, offset=3)

    r = repr(SourceRange(start=start, end=end))

    assert r == "<SourceRange start <SourceLocation file 't.c', line 1, column 1>," \
           " end <SourceLocation file 't.c', line 1, column 4>>"

def assert_location(loc, line, column, offset):
    assert loc.line == line
    assert loc.column == column
    assert loc.offset == offset

def test_usage():
    """Ensure basic usage of SourceRange works as expected."""
    tu = get_tu(default_input)
    one = get_cursor(tu, 'one')
    two = get_cursor(tu, 'two')

    assert_location(one.extent.start,line=1,column=1,offset=0)
    assert_location(one.extent.end,line=1,column=8,offset=7)
    assert default_input[one.extent.start.offset:one.extent.end.offset] == "int one"

    assert_location(two.extent.start,line=2,column=1,offset=9)
    assert_location(two.extent.end,line=2,column=8,offset=16)
    assert default_input[two.extent.start.offset:two.extent.end.offset] == "int two"

    file = File(filename='t.c', tu=tu)
    location1 = SourceLocation.from_position(tu, file, 1, 1)
    location2 = SourceLocation.from_position(tu, file, 1, 8)

    range1 = SourceRange.from_locations(location1, location2)
    range2 = SourceRange.from_locations(location1, location2)
    assert range1 == range2

    location3 = SourceLocation.from_position(tu, file, 1, 6)
    range3 = SourceRange.from_locations(location1, location3)
    assert range1 != range3
