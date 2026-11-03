# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Best-effort guard for the process that runs generated raster code.

The guard removes secrets from the worker and uses a Python audit hook to block
file access outside the GeoFaham data folders, outbound Python sockets, process
creation, and ctypes. Native libraries such as GDAL bypass audit hooks, so
deployments that accept untrusted prompts still need OS isolation (container,
read-only filesystem, egress policy).
"""
import contextlib
import copy
import dataclasses
import ipaddress
import os
import site
import socket
import sys
import tempfile
from pathlib import Path

_ENV_NAMES = {
    "PATH", "HOME", "USER", "LANG", "LANGUAGE", "TZ", "TMPDIR", "TEMP", "TMP",
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "CONDA_PREFIX", "VIRTUAL_ENV",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
}
_ENV_PREFIXES = ("LC_", "GDAL_", "CPL_", "PROJ_", "OGR_", "VSI_", "OMP_", "MKL_", "OPENBLAS_")
_BLOCKED_EVENTS = {
    "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
    "os.fork", "os.forkpty", "os.startfile", "pty.spawn", "webbrowser.open",
    "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function",
}
_NETWORK_EVENTS = {"socket.connect", "socket.sendto", "socket.sendmsg", "socket.bind"}
_LOOKUP_EVENTS = {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex"}
_CODE_SUFFIXES = (".py", ".pyc", ".pyi", ".so", ".pyd")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_active = False


@contextlib.contextmanager
def guarded():
    """Enforce the installed guard (process-wide, including dask threads) inside this block."""
    global _active
    previous, _active = _active, True
    try:
        yield
    finally:
        _active = previous


def scrub_environment() -> None:
    """Keep only variables that libraries need; drop credentials and model configs."""
    kept = {k: v for k, v in os.environ.items() if k in _ENV_NAMES or k.startswith(_ENV_PREFIXES)}
    os.environ.clear()
    os.environ.update(kept)


def strip_secrets(config):
    """Return a copy of the config without database credentials or model client configs."""
    config = copy.deepcopy(config)
    config.database.user = None
    config.database.password = None
    for field in dataclasses.fields(config):
        if field.name.endswith("model_client"):
            setattr(config, field.name, "")
    return config


def _is_loopback(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    host = str(host).strip("[]")
    if host in ("", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def install_io_guard(*data_dirs) -> None:
    """Install the audit hook used by guarded(). Hooks cannot be removed, so call it only in the worker."""
    def real(path) -> str:
        return os.path.realpath(os.fspath(path))

    writable = tuple({real(p) for p in (*data_dirs, tempfile.gettempdir())})
    library = {sys.prefix, sys.base_prefix, sys.exec_prefix, *site.getsitepackages()}
    if site.ENABLE_USER_SITE and site.getusersitepackages():
        library.add(site.getusersitepackages())
    readable = writable + tuple({real(p) for p in library}) + ("/usr/share/zoneinfo",)
    project = real(_PROJECT_ROOT)
    devices = {"/dev/null", "/dev/urandom", "/dev/random"}

    def inside(path: str, roots) -> bool:
        return any(path == root or path.startswith(root + os.sep) for root in roots)

    def check_open(path, mode, flags) -> None:
        if path is None or isinstance(path, int):
            return
        path = real(os.fsdecode(path))
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or bool((flags or 0) & _WRITE_FLAGS)
        if path in devices or inside(path, writable):
            return
        if not writing and (inside(path, readable) or (inside(path, (project,)) and path.endswith(_CODE_SUFFIXES))):
            return
        raise PermissionError(f"Raster sandbox blocked {'write to' if writing else 'read of'} {path}")

    def hook(event, args):
        if not _active:
            return
        if event == "open":
            check_open(*args[:3])
        elif event in _BLOCKED_EVENTS:
            raise PermissionError(f"Raster sandbox blocked {event}")
        elif event in _NETWORK_EVENTS:
            sock, address = args[0], args[1]
            if getattr(sock, "family", None) == getattr(socket, "AF_UNIX", None):
                return
            if not (isinstance(address, tuple) and _is_loopback(address[0])):
                raise PermissionError(f"Raster sandbox blocked network access to {address!r}")
        elif event in _LOOKUP_EVENTS and not _is_loopback(args[0]):
            raise PermissionError(f"Raster sandbox blocked host lookup for {args[0]!r}")

    sys.addaudithook(hook)
