from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

import hashlib

from virtualenv.cache import FileCache
from virtualenv.discovery.py_info import EXTENSIONS, PythonInfo
from virtualenv.info import IS_WIN, fs_is_case_sensitive, fs_supports_symlink


@pytest.fixture()
def cache(session_app_data, request):
    root_dir = Path(request.config.rootdir)
    py_info_script = root_dir / "src" / "virtualenv" / "discovery" / "py_info.py"
    py_info_hash = hashlib.sha256(py_info_script.read_bytes()).hexdigest()
    return FileCache(session_app_data, py_info_hash)


@pytest.fixture()
def current_info(session_app_data, cache):
    return PythonInfo.current(session_app_data, cache)


def test_discover_empty_folder(tmp_path, session_app_data, current_info, cache):
    with pytest.raises(RuntimeError):
        current_info.discover_exe(session_app_data, cache, prefix=str(tmp_path))


@pytest.fixture
def base(current_info):
    return (current_info.install_path("scripts"), ".")


@pytest.mark.skipif(not fs_supports_symlink(), reason="symlink is not supported")
@pytest.mark.parametrize("suffix", sorted({".exe", ".cmd", ""} & set(EXTENSIONS) if IS_WIN else [""]))
@pytest.mark.parametrize("into", ["scripts", "."])
@pytest.mark.parametrize("arch", ["", "64"])
@pytest.mark.parametrize("version", ["3.12", "3.11"])
@pytest.mark.parametrize("impl", ["CPython", "python"])
def test_discover_ok(tmp_path, suffix, impl, version, arch, into, caplog, session_app_data, current_info, cache):  # noqa: PLR0913
    caplog.set_level(logging.DEBUG)
    folder = tmp_path / into
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{impl}{version}{'t' if current_info.free_threaded else ''}"
    if arch:
        name += f"-{arch}"
    name += suffix
    dest = folder / name
    os.symlink(current_info.executable, str(dest))
    pyvenv = Path(current_info.executable).parents[1] / "pyvenv.cfg"
    if pyvenv.exists():
        (folder / pyvenv.name).write_text(pyvenv.read_text(encoding="utf-8"), encoding="utf-8")
    inside_folder = str(tmp_path)
    base = current_info.discover_exe(session_app_data, cache, inside_folder)
    found = base.executable
    dest_str = str(dest)
    if not fs_is_case_sensitive():
        found = found.lower()
        dest_str = dest_str.lower()
    assert found == dest_str
    assert len(caplog.messages) >= 1, caplog.text
    assert "get interpreter info via cmd: " in caplog.text

    dest.rename(dest.parent / (dest.name + "-1"))
    current_info._cache_exe_discovery.clear()  # noqa: SLF001
    with pytest.raises(RuntimeError):
        current_info.discover_exe(session_app_data, cache, inside_folder)
