from __future__ import annotations

import os
import sys

import pytest

from virtualenv.create.via_global_ref.venv import Venv
from virtualenv.discovery.py_info import PythonInfo


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks are not well supported on Windows")
def test_venv_symlinks_to_specific_python(tmp_path):
    """Test that the created venv symlinks to the specific python version and not a generic one."""
    # Create a fake python executable
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    specific_python = python_dir / "python3.10"
    specific_python.touch()
    specific_python.chmod(0o755)

    # Create a symlink to the fake python
    generic_python = python_dir / "python3"
    os.symlink(specific_python, generic_python)

    # Create a mock interpreter object
    class MockInterpreter(PythonInfo):
        def __init__(self):
            super().__init__()
            self.executable = str(generic_python)
            self.system_executable = str(specific_python)
            self.version_info = (3, 10, 0, "final", 0)

    # Create a mock options object
    class MockOptions:
        def __init__(self):
            self.describe = None
            self.app_data = None
            self.clear = False
            self.symlinks = True
            self.enable_system_site_package = False

    # Create the venv
    venv_dir = tmp_path / "venv"
    venv = Venv(MockOptions(), MockInterpreter())
    venv.create(str(venv_dir))

    # Check the symlink
    created_python = venv_dir / "bin" / "python"
    assert os.path.islink(created_python)
    assert os.path.realpath(created_python) == os.path.realpath(specific_python)
