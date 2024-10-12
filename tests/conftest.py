from pathlib import Path

import pytest

import repltilian

THIS_FILE_DIR = Path(__file__).parent
RESOURCES_DIR = THIS_FILE_DIR / "resources"


@pytest.fixture()
def sample_filepath() -> str:
    return str(RESOURCES_DIR / "demo.swift")


@pytest.fixture()
def sample_code() -> str:
    with open(RESOURCES_DIR / "demo.swift") as f:
        return f.read()


@pytest.fixture()
def repl() -> repltilian.SwiftREPL:
    return repltilian.SwiftREPL()
