import pytest

from repltilian import SwiftREPL, SwiftREPLException


def test_add_reload_file(repl: SwiftREPL, sample_filepath: str) -> None:
    repl.add_reload_file(sample_filepath)
    assert repl._reload_paths == {sample_filepath}
    repl.add_reload_file(sample_filepath)
    assert repl._reload_paths == {sample_filepath}
    repl.clear_reload_files()
    assert repl._reload_paths == set()


def test__allocate_variable(repl: SwiftREPL) -> None:
    repl.run("let x = 5")
    assert repl.vars["x"].get() == 5

    repl.vars.set("x", "Int", 10)
    assert repl.vars["x"].get() == 10

    repl.vars.set("array", "Array<Int>", [1, 2, 3])
    assert repl.vars["array"].get() == [1, 2, 3]


def test__create_variable_from_included_file(repl: SwiftREPL, sample_filepath: str) -> None:
    with pytest.raises(SwiftREPLException):
        repl.run("var point = Point<Float>(x: 1, y: 2)")

    repl.add_reload_file(sample_filepath)
    with pytest.raises(SwiftREPLException):
        repl.run("var point = Point<Float>(x: 1, y: 2)")

    repl.run("var point = Point<Float>(x: 1, y: 2)", autoreload=True)

    point_data = repl.vars["point"].get()
    assert point_data == {"x": 1, "y": 2}
