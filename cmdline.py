#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Tuple

import blessed
import codecs
import fcntl
import io
import os
import termios

from asyncio import (
    AbstractEventLoop,
    BaseProtocol,
    BaseTransport,
    Protocol,
    Transport,
    get_event_loop,
)

from asyncio.coroutines import coroutine

from collections import deque


def _debug_fileno(filelike):

    try:
        fileno = filelike.fileno()

    except (AttributeError, OSError):
        return None

    return fileno


def _debug_cls(cls):
    return f"{cls.__module__}.{cls.__name__}"


def _debug_mro(obj):
    return ", ".join(_debug_cls(cls) for cls in obj.__class__.__mro__)


def _accmode(mode: str) -> int:

    flags = 0

    for i, c in enumerate('rwxa+'):
        if c in mode:
            flags |= 1 << i

    try:
        return {
            0b00001: os.O_RDONLY,
            0b00010: os.O_WRONLY,
            0b00100: os.O_WRONLY,
            0b01000: os.O_WRONLY,
            0b10001: os.O_RDWR,
            0b10010: os.O_RDWR,
            0b10100: os.O_RDWR,
            0b11000: os.O_RDWR,
        }[flags]

    except KeyError:
        raise ValueError(f"invalid mode {mode!r}")


class _File:

    def __init__(
            self, filelike: io.IOBase,
            mode: str = None,
            encoding: str = None,
            non_blocking: bool = False,
    ) -> None:

        if not isinstance(filelike, io.IOBase):
            raise TypeError("must be a file-like object")

        filelike = self._maybe_text(filelike)
        filelike = self._maybe_bytes(filelike)
        self._maybe_raw(filelike)
        self._maybe_fd(filelike)

        try:
            self.isatty = filelike.isatty()

        except AttributeError:
            self.isatty = os.isatty(self.fd) if self.fd is not None else False

        self.encoding = None

        self._determine_encoding(encoding)

        if non_blocking and self.fd is not None and os.get_blocking(self.fd):
            os.set_blocking(self.fd, False)

        mode, accmode = self._determine_mode(mode)

        mode, accmode = self._maybe_raw_from_fd(mode, accmode)
        mode, accmode = self._maybe_bytes_from_raw(mode, accmode)
        self._maybe_text_from_bytes(mode, accmode)

    def _maybe_text(self, filelike: io.IOBase) -> io.IOBase:

        if (isinstance(filelike, io.TextIOBase) or
                hasattr(filelike, 'encoding')):

            self.text = filelike

            try:
                filelike = filelike.buffer

            except AttributeError:
                try:
                    # noinspection PyUnresolvedReferences
                    filelike = filelike.raw

                except AttributeError:
                    pass

        else:
            self.text = None

        return filelike

    def _maybe_bytes(self, filelike: io.IOBase) -> io.IOBase:

        if (isinstance(filelike, io.BufferedIOBase) or
                hasattr(filelike, 'read1') or
                (not hasattr(filelike, 'encoding') and
                     hasattr(filelike, 'detach'))):

            self.bytes = filelike

            try:
                # noinspection PyUnresolvedReferences
                filelike = filelike.raw

            except AttributeError:
                pass

        else:
            self.bytes = None

        return filelike

    def _maybe_raw(self, filelike: io.IOBase) -> None:

        if (isinstance(filelike, io.RawIOBase) or
                not hasattr(filelike, 'detach')):

            self.raw = filelike

        else:
            self.raw = None

    def _maybe_fd(self, filelike: io.IOBase) -> None:

        try:
            self.fd = filelike.fileno()

        except (AttributeError, OSError):
            self.fd = None

    def _determine_encoding(self, encoding: Optional[str]) -> None:

        self.encoding = encoding

        if self.encoding is None and self.text is not None:
            self.encoding = self.text.encoding

        if self.encoding is None and self.fd is not None:
            self.encoding = os.device_encoding(self.fd)

        if self.encoding is None:
            self.encoding = 'utf-8'

    def _determine_mode(self, mode: Optional[str]) -> Tuple[str, int]:

        if mode is None:
            accmode = (os.O_RDWR if self.fd is None
                       else fcntl.fcntl(self.fd, fcntl.F_GETFL) & os.O_ACCMODE)
            mode = ('rb', 'wb', 'r+b')[accmode]

        else:
            accmode = _accmode(mode)
            if 'b' not in mode:
                mode += 'b'

        return mode, accmode

    def _maybe_raw_from_fd(self, mode: str, accmode: int) -> Tuple[str, int]:

        if self.fd is not None:
            # noinspection PyUnresolvedReferences
            if (self.raw is None or
                    not hasattr(self.raw, 'mode') or
                    _accmode(self.raw.mode) != accmode):

                self.raw = io.open(self.fd,
                                   mode=mode,
                                   buffering=0,
                                   closefd=False,
                                   opener=lambda path, flags: self.fd)

        elif self.raw is not None:
            try:
                # noinspection PyUnresolvedReferences
                mode = self.raw.mode

            except AttributeError:
                pass

            else:
                accmode = _accmode(mode)

        return mode, accmode

    def _maybe_bytes_from_raw(self, mode: str, accmode: int) -> Tuple[str,
                                                                      int]:

        if self.raw is not None:
            if (self.bytes is None or
                    not hasattr(self.bytes, 'mode') or
                    _accmode(self.bytes.mode) != accmode):

                buffered_io = (
                    io.BufferedReader,
                    io.BufferedWriter,
                    io.BufferedRandom,
                )[accmode]

                if accmode == os.O_RDWR and not self.raw.seekable():
                    self.bytes = io.BufferedRWPair(self.raw, self.raw)
                else:
                    self.bytes = buffered_io(self.raw)

        elif self.bytes is not None:
            try:
                mode = self.bytes.mode

            except AttributeError:
                pass

            else:
                accmode = _accmode(mode)

        return mode, accmode

    def _maybe_text_from_bytes(self, mode: str, accmode: int) -> Tuple[str,
                                                                       int]:

        if self.bytes is not None:
            # noinspection PyUnresolvedReferences
            if (self.text is None or
                    not hasattr(self.text, 'mode') or
                    _accmode(self.text.mode) != accmode):

                self.text = io.TextIOWrapper(
                        self.bytes,
                        encoding=self.encoding,
                        errors='replace' if self.isatty else 'strict',
                        line_buffering=True,
                )

        elif self.text is not None:
            try:
                # noinspection PyUnresolvedReferences
                mode = self.text.mode

            except AttributeError:
                pass

            else:
                accmode = _accmode(mode)

        return mode, accmode

    def __eq__(self, other: '_File') -> bool:

        if other is self:
            return True

        if not isinstance(other, _File):
            return NotImplemented

        if self.text is not None and other.text is self.text:
            return True

        if self.bytes is not None and other.bytes is self.bytes:
            return True

        if self.raw is not None and other.raw is self.raw:
            return True

        if self.fd is None or other.fd is None:
            return False

        if other.fd == self.fd:
            return True

        stat1 = os.fstat(self.fd)
        stat2 = os.fstat(other.fd)

        return stat1.st_dev == stat2.st_dev and stat1.st_ino == stat2.st_ino

    def tty_file(self, mode='w+') -> io.TextIOWrapper:

        if not self.isatty:
            raise TypeError("must be a tty")

        if self.fd is None:
            raise TypeError("must have a file descriptor")

        return open(os.ttyname(self.fd),
                    mode=mode,
                    encoding=self.encoding,
                    errors='replace')


class _CmdLineTransport(Transport):

    def __init__(self, loop: AbstractEventLoop, protocol: Protocol) -> None:

        super().__init__()

        self._loop = loop
        self._protocol = protocol

        import sys
        self._input = _File(sys.__stdin__, mode='r', non_blocking=True)
        self._output = _File(sys.__stdout__, mode='w')

        self._input_decoder = codecs.getincrementaldecoder(self._input.encoding)(errors='ignore')
        self._input_buf = []

        self._output_encoder = codecs.getincrementalencoder(self._output.encoding)(errors='ignore')
        self._output_buf = deque()

        self._saved_attr = None
        self._terminal = None
        self._shared = False
        self._echo = None

        if self._input.isatty:
            self._saved_attr = termios.tcgetattr(self._input.fd)
            attr = termios.tcgetattr(self._input.fd)
            attr[3] &= ~termios.ICANON
            attr[6][termios.VMIN] = 1
            attr[6][termios.VTIME] = 0
            termios.tcsetattr(self._input.fd, termios.TCSADRAIN, attr)

            if self._input == self._output:
                self._terminal = blessed.Terminal()
                self._shared = True

            else:
                self._terminal = blessed.Terminal(
                        stream=self._input.tty_file(mode='w'),
                )

            self._echo = _File(self._terminal.stream, mode='w')

        self._loop.call_soon(self._protocol.connection_made, self)
        self._loop.call_soon(self._add_reader)

    def _add_reader(self) -> None:

        try:
            self._loop.add_reader(self._input.fd, self._input_available)

        except PermissionError:
            # FIXME: handle case when file descriptor cannot be watched
            pass

    def _add_writer(self) -> None:

        try:
            import sys
            print("adding writer", file=sys.stderr, flush=True)

            self._loop.add_writer(self._output.fd, self._output_available)

        except PermissionError:
            # FIXME: handle case when file descriptor cannot be watched

            import sys
            print("output file descriptor cannot be watched", file=sys.stderr, flush=True)

    def _input_available(self) -> None:

        raw_buf = os.read(self._input.fd, 4096)

        while True:
            raw_line, sep, raw_buf = raw_buf.partition(b'\n')

            if not sep:
                break

            self._input_buf.append(self._input_decoder.decode(raw_line, True))
            self._input_decoder.reset()

            self._loop.call_soon(self._protocol.data_received,
                                 ''.join(self._input_buf))
            self._input_buf.clear()

        if not raw_line:
            return

        self._input_buf.append(self._input_decoder.decode(raw_line, False))

    def _output_available(self) -> None:

        if not self._output_buf:
            self._loop.remove_writer(self._output.fd)

            import sys
            print("fsync", file=sys.stderr, flush=True)

            try:
                os.fsync(self._output.fd)

            except OSError:
                pass

            return

        raw_data = self._output_buf.popleft()
        if not raw_data:
            import sys
            print("data empty", file=sys.stderr, flush=True)

            return

        bytes_written = os.write(self._output.fd, raw_data[:4096])
        assert 0 <= bytes_written <= len(raw_data)

        if bytes_written >= len(raw_data):
            import sys
            print(f"complete write ({bytes_written})", file=sys.stderr, flush=True)

            return

        import sys
        print(f"incomplete write ({bytes_written})", file=sys.stderr, flush=True)

        self._output_buf.appendleft(raw_data[bytes_written:])

    def close(self) -> None:
        self._protocol = None

        if self._saved_attr:
            termios.tcsetattr(self._input.fd,
                              termios.TCSAFLUSH,
                              self._saved_attr)

    def is_closing(self) -> bool:
        return self._protocol is None

    def set_protocol(self, protocol: Protocol) -> None:
        self._protocol = protocol

    def get_protocol(self) -> Protocol:
        return self._protocol

    def get_write_buffer_size(self):
        assert False

    def set_write_buffer_limits(self, high=None, low=None):
        assert False

    def abort(self):
        assert False

    def can_write_eof(self) -> bool:
        return True

    def write_eof(self):

        raw_data = self._output_encoder.encode('', True)
        self._output_encoder.reset()

        if not raw_data:
            return

        self._output_buf.append(raw_data)
        self._add_writer()

    def write(self, data: str) -> None:

        raw_data = self._output_encoder.encode(data, True)
        self._output_encoder.reset()

        if not raw_data:
            return

        self._output_buf.append(raw_data)
        self._add_writer()

    def pause_reading(self):
        assert False

    def resume_reading(self):
        assert False


@coroutine
def connect_console(protocol_factory, loop: AbstractEventLoop) -> Tuple[
    BaseTransport,
    Protocol,
]:

    transport = _CmdLineTransport(loop=loop, protocol=protocol_factory())
    return transport, transport.get_protocol()


def _main():
    loop = get_event_loop()

    class _DebugProtocol(Protocol):

        def __init__(self) -> None:
            self._transport = None

        def connection_made(self, transport: BaseTransport) -> None:
            assert self._transport is None

            self._transport = transport

        def connection_lost(self, exc: BaseException) -> None:
            assert self._transport is not None

            self._transport = None

        def data_received(self, data: str) -> None:
            self._transport.write(f"{data!r}\n")

        def eof_received(self) -> None:
            self._transport.write_eof()

    connector_coroutine = connect_console(_DebugProtocol, loop=loop)

    transport, protocol = loop.run_until_complete(connector_coroutine)

    try:
        loop.run_forever()

    finally:
        transport.close()


if __name__ == '__main__':
    _main()
