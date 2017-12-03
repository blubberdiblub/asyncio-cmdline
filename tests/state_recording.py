#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Optional

import asyncio
import io
import os


class _ProtocolRecorder(asyncio.Protocol):

    (
        STATE_UNCONNECTED,
        STATE_CONNECTED,
        STATE_DISCONNECTED,
    ) = range(3)

    def __init__(self,
                 connect: asyncio.Future = None,
                 disconnect: asyncio.Future = None,
                 *args, **kwargs) -> None:

        super().__init__(*args, **kwargs)

        class EOF:
            pass

        self.EOF = EOF()

        self.state = self.STATE_UNCONNECTED
        self.transport = None
        self.exception = None
        self.paused = False
        self.received = []

        self.connect = connect
        self.disconnect = disconnect

    def connection_made(self, transport: asyncio.BaseTransport) -> None:

        assert self.state == self.STATE_UNCONNECTED
        assert self.transport is None
        assert self.exception is None
        assert not self.paused
        assert not self.received

        self.state = self.STATE_CONNECTED
        self.transport = transport

        if transport is None:
            self.exception = ValueError("transport must not be None")

            if self.connect is not None:
                self.connect.set_exception(self.exception)

            if self.disconnect is not None:
                self.disconnect.cancel()

            raise self.exception

        if self.connect is None:
            return

        self.connect.set_result((transport, self))

    def connection_lost(self, exc: Optional[BaseException]) -> None:

        assert self.state == self.STATE_CONNECTED
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.state = self.STATE_DISCONNECTED
        self.exception = exc

        if self.disconnect is None:
            return

        if exc is None:
            self.disconnect.set_result(exc)

        else:
            self.disconnect.set_exception(exc)

    def pause_writing(self) -> None:

        assert self.state == self.STATE_CONNECTED
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.paused = True

    def resume_writing(self) -> None:

        assert self.state == self.STATE_CONNECTED
        assert self.transport is not None
        assert self.exception is None
        assert self.paused

        self.paused = False

    def data_received(self, data: bytes) -> None:

        assert self.state == self.STATE_CONNECTED
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.received.append(data)

    def eof_received(self) -> None:

        assert self.state == self.STATE_CONNECTED
        assert self.transport is not None
        assert self.exception is None
        assert not self.paused

        self.received.append(self.EOF)

    def is_eof_last_only(self) -> bool:

        try:
            return self.received.index(self.EOF) == len(self.received) - 1

        except ValueError:
            return False

    def data_sequence(self, idx: int) -> List[bytes]:

        start = 0

        for _ in range(idx):
            start = self.received.index(self.EOF, start) + 1

        try:
            stop = self.received.index(self.EOF, start)

        except ValueError:
            return self.received[start:]

        return self.received[start:stop]


class Protocol(_ProtocolRecorder):

    def __init__(self,
                 connect: asyncio.Future = None,
                 disconnect: asyncio.Future = None,
                 *args, **kwargs) -> None:

        super().__init__(connect=connect, disconnect=disconnect,
                         *args, **kwargs)


class Output(io.RawIOBase, _ProtocolRecorder):

    def __init__(self,
                 loop: asyncio.AbstractEventLoop,
                 *args, **kwargs) -> None:

        super().__init__(disconnect=loop.create_future(),
                         *args, **kwargs)

        self._loop = loop

        fd_read, fd_write = os.pipe()
        os.set_blocking(fd_read, False)
        os.set_blocking(fd_write, False)
        self._file_read = io.FileIO(fd_read, mode='r')
        self._file_write = io.FileIO(fd_write, mode='w')

        connect = self._loop.connect_read_pipe(lambda: self, self._file_read)
        transport, protocol = self._loop.run_until_complete(connect)

        import sys
        print(f"transport={transport!r}, protocol={protocol!r}", file=sys.stderr)

    def close(self) -> None:

        if self.closed:
            return

        super().close()
        assert self.closed

        self._file_write.close()

        assert self.disconnect is not None
        self._loop.run_until_complete(self.disconnect)
        assert self.disconnect.result() is None

        self._file_read.close()

    def fileno(self) -> int:

        self._checkClosed()
        return self._file_write.fileno()

    def flush(self) -> None:

        self._checkClosed()
        self._file_write.flush()

    def isatty(self) -> bool:

        self._checkClosed()
        return self._file_write.isatty()

    def writable(self) -> bool:

        self._checkClosed()
        return True

    def write(self, b: bytes) -> int:

        self._checkClosed()
        return self._file_write.write(b)

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
