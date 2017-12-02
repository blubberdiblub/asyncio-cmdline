#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional

import asyncio
import errno
import io
import os

from functools import partial


class Protocol(asyncio.Protocol):

    EOF = object()

    def __init__(self,
                 connect: asyncio.Future = None,
                 disconnect: asyncio.Future = None) -> None:

        super().__init__()

        self.connected = False
        self.transport = None
        self.exception = None
        self.paused = False
        self.received = []

        self.connect_future = connect
        self.disconnect_future = disconnect

    def connection_made(self, transport: asyncio.BaseTransport) -> None:

        if self.connect_future is not None:
            if transport is None:
                self.connect_future.set_exception(
                    ValueError("transport must not be None"))

            else:
                self.connect_future.set_result(self)

        assert not self.connected
        assert self.transport is None
        assert self.exception is None
        assert not self.paused
        assert not self.received

        assert transport is not None

        self.connected = True
        self.transport = transport

    def connection_lost(self, exc: Optional[BaseException]) -> None:

        if self.disconnect_future is not None:
            if exc is None:
                self.disconnect_future.set_result(self)

            else:
                self.disconnect_future.set_exception(exc)

        assert self.connected
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.connected = False
        self.exception = exc

    def pause_writing(self) -> None:

        assert self.connected
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.paused = True

    def resume_writing(self) -> None:

        assert self.connected
        assert self.transport is not None
        assert self.exception is None
        assert self.paused

        self.paused = False

    def data_received(self, data) -> None:

        assert self.connected
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.received.append(data)

    def eof_received(self) -> None:

        assert self.connected
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.received.append(self.EOF)


class Output(io.FileIO):

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:

        self.EOF = object()
        self.received = []

        self._loop = loop

        self._fd_read, _fd_write = os.pipe()
        os.set_blocking(self._fd_read, False)
        os.set_blocking(_fd_write, False)

        super().__init__(_fd_write, mode='w')

        import sys
        print(f"#{_fd_write}: closefd = {self.closefd}", file=sys.stderr)

        class _Protocol(asyncio.Protocol):

            def __init__(self, output: Output):

                self._output = output

            def data_received(self, data):

                self._output.received.append(data)

            def eof_received(self):

                self._output.received.append(self._output.EOF)

        self._loop.connect_read_pipe(partial(_Protocol, self), self._fd_read)

    def close(self) -> None:

        if self.closed:
            return

        super().close()

        # FIXME: read remaining data
        os.close(self._fd_read)

    # def write(self, b: bytes) -> int:
    #
    #     self._check_open()
    #
    #     if not b:
    #         return 0
    #
    #     try:
    #         return os.write(self._fd_write, b)
    #
    #     except BlockingIOError:
    #         return None
