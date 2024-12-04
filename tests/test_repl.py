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


def test__get_variable__not_in_register(repl: SwiftREPL) -> None:
    repl.run("let x = 5")
    assert repl.vars["x"].get() == 5

    del repl.vars["x"]
    assert repl.vars["x"].get() == 5


def test__run_async_function__should_fail_on_await(repl: SwiftREPL) -> None:
    repl.run(
        """
    func sum(_ a: Int, _ b: Int) async -> Int {
        return a + b
    }
    """
    )
    with pytest.raises(SwiftREPLException):
        repl.run("let result = await sum(5, 7)")


def test__run_async_function(repl: SwiftREPL) -> None:
    repl.run(
        """
    func sum(_ a: Int, _ b: Int) async -> Int {
        return a + b
    }
    """
    )
    repl.run("let result = try runSync {await sum(5, 7)}")
    assert repl.vars["result"].get() == 12
