import os
import re
import json
from copy import copy
from typing import Any

import pexpect

INIT_COMMANDS = """
import Foundation

func _toJSONString<T: Encodable>(_ value: T) throws -> String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
	let data = try encoder.encode(value)
	return String(data: data, encoding: .utf8)!
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

    def json(self, verbose: bool =False) -> dict[str, Any]:
        output = self._repl.run(
            f"_toJSONString({self.name})",
            verbose=verbose,
            reload=False,
        )
        return parse_output_variable(output)

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

    def __setitem__(self, key: str, value: dict | tuple[str, dict]):
        if key in self and isinstance(value, dict):
            variable: Variable = self[key]
            data_str = json.dumps(value)
            dtype = variable.dtype
            self._repl_ref.run(
                f"\nvar {key} = JSONDecoder().decode({dtype}.self, "
                f'from: #"{data_str}"#.data(using: .utf8)!)\n',
                verbose=False,
                reload=False,
            )
        else:
            if not isinstance(value, tuple):
                raise ValueError("Value must be a tuple (type, value dict)")
            dtype, data = value
            if not isinstance(data, dict):
                raise ValueError("Value must be a dictionary")
            data_str = json.dumps(data)
            self._repl_ref.run(
                f"\nvar {key} = JSONDecoder().decode({dtype}.self, "
                f'from: #"{data_str}"#.data(using: .utf8)!)\n',
                verbose=False,
                reload=False,
            )


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
        self._reload_paths = set()
        self._output = None
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
            code = include_text + "\n" + END_OF_INCLUDE + "\n" + code

        self._process.sendline(code)
        incoming = []
        while True:
            try:
                buffer = self._process.read_nonblocking(self._process.maxread, timeout)
                incoming.append(buffer)
            except pexpect.exceptions.TIMEOUT:
                # a regex which matches the waiting prompt e.g. "1>" or "102>" but there must
                # not be any text after the prompt
                prompt_pattern = re.compile(r"(\d+>\s+$)")
                buffer_end = "".join(incoming[-10:])
                buffer_end_clean = clean(buffer_end)
                has_prompt = prompt_pattern.search(buffer_end_clean)
                if has_prompt is None:
                    continue
                break

        incoming = "".join(incoming)
        output = clean(incoming)
        if has_error(output):
            print(output)
            raise ValueError("Error in Swift code!")
        self._output = output
        if verbose:
            _, output = split_output_by_end_of_include(output)
            print(output)

        variable_updates = find_variables(output)
        self.vars.update(variable_updates)
        return output

    def close(self):
        # Exit the REPL
        self._process.sendline(":quit")
        self._process.terminate()
        self._process.close()


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

    # Regular expression pattern to match variable assignments of the form '$R7: Type = Value'
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


def extract_string_value(s):
    """
    Extracts a string value enclosed in double quotes, handling escaped quotes.

    Args:
        s (str): The raw value string starting with a quote.

    Returns:
        str or None: The extracted string without the surrounding quotes,
                     or None if no closing quote is found.
    """
    if not s.startswith('"'):
        raise ValueError(f"String value must start with a double quote, got: {s=}")
    i = 1  # Skip the opening quote
    escaped = False
    value_chars = []
    while i < len(s):
        c = s[i]
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
    raise ValueError(f"Unmatched quotes in string value, got: {s=}")


def parse_json_string(s):
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
        return None
