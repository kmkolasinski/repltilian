"""Functions related to parsing Swift code."""


def get_files_content(paths: list[str]) -> str:
    include_content = []
    for file_path in paths:
        include_code = get_file_content(file_path)
        include_content.append(include_code)
    include_text = "\n".join(include_content)
    return include_text


def get_file_content(path: str) -> str:
    with open(path) as file:
        file_content = file.read()
    return file_content
