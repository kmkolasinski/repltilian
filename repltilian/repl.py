import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pexpect

from repltilian import code, constants, profiler, repl_output


class SwiftREPLException(Exception):
    pass


@dataclass
class Options:
    output_hide_inputs: bool = True
    output_hide_variables: bool = False
    output_stop_pattern: str | None = None
    timeout: float = 0.01
    num_read_calls: int = 1
    maxread: int = 10000


class SwiftREPL:
    def __init__(self, cwd: str | None = None, options: Options = Options()) -> None:
        """Initialize the Swift REPL.

        Args:
            cwd: optional path to the working directory, a folder with Package.swift file. If
                provided, the REPL will be started with `swift run --repl` command, otherwise
                with `swift repl`.
            options: an instance of REPLOptions class with optional parameters for REPL output.
        """
        self.cwd = cwd
        self.options = options
        self.vars = VariablesRegister(self)
        self._initialized = False
        self._reload_paths: set[str] = set()
        self._output: str | None = None

        self._process = self._initiate_repl()
        self.run(constants.INIT_COMMANDS, verbose=False)
        self.run("""print("REPL is running !")""")

    def _initiate_repl(self) -> pexpect.spawn:
        env = os.environ.copy()
        env = {"PATH": env["PATH"], "SHELL": env["SHELL"], "TERM": "dumb"}
        command = "swift run --repl"
        if self.cwd is None:
            command = "swift repl"

        self._process = pexpect.spawn(
            command=command,
            encoding="utf-8",
            timeout=1,
            env=env,
            cwd=self.cwd,
        )
        self._initialized = True
        return self._process

    def add_reload_file(self, path: str | Path) -> None:
        """Path to file which will be added to the REPL input before running the code."""
        if path not in self._reload_paths:
            if not Path(path).is_file():
                raise FileNotFoundError(f"File '{path}' does not exist.")
            self._reload_paths.add(str(path))

    def clear_reload_files(self) -> None:
        """Clear the list of files which are reloaded before running the code."""
        self._reload_paths.clear()

    def run(
        self,
        prompt: str,
        autoreload: bool = False,
        verbose: bool = True,
    ) -> None:
        if not self._initialized:
            raise SwiftREPLException("REPL is not initialized.")

        include_paths: list[str] | None = None
        if self._reload_paths and autoreload:
            include_paths = list(self._reload_paths)
        if include_paths:
            include_text = code.get_files_content(include_paths)
            prompt = include_text + "\n" + constants.END_OF_INCLUDE + "\n" + prompt

        if not prompt.startswith("\n"):
            prompt = "\n" + prompt

        blocks = repl_output.batch_prompt(prompt, 100)
        repl_raw_outputs = []
        while True:
            try:
                if blocks:
                    block = blocks.pop(0)
                    print("> sending", len(block))
                    self._process.sendline(block)

                for _ in range(self.options.num_read_calls):
                    print("> reading")
                    buffer = self._process.read_nonblocking(
                        size=self.options.maxread,
                        timeout=self.options.timeout,
                    )
                    print("> read:", len(buffer))
                    repl_raw_outputs.append(buffer)
            except pexpect.exceptions.EOF as e:
                raise SwiftREPLException(
                    f"REPL crashed with error: '{e}'. Did you try to run "
                    f"async function ? If yes consider to use: 'try runSync "
                    f"{{ try await yourAsyncFunction }}'"
                )
            except pexpect.exceptions.TIMEOUT:
                # a regex which matches the waiting prompt e.g. "1>" or "102>" but
                # there must not be any text after the prompt
                prompt_pattern = re.compile(r"(\d+>$)")
                buffer_end = "".join(repl_raw_outputs[-10:])
                has_prompt = prompt_pattern.search(repl_output.clean(buffer_end))
                if has_prompt is None:
                    continue
                break
            except Exception as e:
                raise SwiftREPLException(f"REPL error: {e}")

        output = repl_output.clean("".join(repl_raw_outputs))
        self._output = output
        if error_line := repl_output.search_for_error(output):
            repl_output.print_output(output)
            raise SwiftREPLException(f"Error in Swift code: '{error_line}'")

        if verbose:
            repl_output.print_output(
                output,
                stop_output_at_pattern=self.options.output_stop_pattern,
                hide_inputs=self.options.output_hide_inputs,
                hide_variables=self.options.output_hide_variables,
            )

        variable_updates = repl_output.find_variables(output)
        for key, (dtype, value) in variable_updates.items():
            self.vars[key] = Variable(self, key, dtype, value)

    def line_profile(
        self,
        prompt: str,
        function_name: str,
        source_path: str,
        autoreload: bool = False,
    ) -> None:
        """Return the code with line profiling instrumentation."""
        source_code = code.get_file_content(source_path)
        profiled_function = profiler.get_function_for_line_profiler(function_name, source_code)
        prompt = profiled_function + "\n" + prompt
        self.run(prompt, autoreload=autoreload)

    def close(self) -> None:
        self._process.sendline(":quit")
        self._process.terminate()
        self._process.close()
        self._initialized = False


class Variable:
    def __init__(
        self,
        repl_ref: SwiftREPL,
        name: str,
        dtype: str | None = None,
        value: str | None = None,
    ):
        self.name = name
        self.dtype = dtype
        self.value = value
        self._repl = repl_ref

    def get(self, verbose: bool = False) -> Any:
        """Return the JSON representation of the variable obtained through
        the JSON deserialization from REPL process.
        """
        if self._repl is None:
            raise SwiftREPLException("Variable is not associated with a REPL instance.")

        with tempfile.NamedTemporaryFile() as tmpfile:
            path = f"{tmpfile.name}.json"
            self._repl.run(
                f'_serializeObject({self.name}, to: "{path}")',
                verbose=verbose,
                autoreload=False,
            )
            with open(path) as file:
                data = json.load(file)
            return data

    def __repr__(self) -> str:
        return f"{self.name}[{self.dtype}] at {id(self)}"


class VariablesRegister(dict[str, Variable]):
    """A class which is responsible for managing variables in the REPL."""

    def __init__(self, repl_ref: SwiftREPL) -> None:
        super().__init__()
        self._repl_ref = repl_ref

    def __setitem__(self, key: str, value: Any | Variable) -> None:
        if not isinstance(value, Variable):
            raise SwiftREPLException(
                "Only Variable instances can be added to the register, use set " "method instead."
            )
        super().__setitem__(key, value)

    def __getitem__(self, key: str) -> Variable:
        if key not in self:
            return Variable(self._repl_ref, key)
        return super().__getitem__(key)

    def set(self, name: str, dtype: str, value: Any, verbose: bool = False) -> None:
        """Set a variable in the REPL with the given name, type and value. This function will
        create or update existing variable.
        """
        with tempfile.NamedTemporaryFile() as tmpfile:
            path = f"{tmpfile.name}.json"
            with open(path, "w") as fp:
                json.dump(value, fp)

            self._repl_ref.run(
                f'\nvar {name}: {dtype} = try _deserializeObject("{path}")\n',
                verbose=verbose,
                autoreload=False,
            )
            self[name] = Variable(self._repl_ref, name, dtype, value)
