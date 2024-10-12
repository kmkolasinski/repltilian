"""Functions related to parsing Swift REPL output."""
import re

from repltilian import constants


def clean(text: str) -> str:
    # Initialize the screen buffer as a list of lines
    screen_lines = [""]
    line = 0  # Current line index
    col = 0  # Current column index
    i = 0  # Current index in the input text
    n = len(text)

    def read_escape_sequence(s, i):
        """Reads an ANSI escape sequence starting from index i in string s.
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


def find_end_of_include_line(text: str) -> int:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if constants.END_OF_INCLUDE in line:
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


def find_variables(text) -> dict[str, tuple[str, str]]:
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
                var_type: str = m.group(2)
                var_value: str = m.group(3).strip()
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
                    register[var_name] = (var_type, var_value)
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

    return register


def extract_string_value(text: str) -> str:
    """Extracts a string value enclosed in double quotes, handling escaped quotes.

    Args:
        text (str): The raw value string starting with a quote.

    Returns:
        str or None: The extracted string without the surrounding quotes,
                     or None if no closing quote is found.
    """
    if not text.startswith('"'):
        raise ValueError(f"String value must start with a double quote, " f"got: {text=}")
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
