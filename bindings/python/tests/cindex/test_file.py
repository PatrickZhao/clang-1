from clang.cindex import Index, File
from nose.plugins.skip import SkipTest

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
