from clang.cindex import CodeCompletionResults
from clang.cindex import CodeCompletionResult
from clang.cindex import Index
from nose.tools import eq_
from nose.tools import ok_

def get_tu(source):
    index = Index.create()
    return index.parse('t.cpp', unsaved_files=[('t.cpp', source)])

def test_code_complete():
    """Ensure basic code completion works."""

    source ="""
class X {
    public:
        void foo();
        void foobar();
};

X x1;
x1.foo();
"""

    tu = get_tu(source)
    cc = tu.codeComplete('t.cpp', 9, 4, unsaved_files=[('t.cpp', source)])
    ok_(isinstance(cc, CodeCompletionResults))

    results = cc.results
    ok_(len(results) > 0)

    # TODO need more tests.
