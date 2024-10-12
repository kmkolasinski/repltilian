"""Functions related to line profiler functionality."""
import re

from repltilian import code


def get_function_for_line_profiler(function_name: str, source_code: str) -> str:
    function = code.find_function(function_name, source_code)
    body_lines = code.make_body_return_var(function.body).split("\n")
    body_lines = [line for line in body_lines if line.strip()]
    return_line, body_lines = body_lines[-1], body_lines[:-1]

    # Initialize the profiling variables
    indent_match = re.match(r"\s*", body_lines[0])
    indent = indent_match.group() if indent_match else ""
    num_lines = len(body_lines)

    line_contents: dict[int, str] = {}
    instrumented_lines: list[str] = [
        indent + "var __line_times = [Int: UInt64]()",
        indent + "var __line_hits = [Int: Int]()",
        indent + f"(0..<{num_lines}).map {{ i in __line_times[i] = 0}}",
        indent + f"(0..<{num_lines}).map {{ i in __line_hits[i] = 0}}",
        indent + "let __start_time_func = DispatchTime.now().uptimeNanoseconds",
    ]

    blocks = code.extract_code_blocks(body_lines)
    for block in blocks:
        render_for_profile(block, instrumented_lines, line_contents)

    instrumented_lines.append(indent + "let __end_time_func = DispatchTime.now().uptimeNanoseconds")

    # Insert code to print profiling statistics before the closing brace
    profiling_output = [
        indent + 'print("Timer unit: 1 ns")',
        indent + "let __total_time = __end_time_func - __start_time_func",
        indent + 'print(String(format: "\\nTotal time: %.3f s", Double('
        "__total_time)/1_000_000_000))",
        indent + f'print("Function: {function_name} at line {function.code_start_line + 1}")',
        indent + 'print("")',
        indent + 'print("Line #      Hits         Time   Per Hit   % Time  Line Contents")',
        indent + 'print("===============================================================")',
        indent + "for line in (__line_times.keys.sorted()) {",
        indent + "    let hits = __line_hits[line] ?? 0",
        indent + "    let time = __line_times[line] ?? 0",
        indent + "    let per_hit = hits > 0 ? Double(time) / Double(hits) : 0",
        indent + "    let percent_time = __total_time > 0 "
        "? (Double(time) / Double(__total_time)) * 100 : 0",
        indent + "    let lineContentDict: [Int: String] = [",
    ]

    # Add line contents to the dictionary
    for ln in sorted(line_contents.keys()):
        content = line_contents[ln]
        profiling_output.append(indent + f'        {ln}: "{content}",')
    profiling_output.append(indent + "    ]")
    profiling_output.append(indent + '    let contents = lineContentDict[line] ?? ""')
    profiling_output.append(
        indent + '    print(String(format: "%6d %10d %12.6f %9.6f %8.1f%%  %@", line, hits, '
        "Double(time)/1_000_000_000, per_hit/1_000_000_000, percent_time, contents))"
    )
    profiling_output.append(indent + "}")
    # Find the closing brace line and insert profiling output before it
    instrumented_lines = instrumented_lines + profiling_output + [return_line]
    match = re.match(r"\s*", function.header)
    header_intent = match.group() if match else ""
    instrumented_lines = [function.header] + instrumented_lines + [header_intent + "}"]

    return "\n".join(instrumented_lines)


def render_for_profile(
    block: code.CodeBlock,
    instrumented_lines: list[str],
    line_contents: dict[int, str],
) -> None:
    if block.num_lines == 0:
        return

    lines = block.code_lines
    match = re.match(r"\s*", lines[0])
    indent = match.group() if match else ""
    line_number = block.start_line

    start_time_var = f"__start_time_{line_number}"
    end_time_var = f"__end_time_{line_number}"
    # Insert timing code
    instrumented_lines.append(
        indent + f"let {start_time_var} = DispatchTime.now().uptimeNanoseconds"
    )
    if len(lines) == 1:
        line_contents[line_number] = lines[0].replace('"', '\\"')
        instrumented_lines.append(lines[0])
    elif not block.can_split():
        for i, line in enumerate(lines):
            line_contents[line_number + i] = line.replace('"', '\\"')
            instrumented_lines.append(line)
    else:
        instrumented_lines.append(lines[0])
        line_contents[line_number] = lines[0].replace('"', '\\"')
        for inner in block.split():
            render_for_profile(inner, instrumented_lines, line_contents)
        instrumented_lines.append(lines[-1])
        line_contents[block.end_line] = lines[-1].replace('"', '\\"')

    instrumented_lines.append(indent + f"let {end_time_var} = DispatchTime.now().uptimeNanoseconds")
    instrumented_lines.append(
        indent + f"__line_times[{line_number}] = (__line_times[{line_number}] ?? 0) "
        f"+ ({end_time_var} - {start_time_var})"
    )
    instrumented_lines.append(
        indent + f"__line_hits[{line_number}] = (__line_hits[{line_number}] ?? 0) + 1"
    )
