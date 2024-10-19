from repltilian.repl import SwiftREPL, SwiftREPLException  # noqa: F401

__all__ = ["SwiftREPL", "SwiftREPLException", "load_ipython_extension"]


def load_ipython_extension(ipython):  # type: ignore
    from repltilian.ipython import REPLMagic

    magic = REPLMagic(ipython)
    ipython.register_magics(magic)
