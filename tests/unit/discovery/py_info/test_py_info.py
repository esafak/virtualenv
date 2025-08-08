from __future__ import annotations

import copy
import functools
import itertools
import json
import logging
import os
import sys
import sysconfig
from pathlib import Path
from textwrap import dedent
from typing import NamedTuple

import pytest

from virtualenv.create.via_global_ref.builtin.cpython.common import is_macos_brew
from virtualenv.discovery import cached_py_info
import hashlib

from virtualenv.cache import FileCache
from virtualenv.discovery.py_info import PythonInfo, VersionInfo
from virtualenv.discovery.py_spec import PythonSpec
from virtualenv.info import IS_PYPY, IS_WIN, fs_supports_symlink


@pytest.fixture(scope="session")
def cache(session_app_data, request):
    root_dir = Path(request.config.rootdir)
    py_info_script = root_dir / "src" / "virtualenv" / "discovery" / "py_info.py"
    py_info_hash = hashlib.sha256(py_info_script.read_bytes()).hexdigest()
    return FileCache(session_app_data, py_info_hash)


@pytest.fixture(scope="session")
def current_info(session_app_data, cache):
    return PythonInfo.current_system(session_app_data, cache)


def test_current_as_json(current_info):
    result = current_info._to_json()  # noqa: SLF001
    parsed = json.loads(result)
    a, b, c, d, e = sys.version_info
    f = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
    assert parsed["version_info"] == {"major": a, "minor": b, "micro": c, "releaselevel": d, "serial": e}
    assert parsed["free_threaded"] is f


def test_bad_exe_py_info_raise(tmp_path, session_app_data, cache):
    exe = str(tmp_path)
    with pytest.raises(RuntimeError) as context:
        PythonInfo.from_exe(exe, session_app_data, cache)
    msg = str(context.value)
    assert "code" in msg
    assert exe in msg


def test_bad_exe_py_info_no_raise(tmp_path, caplog, capsys, session_app_data, cache):
    caplog.set_level(logging.NOTSET)
    exe = str(tmp_path)
    result = PythonInfo.from_exe(exe, session_app_data, cache, raise_on_error=False)
    assert result is None
    out, _ = capsys.readouterr()
    assert not out
    messages = [r.message for r in caplog.records if r.name != "filelock"]
    assert len(messages) == 2
    msg = messages[0]
    assert "get interpreter info via cmd: " in msg
    msg = messages[1]
    assert str(exe) in msg
    assert "code" in msg


def test_satisfy_py_info(current_info):
    spec = ".".join(str(i) for i in current_info.version_info[0:3])
    parsed_spec = PythonSpec.from_string_spec(spec)
    matches = current_info.satisfies(parsed_spec, True)
    assert matches is True


def test_satisfy_not_arch(current_info):
    parsed_spec = PythonSpec.from_string_spec(
        f"{current_info.implementation}-{64 if current_info.architecture == 32 else 32}",
    )
    matches = current_info.satisfies(parsed_spec, True)
    assert matches is False


def test_satisfy_not_threaded(current_info):
    parsed_spec = PythonSpec.from_string_spec(
        f"{current_info.implementation}{current_info.version_info.major}{'' if current_info.free_threaded else 't'}",
    )
    matches = current_info.satisfies(parsed_spec, True)
    assert matches is False


def _generate_not_match_current_interpreter_version():
    result = []
    for i in range(3):
        ver = sys.version_info[0 : i + 1]
        for a in range(len(ver)):
            for o in [-1, 1]:
                temp = list(ver)
                temp[a] += o
                result.append(".".join(str(i) for i in temp))
    return result


_NON_MATCH_VER = _generate_not_match_current_interpreter_version()


@pytest.mark.parametrize("spec", _NON_MATCH_VER)
def test_satisfy_not_version(spec, current_info):
    parsed_spec = PythonSpec.from_string_spec(f"{current_info.implementation}{spec}")
    matches = current_info.satisfies(parsed_spec, True)
    assert matches is False


def test_py_info_cached_error(mocker, tmp_path, session_app_data, cache):
    spy = mocker.spy(cached_py_info, "_run_subprocess")
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(tmp_path), session_app_data, cache)
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(tmp_path), session_app_data, cache)
    assert spy.call_count == 1


@pytest.mark.skipif(not fs_supports_symlink(), reason="symlink is not supported")
def test_py_info_cached_symlink_error(mocker, tmp_path, session_app_data, cache):
    spy = mocker.spy(cached_py_info, "_run_subprocess")
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(tmp_path), session_app_data, cache)
    symlinked = tmp_path / "a"
    symlinked.symlink_to(tmp_path)
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(symlinked), session_app_data, cache)
    assert spy.call_count == 2


def test_py_info_cache_clear(mocker, session_app_data, cache):
    spy = mocker.spy(cached_py_info, "_run_subprocess")
    result = PythonInfo.from_exe(sys.executable, session_app_data, cache)
    assert result is not None
    count = 1 if result.executable == sys.executable else 2  # at least two, one for the venv, one more for the host
    assert spy.call_count >= count
    PythonInfo.clear_cache(cache)
    assert PythonInfo.from_exe(sys.executable, session_app_data, cache) is not None
    assert spy.call_count >= 2 * count


def test_py_info_cache_invalidation_on_py_info_change(mocker, session_app_data, cache):
    # 1. Get a PythonInfo object for the current executable, this will cache it.
    PythonInfo.from_exe(sys.executable, session_app_data, cache)

    # 2. Spy on _run_subprocess
    spy = mocker.spy(cached_py_info, "_run_subprocess")

    # 3. Modify the content of py_info.py
    py_info_script = Path(cached_py_info.__file__).parent / "py_info.py"
    original_content = py_info_script.read_text(encoding="utf-8")
    original_stat = py_info_script.stat()

    try:
        # 4. Clear the in-memory cache
        mocker.patch.dict(cached_py_info._CACHE, {}, clear=True)  # noqa: SLF001
        py_info_script.write_text(original_content + "\n# a comment", encoding="utf-8")
        py_info_hash = hashlib.sha256(py_info_script.read_bytes()).hexdigest()
        new_cache = FileCache(session_app_data, py_info_hash)

        # 5. Get the PythonInfo object again
        info = PythonInfo.from_exe(sys.executable, session_app_data, new_cache)

        # 6. Assert that _run_subprocess was called again
        if is_macos_brew(info):
            assert spy.call_count in {2, 3}
        else:
            assert spy.call_count == 2

    finally:
        # Restore the original content and timestamp
        py_info_script.write_text(original_content, encoding="utf-8")
        os.utime(str(py_info_script), (original_stat.st_atime, original_stat.st_mtime))


@pytest.mark.skipif(not fs_supports_symlink(), reason="symlink is not supported")
@pytest.mark.xfail(
    # https://doc.pypy.org/en/latest/install.html?highlight=symlink#download-a-pre-built-pypy
    IS_PYPY and IS_WIN and sys.version_info[0:2] >= (3, 9),
    reason="symlink is not supported",
)
@pytest.mark.skipif(not fs_supports_symlink(), reason="symlink is not supported")
def test_py_info_cached_symlink(mocker, tmp_path, session_app_data, cache):
    spy = mocker.spy(cached_py_info, "_run_subprocess")
    first_result = PythonInfo.from_exe(sys.executable, session_app_data, cache)
    assert first_result is not None
    count = spy.call_count
    # at least two, one for the venv, one more for the host
    exp_count = 1 if first_result.executable == sys.executable else 2
    assert count >= exp_count  # at least two, one for the venv, one more for the host

    new_exe = tmp_path / "a"
    new_exe.symlink_to(sys.executable)
    pyvenv = Path(sys.executable).parents[1] / "pyvenv.cfg"
    if pyvenv.exists():
        (tmp_path / pyvenv.name).write_text(pyvenv.read_text(encoding="utf-8"), encoding="utf-8")
    new_exe_str = str(new_exe)
    second_result = PythonInfo.from_exe(new_exe_str, session_app_data, cache)
    assert second_result.executable == new_exe_str
    assert spy.call_count == count + 1  # no longer needed the host invocation, but the new symlink is must


class PyInfoMock(NamedTuple):
    implementation: str
    architecture: int
    version_info: VersionInfo


@pytest.mark.parametrize(
    ("target", "position", "discovered"),
    [
        (
            PyInfoMock("CPython", 64, VersionInfo(3, 6, 8, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 64, VersionInfo(3, 6, 9, "final", 0)),
                PyInfoMock("PyPy", 64, VersionInfo(3, 6, 8, "final", 0)),
            ],
        ),
        (
            PyInfoMock("CPython", 64, VersionInfo(3, 6, 8, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 64, VersionInfo(3, 6, 9, "final", 0)),
                PyInfoMock("CPython", 32, VersionInfo(3, 6, 9, "final", 0)),
            ],
        ),
        (
            PyInfoMock("CPython", 64, VersionInfo(3, 8, 1, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 32, VersionInfo(2, 7, 12, "rc", 2)),
                PyInfoMock("PyPy", 64, VersionInfo(3, 8, 1, "final", 0)),
            ],
        ),
    ],
)
def test_system_executable_no_exact_match(  # noqa: PLR0913
    target,
    discovered,
    position,
    tmp_path,
    mocker,
    caplog,
    session_app_data,
    cache,
    current_info,
):
    """Here we should fallback to other compatible"""
    caplog.set_level(logging.DEBUG)

    def _make_py_info(of):
        base = copy.deepcopy(current_info)
        base.implementation = of.implementation
        base.version_info = of.version_info
        base.architecture = of.architecture
        return base

    discovered_with_path = {}
    names = []
    selected = None
    for pos, i in enumerate(discovered):
        path = tmp_path / str(pos)
        path.write_text("", encoding="utf-8")
        py_info = _make_py_info(i)
        py_info.system_executable = current_info.system_executable
        py_info.executable = current_info.system_executable
        py_info.base_executable = str(path)
        if pos == position:
            selected = py_info
        discovered_with_path[str(path)] = py_info
        names.append(path.name)

    target_py_info = _make_py_info(target)
    mocker.patch.object(target_py_info, "_find_possible_exe_names", return_value=names)
    mocker.patch.object(target_py_info, "_find_possible_folders", return_value=[str(tmp_path)])

    def func(k, app_data, cache, resolve_to_host, raise_on_error, env):  # noqa: ARG001, PLR0913
        return discovered_with_path[k]

    mocker.patch.object(target_py_info, "from_exe", side_effect=func)
    target_py_info.real_prefix = str(tmp_path)

    target_py_info.system_executable = None
    target_py_info.executable = str(tmp_path)
    mapped = target_py_info._resolve_to_system(session_app_data, target_py_info, cache)  # noqa: SLF001
    assert mapped.system_executable == current_info.system_executable
    found = discovered_with_path[mapped.base_executable]
    assert found is selected

    assert caplog.records[0].msg == "discover exe for %s in %s"
    for record in caplog.records[1:-1]:
        assert record.message.startswith("refused interpreter ")
        assert record.levelno == logging.DEBUG

    warn_similar = caplog.records[-1]
    assert warn_similar.levelno == logging.DEBUG
    assert warn_similar.msg.startswith("no exact match found, chosen most similar")


def test_py_info_ignores_distutils_config(monkeypatch, tmp_path, session_app_data, cache):
    raw = f"""
    [install]
    prefix={tmp_path}{os.sep}prefix
    install_purelib={tmp_path}{os.sep}purelib
    install_platlib={tmp_path}{os.sep}platlib
    install_headers={tmp_path}{os.sep}headers
    install_scripts={tmp_path}{os.sep}scripts
    install_data={tmp_path}{os.sep}data
    """
    (tmp_path / "setup.cfg").write_text(dedent(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    py_info = PythonInfo.from_exe(sys.executable, session_app_data, cache)
    distutils = py_info.distutils_install
    for key, value in distutils.items():
        assert not value.startswith(str(tmp_path)), f"{key}={value}"


def test_discover_exe_on_path_non_spec_name_match(mocker, current_info):
    suffixed_name = f"python{current_info.version_info.major}.{current_info.version_info.minor}m"
    if sys.platform == "win32":
        suffixed_name += Path(current_info.original_executable).suffix
    spec = PythonSpec.from_string_spec(suffixed_name)
    mocker.patch.object(current_info, "original_executable", str(Path(current_info.executable).parent / suffixed_name))
    assert current_info.satisfies(spec, impl_must_match=True) is True


def test_discover_exe_on_path_non_spec_name_not_match(mocker, current_info):
    suffixed_name = f"python{current_info.version_info.major}.{current_info.version_info.minor}m"
    if sys.platform == "win32":
        suffixed_name += Path(current_info.original_executable).suffix
    spec = PythonSpec.from_string_spec(suffixed_name)
    mocker.patch.object(
        current_info,
        "original_executable",
        str(Path(current_info.executable).parent / f"e{suffixed_name}"),
    )
    assert current_info.satisfies(spec, impl_must_match=True) is False


@pytest.mark.skipif(IS_PYPY, reason="setuptools distutils patching does not work")
def test_py_info_setuptools(current_info):
    from setuptools.dist import Distribution  # noqa: PLC0415

    assert Distribution
    assert current_info


@pytest.mark.usefixtures("_skip_if_test_in_system")
def test_py_info_to_system_raises(session_app_data, mocker, caplog, cache):
    caplog.set_level(logging.DEBUG)
    mocker.patch.object(PythonInfo, "_find_possible_folders", return_value=[])
    result = PythonInfo.from_exe(sys.executable, session_app_data, cache, raise_on_error=False)
    assert result is None
    log = caplog.records[-1]
    assert log.levelno == logging.INFO
    expected = f"ignore {sys.executable} due cannot resolve system due to RuntimeError('failed to detect "
    assert expected in log.message


def _stringify_schemes_dict(schemes_dict):
    """
    Since this file has from __future__ import unicode_literals, we manually cast all values of mocked install_schemes
    to str() as the original schemes are not unicode on Python 2.
    """
    return {str(n): {str(k): str(v) for k, v in s.items()} for n, s in schemes_dict.items()}


def test_custom_venv_install_scheme_is_prefered(mocker, current_info):
    # The paths in this test are Fedora paths, but we set them for nt as well, so the test also works on Windows,
    # despite the actual values are nonsense there.
    # Values were simplified to be compatible with all the supported Python versions.
    default_scheme = {
        "stdlib": "{base}/lib/python{py_version_short}",
        "platstdlib": "{platbase}/lib/python{py_version_short}",
        "purelib": "{base}/local/lib/python{py_version_short}/site-packages",
        "platlib": "{platbase}/local/lib/python{py_version_short}/site-packages",
        "include": "{base}/include/python{py_version_short}",
        "platinclude": "{platbase}/include/python{py_version_short}",
        "scripts": "{base}/local/bin",
        "data": "{base}/local",
    }
    venv_scheme = {key: path.replace("local", "") for key, path in default_scheme.items()}
    sysconfig_install_schemes = {
        "posix_prefix": default_scheme,
        "nt": default_scheme,
        "pypy": default_scheme,
        "pypy_nt": default_scheme,
        "venv": venv_scheme,
    }
    if getattr(sysconfig, "get_preferred_scheme", None):
        # define the prefix as sysconfig.get_preferred_scheme did before 3.11
        sysconfig_install_schemes["nt" if os.name == "nt" else "posix_prefix"] = default_scheme

    # On Python < 3.10, the distutils schemes are not derived from sysconfig schemes
    # So we mock them as well to assert the custom "venv" install scheme has priority
    distutils_scheme = {
        "purelib": "$base/local/lib/python$py_version_short/site-packages",
        "platlib": "$platbase/local/lib/python$py_version_short/site-packages",
        "headers": "$base/include/python$py_version_short/$dist_name",
        "scripts": "$base/local/bin",
        "data": "$base/local",
    }
    distutils_schemes = {
        "unix_prefix": distutils_scheme,
        "nt": distutils_scheme,
    }

    # We need to mock distutils first, so they don't see the mocked sysconfig,
    # if imported for the first time.
    # That can happen if the actual interpreter has the "venv" INSTALL_SCHEME
    # and hence this is the first time we are touching distutils in this process.
    # If distutils saw our mocked sysconfig INSTALL_SCHEMES, we would need
    # to define all install schemes.
    mocker.patch("distutils.command.install.INSTALL_SCHEMES", distutils_schemes)
    mocker.patch("sysconfig._INSTALL_SCHEMES", sysconfig_install_schemes)

    pyinfo = current_info
    pyver = f"{pyinfo.version_info.major}.{pyinfo.version_info.minor}"
    assert pyinfo.install_path("scripts") == "bin"
    assert pyinfo.install_path("purelib").replace(os.sep, "/") == f"lib/python{pyver}/site-packages"


@pytest.mark.skipif(not (os.name == "posix" and sys.version_info[:2] >= (3, 11)), reason="POSIX 3.11+ specific")
def test_fallback_existent_system_executable(mocker, current_info):
    # Posix may execute a "python" out of a venv but try to set the base_executable
    # to "python" out of the system installation path. PEP 394 informs distributions
    # that "python" is not required and the standard `make install` does not provide one

    # Falsify some data to look like we're in a venv
    current_info.prefix = current_info.exec_prefix = "/tmp/tmp.izZNCyINRj/venv"  # noqa: S108
    current_info.executable = current_info.original_executable = os.path.join(current_info.prefix, "bin/python")

    # Since we don't know if the distribution we're on provides python, use a binary that should not exist
    mocker.patch.object(
        sys,
        "_base_executable",
        os.path.join(os.path.dirname(current_info.system_executable), "idontexist"),
    )
    mocker.patch.object(sys, "executable", current_info.executable)

    # ensure it falls back to an alternate binary name that exists
    system_executable = current_info._fast_get_system_executable()  # noqa: SLF001
    assert os.path.basename(system_executable) in [
        f"python{v}"
        for v in (current_info.version_info.major, f"{current_info.version_info.major}.{current_info.version_info.minor}")
    ]
    assert os.path.exists(system_executable)


@pytest.mark.skipif(sys.version_info[:2] != (3, 10), reason="3.10 specific")
def test_uses_posix_prefix_on_debian_3_10_without_venv(mocker, current_info):
    # this is taken from ubuntu 22.04 /usr/lib/python3.10/sysconfig.py
    sysconfig_install_schemes = {
        "posix_prefix": {
            "stdlib": "{installed_base}/{platlibdir}/python{py_version_short}",
            "platstdlib": "{platbase}/{platlibdir}/python{py_version_short}",
            "purelib": "{base}/lib/python{py_version_short}/site-packages",
            "platlib": "{platbase}/{platlibdir}/python{py_version_short}/site-packages",
            "include": "{installed_base}/include/python{py_version_short}{abiflags}",
            "platinclude": "{installed_platbase}/include/python{py_version_short}{abiflags}",
            "scripts": "{base}/bin",
            "data": "{base}",
        },
        "posix_home": {
            "stdlib": "{installed_base}/lib/python",
            "platstdlib": "{base}/lib/python",
            "purelib": "{base}/lib/python",
            "platlib": "{base}/lib/python",
            "include": "{installed_base}/include/python",
            "platinclude": "{installed_base}/include/python",
            "scripts": "{base}/bin",
            "data": "{base}",
        },
        "nt": {
            "stdlib": "{installed_base}/Lib",
            "platstdlib": "{base}/Lib",
            "purelib": "{base}/Lib/site-packages",
            "platlib": "{base}/Lib/site-packages",
            "include": "{installed_base}/Include",
            "platinclude": "{installed_base}/Include",
            "scripts": "{base}/Scripts",
            "data": "{base}",
        },
        "deb_system": {
            "stdlib": "{installed_base}/{platlibdir}/python{py_version_short}",
            "platstdlib": "{platbase}/{platlibdir}/python{py_version_short}",
            "purelib": "{base}/lib/python3/dist-packages",
            "platlib": "{platbase}/{platlibdir}/python3/dist-packages",
            "include": "{installed_base}/include/python{py_version_short}{abiflags}",
            "platinclude": "{installed_platbase}/include/python{py_version_short}{abiflags}",
            "scripts": "{base}/bin",
            "data": "{base}",
        },
        "posix_local": {
            "stdlib": "{installed_base}/{platlibdir}/python{py_version_short}",
            "platstdlib": "{platbase}/{platlibdir}/python{py_version_short}",
            "purelib": "{base}/local/lib/python{py_version_short}/dist-packages",
            "platlib": "{platbase}/local/lib/python{py_version_short}/dist-packages",
            "include": "{installed_base}/local/include/python{py_version_short}{abiflags}",
            "platinclude": "{installed_platbase}/local/include/python{py_version_short}{abiflags}",
            "scripts": "{base}/local/bin",
            "data": "{base}",
        },
    }
    # reset the default in case we're on a system which doesn't have this problem
    sysconfig_get_path = functools.partial(sysconfig.get_path, scheme="posix_local")

    # make it look like python3-distutils is not available
    mocker.patch.dict(sys.modules, {"distutils.command": None})
    mocker.patch("sysconfig._INSTALL_SCHEMES", sysconfig_install_schemes)
    mocker.patch("sysconfig.get_path", sysconfig_get_path)
    mocker.patch("sysconfig.get_default_scheme", return_value="posix_local")

    pyinfo = current_info
    pyver = f"{pyinfo.version_info.major}.{pyinfo.version_info.minor}"
    assert pyinfo.install_path("scripts") == "bin"
    assert pyinfo.install_path("purelib").replace(os.sep, "/") == f"lib/python{pyver}/site-packages"
