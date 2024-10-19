import json
from typing import Any

from ipykernel import zmqshell  # type: ignore
from IPython.core import magic  # type: ignore

from repltilian import SwiftREPL, repl_output


@magic.magics_class
class REPLMagic(magic.Magics):  # type: ignore
    def __init__(self, shell: zmqshell.ZMQInteractiveShell):
        """Initialize the REPLMagic class state."""
        super().__init__(shell)
        self.flip = False
        self._repl_instance: SwiftREPL | None = None

    def get_repl(self) -> SwiftREPL:
        if self._repl_instance is None:
            raise ValueError(
                "REPL is not initialized. Use %repl_init path/package to initialize the REPL."
            )
        return self._repl_instance

    @magic.line_magic  # type: ignore
    def repl_init(self, line: str) -> None:
        """Initialize (or reinitialize) the REPL instance.
        Usage: %repl_init path/to/package
        """
        line = line.strip()
        if self._repl_instance is not None:
            print("Closing previous REPL instance.")
            self._repl_instance.close()
        if line:
            print(f"Initializing REPL with package: '{line}' ...")
        else:
            print("Initializing REPL ...")
        self._repl_instance = SwiftREPL(line or None)

    @magic.cell_magic  # type: ignore
    def repl(self, line: str, cell: str) -> None:
        """Run the code in the REPL.

        Parameters:
            --verbose: print the output of the REPL
            --autoreload: reload the REPL instance
        """
        verbose = "verbose" in line
        autoreload = "autoreload" in line
        self.get_repl().run(cell, autoreload=autoreload, verbose=verbose)

    @magic.line_magic  # type: ignore
    def repl_instance(self, line: str) -> SwiftREPL:
        """Get the current REPL instance."""
        return self.get_repl()

    @magic.line_magic  # type: ignore
    def repl_add_file(self, line: str) -> None:
        """Add the file to the list of files which are reloaded before running the code.
        Usage: %repl_add_file path/to/file
        """
        line = line.strip()
        self.get_repl().add_reload_file(line)

    @magic.line_magic  # type: ignore
    def repl_get(self, line: str) -> Any:
        """Get the value of the variable from the REPL.
        Usage: %repl_get variable_name
        """
        line = line.strip()
        return self.get_repl().vars[line].get()

    @magic.line_magic  # type: ignore
    def repl_set(self, line: str) -> None:
        """Set the value of the variable in the running REPL.
        Usage: %repl_set var_name: var_type = var_value
        """
        repl = self.get_repl()
        line = line.strip()

        variables = repl_output.find_variables(line)
        if len(variables) != 1:
            print(
                "Invalid variable declaration! Expected format: " "var_name: var_type = var_value"
            )
            return
        var_name = list(variables.keys())[0]
        var_type, var_value = variables[var_name]
        var_value = json.loads(var_value)
        repl.vars.set(var_name, var_type, var_value)
