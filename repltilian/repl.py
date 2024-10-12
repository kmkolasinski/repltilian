import json
import os
import re
import tempfile
from typing import Any

import pexpect

from repltilian import code, constants, repl_output


class SwiftREPL:
    def __init__(self, cwd: str | None = None):
        env = os.environ.copy()
        # env.pop("LD_LIBRARY_PATH", None)
        # env.pop("LIBRARY_ROOTS", None)
        # env.pop("XDG_DATA_DIRS", None)
        env = {"PATH": env["PATH"], "SHELL": env["SHELL"], "TERM": "dumb"}
        # env["TERM"] = "dumb"
        print(env)

        command = "swift run --repl"
        if cwd is None:
            command = "swift repl"
        self._process = pexpect.spawn(command, encoding="utf-8", timeout=1, env=env, cwd=cwd)
        self.vars = VariablesRegister(self)
        self._reload_paths: set[str] = set()
        self._output: str | None = None
        self.run(constants.INIT_COMMANDS, verbose=False)
        self.run("""print("REPL is running !")""")

    def add_reload_file(self, path: str):
        if path not in self._reload_paths:
            self._reload_paths.add(path)

    def run(
        self,
        prompt: str,
        timeout: float = 0.01,
        verbose: bool = True,
        reload: bool = False,
        name_mapping: dict[str, str] | None = None,
        output_stop_pattern: str | None = None,
    ):
        include = None
        if self._reload_paths and reload:
            include = list(self._reload_paths)
        if include:
            include_content = []
            for file_path in include:
                include_code = code.get_file_content(file_path)
                include_content.append(include_code)
            include_text = "\n".join(include_content)
            if name_mapping is not None:
                for old_name, new_name in name_mapping.items():
                    include_text = include_text.replace(old_name, new_name)
            prompt = include_text + "\n" + constants.END_OF_INCLUDE + "\n" + prompt

        self._process.sendline(prompt)
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
                buffer_end_clean = repl_output.clean(buffer_end)
                has_prompt = prompt_pattern.search(buffer_end_clean)
                if has_prompt is None:
                    continue
                break

        incoming_str = "".join(incoming)
        output = repl_output.clean(incoming_str)
        if repl_output.has_error(output):
            print(output)
            raise ValueError("Error in Swift code!")
        self._output = output
        if verbose:
            _, output = repl_output.split_output_by_end_of_include(output)
            if output_stop_pattern is not None:
                output_lines = output.split("\n")
                stop_k = 0
                for i, line in enumerate(output_lines):
                    stop_k = i
                    if output_stop_pattern in line:
                        break
                output = "\n".join(output_lines[:stop_k])
            print(output)

        variable_updates = repl_output.find_variables(output)
        updates = {k: Variable(k, v[0], v[1]) for k, v in variable_updates.items()}
        self.vars.update(updates)
        return output

    def close(self):
        # Exit the REPL
        self._process.sendline(":quit")
        self._process.terminate()
        self._process.close()


class Variable:
    def __init__(self, name: str, dtype: str, value: str):
        self.name = name
        self.dtype = dtype
        self.value = value
        self._repl: SwiftREPL | None = None

    def str(self) -> str:
        return repl_output.extract_string_value(self.value)

    def json(self, verbose: bool = False) -> Any:
        if self._repl is None:
            raise ValueError("Variable is not associated with a REPL instance.")

        with tempfile.NamedTemporaryFile() as tmpfile:
            path = f"{tmpfile.name}.json"
            self._repl.run(
                f'_serializeObject({self.name}, to: "{path}")',
                verbose=verbose,
                reload=False,
            )
            with open(path) as file:
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
