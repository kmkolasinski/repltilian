import pytest

from repltilian import code


def test__find_function__simple_function(sample_code: str) -> None:
    function = code.find_function("translate", sample_code)

    assert function.name == "translate"
    assert function.body.strip() == "return Point(x: x + dx, y: y + dy)"
    assert function.header.strip() == "func translate(dx: T, dy: T) -> Point<T> {"
    assert function.body_start_line == function.body_end_line
    assert function.header_start_line == function.header_end_line
    assert function.body_start_line == function.header_end_line + 1
    assert function.num_lines == 3


def test_find_function__should_raise_error(sample_code: str) -> None:
    with pytest.raises(ValueError):
        code.find_function("trans", sample_code)


def test__find_function__multiline_function(sample_code: str) -> None:
    function = code.find_function("findKNearestNeighbors", sample_code)

    assert function.name == "findKNearestNeighbors"
    assert function.header.strip() == (
        "func findKNearestNeighbors<T: FloatingPoint>(query: ["
        "Point<T>], dataset: [Point<T>], k: Int = 5) -> [SearchResult<T>] {"
    )
    assert function.header_start_line == function.code_start_line
    assert function.header_start_line == function.header_end_line
    assert function.body_start_line == function.header_end_line + 1
    assert function.code_end_line == function.body_end_line + 1
    assert function.num_lines == 27


def test__extract_code_blocks__simple_function(sample_code: str) -> None:
    function = code.find_function("translate", sample_code)
    blocks = code.extract_code_blocks(function.body.split("\n"))

    assert len(blocks) == 1
    assert blocks[0].text.strip() == "return Point(x: x + dx, y: y + dy)"


def test__extract_code_blocks__multiline_function(sample_code: str) -> None:
    function = code.find_function("findKNearestNeighbors", sample_code)
    blocks = code.extract_code_blocks(function.body.split("\n"))

    assert len(blocks) == 3
    assert blocks[0].text.strip() == "var results: [SearchResult<T>] = []"
    assert blocks[1].code_lines[0].strip() == "for queryPoint in query {"
    assert blocks[2].code_lines[0].strip() == "return results"

    with pytest.raises(ValueError):
        blocks[0].split()


def test__extract_code_blocks__function_has_string_with_brackets(sample_code: str) -> None:
    function = code.find_function("removeBrackets", sample_code)
    blocks = code.extract_code_blocks(function.body.split("\n"))

    assert len(blocks) == 2
    assert blocks[0].text.strip() == 'let brackets = ["[", "]"]'
    assert blocks[1].text.strip() == "return text.filter { !brackets.contains(String($0)) }"


def test__make_body_return_var(sample_code: str) -> None:
    body = """return Point(x: x + dx, y: y + dy)"""
    new_body = code.make_body_return_var(body)
    assert body == new_body
    body = """Point(x: x + dx, y: y + dy)"""
    new_body = code.make_body_return_var(body, "val")
    assert new_body == "let val = Point(x: x + dx, y: y + dy)\nreturn val"
