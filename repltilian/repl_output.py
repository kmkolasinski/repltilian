"""Functions related to parsing Swift REPL output."""
import re

from repltilian import constants


def clean(text: str) -> str:
    """Cleans the raw output from a Swift REPL prompt output."""
    # Initialize the screen buffer as a list of lines
    screen_lines = [""]
    line = 0  # Current line index
    col = 0  # Current column index
    i = 0  # Current index in the input text
    n = len(text)

    def read_escape_sequence(s: str, i_: int) -> tuple[str | None, int]:
        """Reads an ANSI escape sequence starting from index i in string s.

        Returns the escape sequence and the index after the sequence.
        """
        if s[i_ : i_ + 2] != "\x1b[":
            return None, i_ + 1  # Not an escape sequence we recognize
        j = i_ + 2
        while j < len(s):
            if "A" <= s[j] <= "Z" or "a" <= s[j] <= "z":
                # End of the escape sequence
                j += 1  # Include the command character
                return s[i_:j], j
            else:
                j += 1
        # If we reach here, didn't find the end of escape sequence
        return s[i_:j], j

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
    return result.strip()


def search_for_error(cleaned_output: str) -> str | None:
    """Check if the text contains an error message: "error:" or "$E{number}:"."""
    error_pattern = re.compile(r"(\$E\d+):|^error:")
    for line in cleaned_output.split("\n"):
        if error_pattern.search(line):
            return line
    return None


def _find_end_of_include_line(cleaned_output_lines: list[str]) -> int:
    for i, line in enumerate(cleaned_output_lines):
        if constants.END_OF_INCLUDE in line:
            return i
    return -1


def _split_output_by_end_of_include(cleaned_output: str) -> tuple[str, str]:
    cleaned_output_lines = cleaned_output.split("\n")
    end_of_include_line = _find_end_of_include_line(cleaned_output_lines)
    if end_of_include_line == -1:
        return "", cleaned_output
    include_part = "\n".join(cleaned_output_lines[:end_of_include_line])
    code_part = "\n".join(cleaned_output_lines[end_of_include_line + 1 :])
    return include_part, code_part


def strip_prompt_input_lines(cleaned_output: str) -> str:
    r"""Searches for lines which start from \d+[>.] and removes them."""
    lines = cleaned_output.split("\n")
    stop = False
    i = 0
    for i, line in enumerate(lines):
        if re.match(r"^\d+[>.]", line.strip()):
            stop = True
        elif stop:
            break
    return "\n".join(lines[i:])


def print_output(
    cleaned_output: str,
    output_stop_pattern: str | None = None,
    output_hide_inputs: bool = False,
) -> None:
    """Print the cleaned output from REPL. Optionally limit the output by a stop pattern.

    Args:
        cleaned_output: swift REPL cleaned output
        output_stop_pattern: pattern to stop the output
        output_hide_inputs: hide input prompt lines from print
    """
    _, output = _split_output_by_end_of_include(cleaned_output)
    if output_hide_inputs:
        output = strip_prompt_input_lines(output)
    if output_stop_pattern is not None:
        search_pattern = re.compile(output_stop_pattern)
        output_lines = output.split("\n")
        stop_k = 0
        for i, line in enumerate(output_lines):
            stop_k = i
            if search_pattern.search(line):
                break
        output = "\n".join(output_lines[:stop_k])
    print(output)


def find_variables(cleaned_output: str) -> dict[str, tuple[str, str]]:
    """Extract variable declarations from the cleaned REPL output. This function searches for
    lines with the following pattern: "var_name: var_type = var_value" and returns a dictionary
    with the variable name as key and a tuple with the variable type and value content as string.

    Note: that for very long outputs not all variables may be captured as the REPL output is
    truncated.

    Args:
        cleaned_output: cleaned output from the REPL
    """
    register = {}
    lines = cleaned_output.splitlines()
    variable_pattern = re.compile(r"^(\w+|\$R+\d):\s*(\S+)\s*=\s*(.*)$")

    in_value = False
    brace_counter = 0
    current_var_name = ""
    current_var_type = ""
    current_var_value = ""

    for line in lines:
        if not in_value:
            m = re.match(variable_pattern, line.strip())
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
                register[current_var_name] = (current_var_type, current_var_value)
                # Reset for the next variable
                in_value = False
                current_var_name = ""
                current_var_type = ""
                current_var_value = ""
                brace_counter = 0

    return register
