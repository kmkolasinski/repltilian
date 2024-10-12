from pathlib import Path

import pytest

THIS_FILE_DIR = Path(__file__).parent
RESOURCES_DIR = THIS_FILE_DIR / "resources"


@pytest.fixture()
def sample_code() -> str:
    with open(RESOURCES_DIR / "demo.swift") as f:
        return f.read()
