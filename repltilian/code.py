"""Functions related to parsing Swift code."""


def get_files_content(paths: list[str]) -> str:
    """Get the content of files at the given paths."""
    include_content = []
    for file_path in paths:
        include_code = get_file_content(file_path)
        include_content.append(include_code)
    return "\n".join(include_content)


def get_file_content(path: str) -> str:
    """Get the content of the file at the given path."""
    with open(path) as file:
        file_content = file.read()
    return file_content
