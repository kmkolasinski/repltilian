from repltilian import SwiftREPL


def test_add_reload_file(repl: SwiftREPL, sample_filepath: str) -> None:
    repl.add_reload_file(sample_filepath)
    assert True
