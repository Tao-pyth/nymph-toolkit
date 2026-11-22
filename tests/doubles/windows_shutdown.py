"""Inject shutdown resets only in the dedicated child-process fixture."""

# SPDX-License-Identifier: Apache-2.0
import socket

from tests.doubles.hybrid import Dummy


def factory(context, config):
    # The fixture is used only in owned child processes. Leave the parent
    # interpreter and application sockets untouched. Actual close still runs.
    original = socket.socket.shutdown
    def shutdown(sock, how):
        if how == socket.SHUT_RDWR:
            error = ConnectionResetError("injected child shutdown reset")
            error.winerror = 10054
            raise error
        return original(sock, how)
    socket.socket.shutdown = shutdown
    return Dummy(context, config)
