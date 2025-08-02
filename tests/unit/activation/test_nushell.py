from __future__ import annotations

from shutil import which
from argparse import Namespace

import pytest

from virtualenv.activation import NushellActivator
from virtualenv.info import IS_WIN


def test_nushell_tkinter_generation(tmp_path):
    # GIVEN
    class MockInterpreter:
        pass

    interpreter = MockInterpreter()
    interpreter.tcl_lib = "/path/to/tcl"
    interpreter.tk_lib = "/path/to/tk"

    class MockCreator:
        def __init__(self, dest):
            self.dest = dest
            self.bin_dir = dest / "bin"
            self.bin_dir.mkdir()
            self.interpreter = interpreter
            self.pyenv_cfg = {}
            self.env_name = "my-env"

    creator = MockCreator(tmp_path)
    options = Namespace(prompt=None)
    activator = NushellActivator(options)

    # WHEN
    activator.generate(creator)
    content = (creator.bin_dir / "activate.nu").read_text(encoding="utf-8")

    # THEN
    expected_tcl = "let new_env = $new_env | merge { TCL_LIBRARY: r#'/path/to/tcl'# }"
    expected_tk = "let new_env = $new_env | merge { TK_LIBRARY: r#'/path/to/tk'# }"

    print("--- DEBUGGING INFO ---")
    print(f"Expected TCL line: {expected_tcl}")
    print(f"Expected TK line: {expected_tk}")
    print("\n--- Generated activate.nu content ---")
    print(content)
    print("--- END DEBUGGING INFO ---")

    assert expected_tcl in content
    assert expected_tk in content


def test_nushell(activation_tester_class, activation_tester):
    class Nushell(activation_tester_class):
        def __init__(self, session) -> None:
            cmd = which("nu")
            if cmd is None and IS_WIN:
                cmd = "c:\\program files\\nu\\bin\\nu.exe"

            super().__init__(NushellActivator, session, cmd, "activate.nu", "nu")

            self.activate_cmd = "overlay use"
            self.unix_line_ending = not IS_WIN

        def print_prompt(self):
            return r"print $env.VIRTUAL_PREFIX"

        def activate_call(self, script):
            # Commands are called without quotes in Nushell
            cmd = self.activate_cmd
            scr = self.quote(str(script))
            return f"{cmd} {scr}".strip()

    activation_tester(Nushell)
