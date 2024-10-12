"""
Functions related to line profiler functionality.
"""
import re
from typing import Self


def get_function_source_code(self, name: str, filepath: str):
    """
    Returns:
        - full function content as a string
        - function body as a string
        - start index of the first body line (0-based)
        - end index of the last body line (0-based)
    """

    # Read the source code from the files
    source_code = get_files_content([filepath])
    lines = source_code.split("\n")

    func_lines = []  # To collect the full function content
    brace_count = 0  # To track opening and closing braces
    inside_function = False  # Flag to indicate if we're inside the target function

    func_start_index = None  # Line where the function definition starts
    body_start_index = None  # Line where the function body starts
    body_end_index = None  # Line where the function body ends

    # Regular expression to match the function definition (including multiline)
    func_def_pattern = re.compile(r"\bfunc\b[\s\S]*?\b" + re.escape(name) + r"\b")

    i = 0
    while i < len(lines):
        line = lines[i]

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
                    if "{" in lines[i]:
                        # Found the opening brace
                        func_start_index = def_start_index
                        func_lines.extend(potential_def_lines)
                        brace_count += lines[i].count("{") - lines[i].count("}")
                        # Determine where the body starts
                        if lines[i].strip().endswith("{"):
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
            brace_count += line.count("{") - line.count("}")
            if brace_count == 0:
                # Function body ends here
                body_end_index = i
                break
            i += 1

    if (
        func_start_index is not None
        and body_start_index is not None
        and body_end_index is not None
    ):
        full_function_content = "\n".join(func_lines)
        # The body is from body_start_index to body_end_index - 1
        function_body = "\n".join(lines[body_start_index:body_end_index])
        function_body = make_function_body_end_with_return(function_body)
        function_header = "\n".join(lines[func_start_index:body_start_index])
        return (
            full_function_content,
            function_header,
            function_body,
            body_start_index,
            body_end_index - 1,
        )
    else:
        raise ValueError(f"Function '{name}' not found or improperly formatted.")

def get_function_for_line_profiler(self, function_name: str, filepath: str) -> str:

    (
        _,
        header_str,
        body_str,
        func_start_index,
        func_end_index,
    ) = self.get_function_source_code(function_name, filepath)
    body_lines = body_str.split("\n")
    body_lines = [line for line in body_lines if line.strip()]
    return_line, body_lines = body_lines[-1], body_lines[:-1]
    instrumented_lines = []
    line_contents = {}
    # Initialize the profiling variables
    indent = re.match(r"\s*", body_lines[0]).group()
    num_lines = len(body_lines)
    instrumented_lines.append(indent + "var __line_times = [Int: UInt64]()")
    instrumented_lines.append(indent + "var __line_hits = [Int: Int]()")
    instrumented_lines.append(
        indent + f"(0..<{num_lines}).map {{ i in __line_times[i] = 0}}"
    )
    instrumented_lines.append(
        indent + f"(0..<{num_lines}).map {{ i in __line_hits[i] = 0}}"
    )

    instrumented_lines.append(
        indent + f"let __start_time_func = DispatchTime.now().uptimeNanoseconds"
    )

    blocks = extract_code_blocks(body_lines)
    for block in blocks:
        block.render_for_profile(instrumented_lines, line_contents)

    instrumented_lines.append(
        indent + f"let __end_time_func = DispatchTime.now().uptimeNanoseconds"
    )

    # Insert code to print profiling statistics before the closing brace
    profiling_output = [
        indent + 'print("Timer unit: 1 ns")',
        indent + "let __total_time = __end_time_func - __start_time_func",
        indent
        + f'print(String(format: "\\nTotal time: %.3f s", Double(__total_time)/1_000_000_000))',
        indent
        + f'print("Function: {function_name} at line {func_start_index + 1}")',
        indent + 'print("")',
        indent
        + 'print("Line #      Hits         Time   Per Hit   % Time  Line Contents")',
        indent
        + 'print("===============================================================")',
        indent + "for line in (__line_times.keys.sorted()) {",
        indent + "    let hits = __line_hits[line] ?? 0",
        indent + "    let time = __line_times[line] ?? 0",
        indent + "    let per_hit = hits > 0 ? Double(time) / Double(hits) : 0",
        indent
        + "    let percent_time = __total_time > 0 ? (Double(time) / Double(__total_time)) * 100 : 0",
        indent + "    let lineContentDict: [Int: String] = [",
    ]

    # Add line contents to the dictionary
    for ln in sorted(line_contents.keys()):
        content = line_contents[ln]
        profiling_output.append(indent + f'        {ln}: "{content}",')
    profiling_output.append(indent + "    ]")
    profiling_output.append(
        indent + '    let contents = lineContentDict[line] ?? ""'
    )
    profiling_output.append(
        indent
        + '    print(String(format: "%6d %10d %12.6f %9.6f %8.1f%%  %@", line, hits, Double(time)/1_000_000_000, per_hit/1_000_000_000, percent_time, contents))'
    )
    profiling_output.append(indent + "}")
    # Find the closing brace line and insert profiling output before it
    instrumented_lines = instrumented_lines + profiling_output + [return_line]
    header_intent = re.match(r"\s*", header_str).group()
    instrumented_lines = [header_str] + instrumented_lines + [header_intent + "}"]

    return "\n".join(instrumented_lines)


def make_function_body_end_with_return(body: str) -> str:
    lines = body.split("\n")
    last_line = lines[-1]
    if last_line.strip().startswith("return"):
        return body

    first_line = lines[0]
    indent = re.match(r"^\s*", first_line).group()
    # allocate new variable
    new_line = f"{indent}let __return_value = {first_line.strip()}"
    lines[0] = new_line
    lines.append(f"{indent}return __return_value")
    return "\n".join(lines)


class CodeBlock:
    def __init__(self, code: list[str], start_line: int, end_line: int):
        self.code = code
        self.start_line = start_line
        self.end_line = end_line

    def is_function_call(self) -> bool:
        line = self.code[0].strip()
        # check for "for (condition text) {" or "while (condition text) {"
        if re.search(r"\s*(for|while)\s*.*{\s*", line):
            return False
        if re.search(r"\s*\w+\s*\(", line):
            return True
        return False

    @property
    def text(self):
        return "\n".join(self.code)

    def is_if_else_block(self) -> bool:

        if not re.search(r"\s*if\s*[(]?", self.code[0]):
            return False

        for line in self.code:

            if re.search(r"\s*else\s*", line):
                print(f"WARNING! If else is not supported: {self.text}")
                return True
        return False

    def split(self) -> list[Self]:
        if self.is_function_call():
            raise ValueError("Cannot split a function call block.")
        if self.is_if_else_block():
            raise ValueError("Cannot split an if-else block.")
        inner_blocks = extract_code_blocks(self.code[1:-1])
        # map local lines to global lines
        for block in inner_blocks:
            block.start_line += self.start_line + 1
            block.end_line += self.start_line + 1

        return inner_blocks

    def render_for_profile(
        self, profile_lines: list[str], line_contents: dict[int, str]
    ):
        lines = self.code
        if len(lines) == 0:
            return
        indent = re.match(r"\s*", lines[0]).group()
        line_number = self.start_line

        start_time_var = f"__start_time_{line_number}"
        end_time_var = f"__end_time_{line_number}"
        # Insert timing code
        profile_lines.append(
            indent + f"let {start_time_var} = DispatchTime.now().uptimeNanoseconds"
        )

        if len(lines) == 1:
            line_contents[line_number] = lines[0].replace('"', '\\"')
            profile_lines.append(lines[0])
        elif self.is_function_call() or self.is_if_else_block():
            for i, line in enumerate(lines):
                line_contents[line_number + i] = line.replace('"', '\\"')
                profile_lines.append(line)
        else:
            profile_lines.append(lines[0])
            line_contents[line_number] = lines[0].replace('"', '\\"')
            for inner in self.split():
                inner.render_for_profile(profile_lines, line_contents)
            profile_lines.append(lines[-1])
            line_contents[self.end_line] = lines[-1].replace('"', '\\"')

        profile_lines.append(
            indent + f"let {end_time_var} = DispatchTime.now().uptimeNanoseconds"
        )
        profile_lines.append(
            indent
            + f"__line_times[{line_number}] = (__line_times[{line_number}] ?? 0) + ({end_time_var} - {start_time_var})"
        )
        profile_lines.append(
            indent
            + f"__line_hits[{line_number}] = (__line_hits[{line_number}] ?? 0) + 1"
        )


def extract_code_blocks(source_lines: list[str]) -> list[CodeBlock]:
    blocks = []
    current_block = []
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

        # Remove string literals to avoid counting braces inside strings
        def remove_string_literals(s):
            result = ""
            in_string = False
            escape_next = False
            for c in s:
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

        line_no_strings = remove_string_literals(line_no_comment)

        # Update grouping levels
        grouping_levels["paren"] += line_no_strings.count("(") - line_no_strings.count(
            ")"
        )
        grouping_levels["brace"] += line_no_strings.count("{") - line_no_strings.count(
            "}"
        )
        grouping_levels["bracket"] += line_no_strings.count(
            "["
        ) - line_no_strings.count("]")

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
                    code=current_block, start_line=start_line_num, end_line=end_line_num
                )
            )
            current_block = []
            grouping_levels = {"paren": 0, "bracket": 0, "brace": 0}

    if current_block:
        # Append last block
        end_line_num = end_line - 1
        blocks.append(
            CodeBlock(
                code=current_block, start_line=start_line_num, end_line=end_line_num
            )
        )

    return blocks
