from clang.cindex import CursorKind
from clang.cindex import Index
from clang.cindex import SourceLocation
from clang.cindex import SourceRange
from nose.tools import eq_
from nose.tools import ok_

def get_tu(source):
    index = Index.create()
    return index.parse('t.cpp', unsaved_files=[('t.cpp', source)])

def test_token_to_cursor():
    tu = get_tu('int i = 5;')

    start = SourceLocation(source='t.cpp', offset=0, tu=tu)
    end = SourceLocation(source='t.cpp', offset=9, tu=tu)
    tokens = list(tu.get_tokens(start_location=start, end_location=end))

    assert len(tokens) == 5
    assert tokens[1].spelling == 'i'

    cursor = tokens[1].cursor
    assert cursor.kind == CursorKind.VAR_DECL
    assert tokens[1].cursor == tokens[2].cursor

def test_token_location():
    """Ensure Token.location works."""

    tu = get_tu('int foo = 10;')

    start = SourceLocation(source='t.cpp', offset=0, tu=tu)
    end = SourceLocation(source='t.cpp', offset=11, tu=tu)

    tokens = list(tu.get_tokens(start_location=start, end_location=end))
    eq_(len(tokens), 4)

    loc = tokens[1].location
    ok_(isinstance(loc, SourceLocation))
    eq_(loc.line, 1)
    eq_(loc.column, 5)
    eq_(loc.offset, 4)

def test_token_extent():
    """Ensure Token.extent works."""
    tu = get_tu('int foo = 10;')

    start = SourceLocation(source='t.cpp', offset=0, tu=tu)
    end = SourceLocation(source='t.cpp', offset=11, tu=tu)

    tokens = list(tu.get_tokens(start_location=start, end_location=end))
    eq_(len(tokens), 4)

    extent = tokens[1].extent
    ok_(isinstance(extent, SourceRange))

    eq_(extent.start.offset, 4)
    eq_(extent.end.offset, 7)
