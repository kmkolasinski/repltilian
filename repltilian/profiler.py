"""
Functions related to line profiler functionality.
"""
import re
from typing import Self


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
        indent + f'print("Function: {function_name} at line {func_start_index + 1}")',
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
    profiling_output.append(indent + '    let contents = lineContentDict[line] ?? ""')
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


def render_for_profile(self, profile_lines: list[str], line_contents: dict[int, str]):
    lines = self.code_lines
    if len(lines) == 0:
        return
    indent = re.match(r"\s*", lines[0]).group()
    line_number = self.code_start_line

    start_time_var = f"__start_time_{line_number}"
    end_time_var = f"__end_time_{line_number}"
    # Insert timing code
    profile_lines.append(
        indent + f"let {start_time_var} = DispatchTime.now().uptimeNanoseconds"
    )

    if len(lines) == 1:
        line_contents[line_number] = lines[0].replace('"', '\\"')
        profile_lines.append(lines[0])
    elif self.is_function_call_block() or self.is_if_else_block():
        for i, line in enumerate(lines):
            line_contents[line_number + i] = line.replace('"', '\\"')
            profile_lines.append(line)
    else:
        profile_lines.append(lines[0])
        line_contents[line_number] = lines[0].replace('"', '\\"')
        for inner in self.split():
            inner.render_for_profile(profile_lines, line_contents)
        profile_lines.append(lines[-1])
        line_contents[self.code_end_line] = lines[-1].replace('"', '\\"')

    profile_lines.append(
        indent + f"let {end_time_var} = DispatchTime.now().uptimeNanoseconds"
    )
    profile_lines.append(
        indent
        + f"__line_times[{line_number}] = (__line_times[{line_number}] ?? 0) + ({end_time_var} - {start_time_var})"
    )
    profile_lines.append(
        indent + f"__line_hits[{line_number}] = (__line_hits[{line_number}] ?? 0) + 1"
    )
