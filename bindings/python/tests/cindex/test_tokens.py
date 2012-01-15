from clang.cindex import Index, File, SourceLocation, CursorKind

def test_token_to_cursor():
    index = Index.create()
    tu = index.parse('t.c', unsaved_files=[('t.c', 'int i = 5;')])
    assert tu is not None

    file = File.from_name(tu, 't.c')
    start = SourceLocation.from_position(tu, file, 1, 1)
    end = SourceLocation.from_position(tu, file, 1, 10)

    tokens = list(tu.get_tokens(start_location=start, end_location=end))

    assert len(tokens) == 5
    assert tokens[1].spelling == 'i'

    cursor = tokens[1].cursor
    assert cursor.kind == CursorKind.VAR_DECL
    assert tokens[1].cursor == tokens[2].cursor
