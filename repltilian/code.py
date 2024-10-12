"""Functions related to parsing Swift code."""
import re
from dataclasses import dataclass
from typing import Self, final


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


@dataclass
class FunctionCode:
    name: str
    code: str
    code_start_line: int
    code_end_line: int
    header: str
    header_start_line: int
    header_end_line: int
    body: str
    body_start_line: int
    body_end_line: int

    @property
    def num_lines(self) -> int:
        return self.code_end_line - self.code_start_line + 1


def make_body_return_var(function_body: str, name: str = "__return_value") -> str:
    lines = function_body.split("\n")
    last_line = lines[-1]
    if last_line.strip().startswith("return"):
        return function_body

    first_line = lines[0]
    match = re.match(r"^\s*", first_line)
    indent = match.group() if match else ""

    # allocate new variable
    new_line = f"{indent}let {name} = {first_line.strip()}"
    lines[0] = new_line
    lines.append(f"{indent}return {name}")
    return "\n".join(lines)


def _count_delta(text: str, start: str, end: str) -> int:
    """Count the difference between the number of occurrences of start and end."""
    return text.count(start) - text.count(end)


def find_function(function_name: str, source_code: str) -> FunctionCode:
    """Extract the code for a function from the given source code text.

    Returns:
        - full function content as a string
        - function body as a string
        - start index of the first body line (0-based)
        - end index of the last body line (0-based)
    """
    lines = source_code.split("\n")

    func_lines = []  # To collect the full function content
    brace_count = 0  # To track opening and closing braces
    inside_function = False  # Flag to indicate if we're inside the target function

    func_start_index = None  # Line where the function definition starts
    body_start_index = None  # Line where the function body starts
    body_end_index = None  # Line where the function body ends

    # Regular expression to match the function definition (including multiline)
    func_def_pattern = re.compile(r"\bfunc\b[\s\S]*?\b" + re.escape(function_name) + r"\b")
    lines_wo_comments = [line.split("//")[0] for line in lines]

    i = 0
    while i < len(lines):
        line = lines[i]
        line_wo_comments = lines_wo_comments[i]

        # If we're not yet inside the function
        if not inside_function:
            # Check if the function definition starts here
            # Collect lines until we find the opening brace '{'
            potential_def_lines = []
            def_start_index = i
            while i < len(lines):
                potential_def_lines.append(lines[i])
                joined_lines = "\n".join(potential_def_lines)
                if re.search(func_def_pattern, joined_lines):
                    if "{" in lines_wo_comments[i]:
                        # Found the opening brace
                        func_start_index = def_start_index
                        func_lines.extend(potential_def_lines)
                        brace_count += _count_delta(lines_wo_comments[i], "{", "}")
                        # Determine where the body starts
                        if lines_wo_comments[i].strip().endswith("{"):
                            body_start_index = i + 1
                        else:
                            body_start_index = i
                        inside_function = True
                        i += 1
                        break
                    else:
                        i += 1
                else:
                    # Not the function we're looking for
                    i += 1
                    break
            else:
                # End of file reached without finding function
                break
        else:
            # We're inside the function body
            func_lines.append(line)
            brace_count += _count_delta(line_wo_comments, "{", "}")
            if brace_count == 0:
                # Function body ends here
                body_end_index = i
                break
            i += 1

    if func_start_index is not None and body_start_index is not None and body_end_index is not None:
        full_function_content = "\n".join(func_lines)
        # The body is from body_start_index to body_end_index - 1
        function_body = "\n".join(lines[body_start_index:body_end_index])
        function_header = "\n".join(lines[func_start_index:body_start_index])
        return FunctionCode(
            name=function_name,
            # full function content
            code=full_function_content,
            code_start_line=func_start_index,
            code_end_line=i,
            # header
            header=function_header,
            header_start_line=func_start_index,
            header_end_line=body_start_index - 1,
            # body
            body=function_body,
            body_start_line=body_start_index,
            body_end_line=body_end_index - 1,
        )
    else:
        raise ValueError(
            f"Function '{function_name}' not found or improperly formatted, check for unmatched "
            f"{{}} or () or [] in the text or comments inside the function."
        )


@final
class CodeBlock:
    def __init__(self, code_lines: list[str], start_line: int, end_line: int):
        self.code_lines = code_lines
        self.start_line = start_line
        self.end_line = end_line

    @property
    def num_lines(self) -> int:
        return len(self.code_lines)

    @property
    def text(self) -> str:
        return "\n".join(self.code_lines)

    def is_comment_block(self) -> bool:
        """Check if each line in the block is a single line comment."""
        for line in self.code_lines:
            if not line.strip().startswith("//"):
                return False
        return True

    def is_function_call_block(self) -> bool:
        line = self.code_lines[0].strip()
        # check for "for (condition text) {" or "while (condition text) {"
        if re.search(r"\s*(for|while)\s*.*{\s*", line):
            return False
        if re.search(r"\s*\w+\s*\(", line):
            return True
        return False

    def is_if_else_block(self) -> bool:
        if not re.search(r"\s*if\s*[(]?", self.code_lines[0]):
            return False

        for line in self.code_lines:
            if re.search(r"\s*else\s*", line):
                print(f"WARNING! If else is not supported: {self.text}")
                return True
        return False

    def can_split(self) -> bool:
        conditions = [
            self.num_lines > 1,
            not self.is_comment_block(),
            not self.is_function_call_block(),
            not self.is_if_else_block(),
        ]
        return all(conditions)

    def split(self) -> list[Self]:
        if not self.can_split():
            raise ValueError("Cannot split this block.")

        inner_blocks = extract_code_blocks(self.code_lines[1:-1])
        # map local lines to global lines
        for block in inner_blocks:
            block.start_line += self.start_line + 1
            block.end_line += self.start_line + 1
        return inner_blocks


def extract_code_blocks(source_lines: list[str]) -> list[CodeBlock]:
    blocks = []
    current_block: list[str] = []
    start_line_num = 0
    grouping_levels = {"paren": 0, "bracket": 0, "brace": 0}

    for i in range(0, len(source_lines)):
        line = source_lines[i]
        if not current_block:
            # Start of a new block
            start_line_num = i
        current_block.append(line)

        # Remove comments
        line_no_comment = line.split("//")[0]
        line_no_strings = _remove_string_literals(line_no_comment)

        # Update grouping levels
        grouping_levels["paren"] += _count_delta(line_no_strings, "(", ")")
        grouping_levels["brace"] += _count_delta(line_no_strings, "{", "}")
        grouping_levels["bracket"] += _count_delta(line_no_strings, "[", "]")

        # Check if grouping levels are zero
        if (
            grouping_levels["paren"] == 0
            and grouping_levels["brace"] == 0
            and grouping_levels["bracket"] == 0
        ):
            # Statement is complete
            end_line_num = i
            blocks.append(
                CodeBlock(
                    code_lines=current_block,
                    start_line=start_line_num,
                    end_line=end_line_num,
                )
            )
            current_block = []
            grouping_levels = {"paren": 0, "bracket": 0, "brace": 0}

    if current_block:
        # Append last block
        end_line_num = len(source_lines) - 1
        blocks.append(
            CodeBlock(
                code_lines=current_block,
                start_line=start_line_num,
                end_line=end_line_num,
            )
        )
    # remove empty blocks
    blocks = [block for block in blocks if block.text.strip() != ""]
    return blocks


def _remove_string_literals(text: str) -> str:
    """Remove string literals to avoid counting braces inside strings"""
    result = ""
    in_string = False
    escape_next = False
    for c in text:
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not in_string:
            in_string = True
            continue
        elif c == '"' and in_string:
            in_string = False
            continue
        if not in_string:
            result += c
    return result
