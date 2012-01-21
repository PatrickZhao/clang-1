from clang.cindex import CursorKind
from clang.cindex import Index
from clang.cindex import ResourceUsageKind
from clang.cindex import TokenKind
from clang.cindex import TypeKind

import os

CLANG_SOURCE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__),
    '..', '..', '..', '..'))

INDEX_H = os.path.join(CLANG_SOURCE_DIR, 'include', 'clang-c', 'Index.h')

def test_enumeration_completeness():
    """Ensure that all enumerations defined in libclang are defined in Python.

    This test iterates over the libclang headers and ensures that all the
    enumerations captured in the Python bindings have corresponding Python
    definitions. This test helps ensure that new enumerations in libclang
    are added to the Python binding and that the Python binding is always up
    to date."""

    assert os.path.exists(INDEX_H)

    index = Index.create()
    tu = index.parse(INDEX_H)
    assert tu

    cursor = tu.cursor
    assert cursor.kind == CursorKind.TRANSLATION_UNIT

    enums = {
        'CXCursorKind': CursorKind,
        'CXTUResourceUsageKind': ResourceUsageKind,
        'CXTokenKind': TokenKind,
        'CXTypeKind': TypeKind,
    }

    for child in cursor.get_children():
        if child.kind != CursorKind.ENUM_DECL:
            continue

        if child.spelling not in enums:
            continue

        value = -1
        binding = enums[child.spelling]

        for child2 in child.get_children():
            value += 1
            tokens = list(child2.get_tokens())

            literal = None
            for token in tokens:
                if token.kind == TokenKind.LITERAL:
                    literal = token
                    break

            # Some enumerations assign to other enumeration values, not
            # literals. We ignore these.
            if literal is None:
                if len(tokens) >= 4 and tokens[1].spelling == '=':
                    continue
            else:
                value = int(literal.spelling)

            converter = getattr(binding, 'from_value')
            result = converter(value)

            assert isinstance(result, binding)
