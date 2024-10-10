import json
import os
import re
import tempfile
from typing import Any, Self

import pexpect

INIT_COMMANDS = """
import Foundation

// Function to deserialize an object from a JSON file at the given path
func _deserializeObject<T: Decodable>(_ path: String) throws -> T {
    let url = URL(fileURLWithPath: path)
    let data = try Data(contentsOf: url)
    let decoder = JSONDecoder()
    let object = try decoder.decode(T.self, from: data)
    return object
}

// Function to serialize an object and save it as a JSON file at the given path
func _serializeObject<T: Encodable>(_ object: T, to path: String) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys] // Optional formatting
    let data = try encoder.encode(object)
    let url = URL(fileURLWithPath: path)
    try data.write(to: url)
}

"""
END_OF_INCLUDE = "// -- END OF AUTO REPL INCLUDE --"


class Variable:
    def __init__(self, name: str, dtype: str, value: str):
        self.name = name
        self.dtype = dtype
        self.value = value
        self._repl: SwiftREPL | None = None

    def str(self) -> str:
        return extract_string_value(self.value)

    def json(self, verbose: bool = False) -> dict[str, Any]:
        if self._repl is None:
            raise ValueError("Variable is not associated with a REPL instance.")

        with tempfile.NamedTemporaryFile() as tmpfile:
            path = f"{tmpfile.name}.json"
            self._repl.run(
                f'_serializeObject({self.name}, to: "{path}")',
                verbose=verbose,
                reload=False,
            )
            with open(path, "r") as file:
                data = json.load(file)
            return data

    def __repr__(self):
        return f"{self.name}[{self.dtype}] at {id(self)}"


class VariablesRegister(dict):
    def __init__(self, repl_ref: "SwiftREPL"):
        super().__init__()
        self._repl_ref = repl_ref

    def __getitem__(self, item: str):
        variable = super().__getitem__(item)
        variable._repl = self._repl_ref
        return variable

    def create(self, name: str, dtype: str, value: Any, verbose: bool = False):
        with tempfile.NamedTemporaryFile() as tmpfile:
            path = f"{tmpfile.name}.json"
            with open(path, "w") as fp:
                json.dump(value, fp)

            self._repl_ref.run(
                f'\nvar {name}: {dtype} = try _deserializeObject("{path}")\n',
                verbose=verbose,
                reload=False,
            )
            self[name] = Variable(name, dtype, value)


class SwiftREPL:
    def __init__(self, cwd: str | None = None):
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        env["TERM"] = "dumb"

        command = "swift run --repl"
        if cwd is None:
            command = "swift repl"
        self._process = pexpect.spawn(
            command, encoding="utf-8", timeout=1, env=env, cwd=cwd
        )
        self.vars = VariablesRegister(self)
        self._reload_paths: set[str] = set()
        self._output: str | None = None
        self.run(INIT_COMMANDS, verbose=False)
        self.run("""print("REPL is running !")""")

    def add_reload_file(self, path: str):
        if path not in self._reload_paths:
            self._reload_paths.add(path)

    def run(
        self,
        code: str,
        timeout: float = 0.01,
        verbose: bool = True,
        reload: bool = False,
        name_mapping: dict[str, str] | None = None,
        output_stop_pattern: str = None,
    ):
        include = None
        if self._reload_paths and reload:
            include = list(self._reload_paths)
        if include:
            include_content = []
            for file_path in include:
                include_code = get_file_content(file_path)
                include_content.append(include_code)
            include_text = "\n".join(include_content)
            if name_mapping is not None:
                for old_name, new_name in name_mapping.items():
                    include_text = include_text.replace(old_name, new_name)
            code = include_text + "\n" + END_OF_INCLUDE + "\n" + code

        self._process.sendline(code)
        incoming = []
        while True:
            try:
                buffer = self._process.read_nonblocking(self._process.maxread, timeout)
                incoming.append(buffer)
            except pexpect.exceptions.TIMEOUT:
                # a regex which matches the waiting prompt e.g. "1>" or "102>" but
                # there must not be any text after the prompt
                prompt_pattern = re.compile(r"(\d+>\s+$)")
                buffer_end = "".join(incoming[-10:])
                buffer_end_clean = clean(buffer_end)
                has_prompt = prompt_pattern.search(buffer_end_clean)
                if has_prompt is None:
                    continue
                break

        incoming_str = "".join(incoming)
        output = clean(incoming_str)
        if has_error(output):
            print(output)
            raise ValueError("Error in Swift code!")
        self._output = output
        if verbose:
            _, output = split_output_by_end_of_include(output)
            if output_stop_pattern is not None:
                output_lines = output.split("\n")
                stop_k = 0
                for i, line in enumerate(output_lines):
                    stop_k = i
                    if output_stop_pattern in line:
                        break
                output = "\n".join(output_lines[:stop_k])
            print(output)

        variable_updates = find_variables(output)
        self.vars.update(variable_updates)
        return output

    def close(self):
        # Exit the REPL
        self._process.sendline(":quit")
        self._process.terminate()
        self._process.close()

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


def get_files_content(paths: list[str]) -> str:
    include_content = []
    for file_path in paths:
        include_code = get_file_content(file_path)
        include_content.append(include_code)
    include_text = "\n".join(include_content)
    return include_text


def split_code_line(line: str) -> list[str]:
    return [line]


def split_code_lines(lines: list[str]) -> list[str]:
    final_lines = []
    for line in lines:
        final_lines.extend(split_code_line(line))
    return final_lines


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


def has_error(text: str) -> bool:
    lines = text.split("\n")
    # alternative error pattern e.g. $E11:
    error_pattern1 = re.compile(r"(\$E\d+):")
    # alternative error pattern line starts with "error:"
    error_pattern2 = re.compile(r"^error:")
    error_patterns = [
        error_pattern1,
        error_pattern2,
    ]
    for line in lines:
        for pattern in error_patterns:
            match = pattern.search(line)
            if match:
                return True

    return False


def get_file_content(path: str) -> str:
    with open(path, "r") as file:
        file_content = file.read()
    return file_content


def find_end_of_include_line(text: str) -> int:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if END_OF_INCLUDE in line:
            return i
    return -1


def split_output_by_end_of_include(text: str) -> tuple[str, str]:
    end_of_include_line = find_end_of_include_line(text)
    if end_of_include_line == -1:
        return "", text
    lines = text.split("\n")
    include_part = "\n".join(lines[:end_of_include_line])
    code_part = "\n".join(lines[end_of_include_line + 1 :])
    return include_part, code_part


def clean(text: str) -> str:
    import re

    # Initialize the screen buffer as a list of lines
    screen_lines = [""]
    line = 0  # Current line index
    col = 0  # Current column index
    i = 0  # Current index in the input text
    n = len(text)

    def read_escape_sequence(s, i):
        """
        Reads an ANSI escape sequence starting from index i in string s.
        Returns the escape sequence and the index after the sequence.
        """
        if s[i : i + 2] != "\x1b[":
            return None, i + 1  # Not an escape sequence we recognize
        j = i + 2
        while j < len(s):
            if "A" <= s[j] <= "Z" or "a" <= s[j] <= "z":
                # End of the escape sequence
                j += 1  # Include the command character
                return s[i:j], j
            else:
                j += 1
        # If we reach here, didn't find the end of escape sequence
        return s[i:j], j

    while i < n:
        c = text[i]
        if c == "\x1b":
            # Process escape sequence
            esc_seq, next_i = read_escape_sequence(text, i)
            if esc_seq:
                # Process the escape sequence
                i = next_i
                # Extract the command and parameters
                cmd_match = re.match(r"\x1b\[([0-9;]*)([A-Za-z])", esc_seq)
                if cmd_match:
                    params = cmd_match.group(1)
                    cmd = cmd_match.group(2)
                    # Process the command
                    if cmd == "G":
                        # Cursor horizontal absolute
                        # Move cursor to column N (default 1)
                        N = int(params) if params else 1
                        col = max(N - 1, 0)  # Adjust for zero-based index
                    elif cmd == "J":
                        # Erase display from cursor to end of screen
                        # Clear from current line and position to end
                        screen_lines = screen_lines[: line + 1]
                        # Truncate the current line from cursor position
                        screen_lines[line] = screen_lines[line][:col]
                    else:
                        # Other commands can be implemented as needed
                        pass
                continue
            else:
                # Not a recognized escape sequence
                i += 1
                continue
        elif c == "\r":
            # Carriage return
            col = 0
            i += 1
        elif c == "\n":
            # Line feed
            line += 1
            if line >= len(screen_lines):
                screen_lines.append("")
            i += 1
        else:
            # Printable character
            # Ensure the current line exists
            while len(screen_lines) <= line:
                screen_lines.append("")
            current_line = screen_lines[line]
            # Extend the line with spaces if necessary
            if col > len(current_line):
                current_line += " " * (col - len(current_line))
            # Insert or replace the character at the current position
            if col < len(current_line):
                current_line = current_line[:col] + c + current_line[col + 1 :]
            else:
                current_line += c
            # Update the screen buffer
            screen_lines[line] = current_line
            # Move cursor forward
            col += 1
            i += 1

    # After processing, join the lines
    result = "\n".join(screen_lines)
    return result


def find_variables(text) -> dict[str, Variable]:
    register = {}
    lines = text.splitlines()

    in_value = False
    brace_counter = 0
    current_var_name = ""
    current_var_type = ""
    current_var_value = ""

    for line in lines:
        if not in_value:
            # Match variable declarations
            m = re.match(r"^(\w+):\s*(\S+)\s*=\s*(.*)$", line)
            if m:
                var_name = m.group(1)
                var_type = m.group(2)
                var_value = m.group(3).strip()
                # Check for opening and closing braces in the initial value
                open_braces = var_value.count("{")
                close_braces = var_value.count("}")
                brace_counter = open_braces - close_braces
                if brace_counter > 0:
                    # Value spans multiple lines
                    in_value = True
                    current_var_value = var_value + "\n"  # Include the newline
                    current_var_name = var_name
                    current_var_type = var_type
                else:
                    # Value is on a single line
                    register[var_name] = (var_type, var_value.strip())
            else:
                # Not a variable declaration line
                continue
        else:
            # Collecting multi-line variable value
            current_var_value += line + "\n"
            brace_counter += line.count("{") - line.count("}")
            if brace_counter <= 0:
                # Finished collecting the variable value
                register[current_var_name] = (
                    current_var_type,
                    current_var_value.strip(),
                )
                # Reset for the next variable
                in_value = False
                current_var_name = ""
                current_var_type = ""
                current_var_value = ""
                brace_counter = 0
    register = {k: Variable(k, v[0], v[1]) for k, v in register.items()}
    return register


def parse_output_variable(text):
    """
    Parses variables from the given text, extracting their values
    and converting them to Python objects depending on their types.

    Args:
        text (str): The input string containing variable assignments.

    Returns:
        dict: A dictionary mapping variable names to their parsed values.
    """
    variables = {}

    # Regular expression pattern to match variable assignments
    # of the form '$R7: Type = Value'
    var_pattern = re.compile(r"(\$R\d+):\s*(\w+)\s*=\s*")

    # Find all matches in the text
    matches = list(var_pattern.finditer(text))

    for idx, match in enumerate(matches):
        var_name = match.group(1)  # e.g., $R7
        var_type = match.group(2)  # e.g., String

        # Determine the start and end positions of the value
        value_start = match.end()
        if idx + 1 < len(matches):
            # Value ends at the start of the next variable assignment
            value_end = matches[idx + 1].start()
        else:
            # Value ends at the end of the text
            value_end = len(text)

        # Extract the raw value string
        raw_value = text[value_start:value_end].strip()

        # Parse the value depending on its type
        if var_type == "String":
            # Expect the value to be enclosed in double quotes
            value = extract_string_value(raw_value)
            if value is not None:
                # Attempt to parse the string as JSON
                parsed_value = parse_json_string(value)
                if parsed_value is not None:
                    variables[var_name] = parsed_value  # Store the JSON object
                else:
                    variables[var_name] = value  # Store the raw string
            else:
                print(f"Error: Unmatched quotes for variable {var_name}")
        else:
            # For other types, you can add parsing logic as needed
            variables[var_name] = raw_value

    assert len(variables) == 1
    return list(variables.values())[0]


def extract_string_value(text: str) -> str:
    """
    Extracts a string value enclosed in double quotes, handling escaped quotes.

    Args:
        text (str): The raw value string starting with a quote.

    Returns:
        str or None: The extracted string without the surrounding quotes,
                     or None if no closing quote is found.
    """
    if not text.startswith('"'):
        raise ValueError(
            f"String value must start with a double quote, " f"got: {text=}"
        )
    i = 1  # Skip the opening quote
    escaped = False
    value_chars = []
    while i < len(text):
        c = text[i]
        if escaped:
            if c in ('"', "\\", "/"):
                value_chars.append(c)
            elif c == "n":
                value_chars.append("\n")
            elif c == "r":
                value_chars.append("\r")
            elif c == "t":
                value_chars.append("\t")
            else:
                # Handle other escape sequences as needed
                value_chars.append(c)
            escaped = False
        elif c == "\\":
            escaped = True
        elif c == '"':
            # Closing quote found
            return "".join(value_chars)
        else:
            value_chars.append(c)
        i += 1
    # No closing quote found
    raise ValueError(f"Unmatched quotes in string value, got: {text=}")


def parse_json_string(s: str) -> dict:
    """
    Attempts to parse a string as JSON.

    Args:
        s (str): The string to parse.

    Returns:
        object or None: The parsed JSON object, or None if parsing fails.
    """
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        raise ValueError(f"Failed to parse JSON string: {s}")
