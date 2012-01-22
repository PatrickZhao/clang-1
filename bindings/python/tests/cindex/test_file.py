from clang.cindex import File
from clang.cindex import Index
from nose.plugins.skip import SkipTest
from nose.tools import ok_
from nose.tools import raises

def test_file():
  index = Index.create()
  tu = index.parse('t.c', unsaved_files = [('t.c', "")])
  file = File(filename='t.c', tu=tu)
  assert str(file) == "t.c"
  assert file.name == "t.c"
  assert repr(file) == "<File: t.c>"
  assert not file.is_multiple_include_guarded

def test_is_include_guarded():
    header = """
#pragma once

int foo();
"""

    index = Index.create()
    tu = index.parse('t.h', unsaved_files = [('t.h', header)])
    file = File(filename='t.h', tu=tu)
    assert str(file) == 't.h'

    raise SkipTest("is_multiple_include_guarded doesn't seem to work.")
    assert file.is_multiple_include_guarded

@raises(Exception)
def test_unknown_file():
    """Ensure that constructing a file not in a TU raises."""

    index = Index.create()
    tu = index.parse('t.c', unsaved_files=[('t.c', 'int foo;')])

    File(filename='foo.c', tu=tu)

def test_from_name():
    """Ensure that File.from_name works."""

    index = Index.create()
    tu = index.parse('t.c', unsaved_files=[('t.c', 'int foo;')])

    f = File.from_name(tu, 't.c')
    ok_(isinstance(f, File))
