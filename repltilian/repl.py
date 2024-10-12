import json
import os
import re
import tempfile
from dataclasses import dataclass
from typing import Any

import pexpect

from repltilian import code, constants, repl_output


@dataclass
class Options:
    output_hide_inputs: bool = True
    output_stop_pattern: str | None = None
    timeout: float = 0.01


class SwiftREPL:
    def __init__(self, cwd: str | None = None, options: Options = Options()) -> None:
        """Initialize the Swift REPL.

        Args:
            cwd: optional path to the working directory, a folder with Package.swift file. If
                provided, the REPL will be started with `swift run --repl` command, otherwise
                with `swift repl`.
            options: an instance of REPLOptions class with optional parameters for REPL output.
        """
        env = os.environ.copy()
        env = {"PATH": env["PATH"], "SHELL": env["SHELL"], "TERM": "dumb"}
        command = "swift run --repl"
        if cwd is None:
            command = "swift repl"
        self._process = pexpect.spawn(command, encoding="utf-8", timeout=1, env=env, cwd=cwd)
        self.options = options
        self.vars = VariablesRegister(self)
        self._reload_paths: set[str] = set()
        self._output: str | None = None

        self.run(constants.INIT_COMMANDS, verbose=False)
        self.run("""print("REPL is running !")""")

    def add_reload_file(self, path: str) -> None:
        """Path to file which will be added to the REPL input before running the code."""
        if path not in self._reload_paths:
            self._reload_paths.add(path)

    def run(
        self,
        prompt: str,
        autoreload: bool = False,
        verbose: bool = True,
    ) -> None:
        include_paths: list[str] | None = None
        if self._reload_paths and autoreload:
            include_paths = list(self._reload_paths)
        if include_paths:
            include_text = code.get_files_content(include_paths)
            prompt = include_text + "\n" + constants.END_OF_INCLUDE + "\n" + prompt

        self._process.sendline(prompt)
        repl_raw_outputs = []
        while True:
            try:
                buffer = self._process.read_nonblocking(
                    size=self._process.maxread,
                    timeout=self.options.timeout,
                )
                repl_raw_outputs.append(buffer)
            except pexpect.exceptions.TIMEOUT:
                # a regex which matches the waiting prompt e.g. "1>" or "102>" but
                # there must not be any text after the prompt
                prompt_pattern = re.compile(r"(\d+>$)")
                buffer_end = "".join(repl_raw_outputs[-10:])
                has_prompt = prompt_pattern.search(repl_output.clean(buffer_end))
                if has_prompt is None:
                    continue
                break

        output = repl_output.clean("".join(repl_raw_outputs))
        self._output = output
        if error_line := repl_output.search_for_error(output):
            repl_output.print_output(output)
            raise ValueError(f"Error in Swift code: '{error_line}'")

        if verbose:
            repl_output.print_output(
                output,
                output_stop_pattern=self.options.output_stop_pattern,
                output_hide_inputs=self.options.output_hide_inputs,
            )

        variable_updates = repl_output.find_variables(output)
        for key, (dtype, value) in variable_updates.items():
            self.vars[key] = Variable(self, key, dtype, value)

    def close(self) -> None:
        self._process.sendline(":quit")
        self._process.terminate()
        self._process.close()


class Variable:
    def __init__(self, repl_ref: SwiftREPL, name: str, dtype: str, value: str):
        self.name = name
        self.dtype = dtype
        self.value = value
        self._repl = repl_ref

    def get(self, verbose: bool = False) -> Any:
        """Return the JSON representation of the variable obtained through
        the JSON deserialization from REPL process.
        """
        if self._repl is None:
            raise ValueError("Variable is not associated with a REPL instance.")

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
            raise ValueError(
                "Only Variable instances can be added to the register, use set " "method instead."
            )
        super().__setitem__(key, value)

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
