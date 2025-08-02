from __future__ import annotations

from argparse import Namespace

import pytest

from virtualenv.activation import CShellActivator


@pytest.mark.parametrize(
    ("tcl_lib", "tk_lib", "present"),
    [
        ("/path/to/tcl", "/path/to/tk", True),
        (None, None, False),
    ],
)
def test_cshell_tkinter_generation(tmp_path, tcl_lib, tk_lib, present):
    # GIVEN
    class MockInterpreter:
        pass

    interpreter = MockInterpreter()
    interpreter.tcl_lib = tcl_lib
    interpreter.tk_lib = tk_lib

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
    activator = CShellActivator(options)

    # WHEN
    activator.generate(creator)
    content = (creator.bin_dir / "activate.csh").read_text(encoding="utf-8")

    # THEN
    if present:
        assert "setenv TCL_LIBRARY '/path/to/tcl'" in content
        assert "setenv TK_LIBRARY '/path/to/tk'" in content
        assert "test $?_OLD_VIRTUAL_TCL_LIBRARY != 0" in content
        assert "test $?_OLD_VIRTUAL_TK_LIBRARY != 0" in content
    else:
        assert "setenv TCL_LIBRARY ''" in content
