"""Local pytest compatibility shims.

Home Assistant 2026.6 imports ``fcntl`` while loading its pytest plugin. The
module is POSIX-only, so provide the tiny surface needed for collection on
Windows test runs. Linux CI keeps using the real stdlib module.
"""

from __future__ import annotations

import sys
from types import ModuleType

if sys.platform == "win32":
    import socket as _socket

    _original_socket = _socket.socket
    _original_socketpair = _socket.socketpair

    def _loopback_socketpair(
        family: int | None = None,
        type: int = _socket.SOCK_STREAM,  # noqa: A002
        proto: int = 0,
    ) -> tuple[_socket.socket, _socket.socket]:
        """Create a local socket pair without pytest-socket's guarded socket."""
        if family not in (None, _socket.AF_INET, _socket.AF_INET6):
            return _original_socketpair(family, type, proto)

        socket_family = _socket.AF_INET if family is None else family
        host = "::1" if socket_family == _socket.AF_INET6 else "127.0.0.1"
        listener = _original_socket(socket_family, type, proto)
        try:
            listener.bind((host, 0))
            listener.listen(1)
            client = _original_socket(socket_family, type, proto)
            try:
                client.connect(listener.getsockname())
                guarded_socket = _socket.socket
                try:
                    _socket.socket = _original_socket
                    server, _address = listener.accept()
                finally:
                    _socket.socket = guarded_socket
                return server, client
            except Exception:
                client.close()
                raise
        finally:
            listener.close()

    _socket.socketpair = _loopback_socketpair


if sys.platform == "win32" and "fcntl" not in sys.modules:
    fcntl = ModuleType("fcntl")
    fcntl.LOCK_EX = 1
    fcntl.LOCK_NB = 2
    fcntl.LOCK_UN = 8
    fcntl.flock = lambda _fd, _operation: None
    sys.modules["fcntl"] = fcntl

if sys.platform == "win32" and "resource" not in sys.modules:
    resource = ModuleType("resource")
    resource.RLIMIT_NOFILE = 7
    resource.getrlimit = lambda _resource: (2048, 2048)
    resource.setrlimit = lambda _resource, _limits: None
    sys.modules["resource"] = resource
