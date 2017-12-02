#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest import TestCase, main

import asyncio

from functools import partial
from io import StringIO

from . import state_recording

from .context import asyncio_cmdline


class TestDumbOutput(TestCase):

    def setUp(self):
        import sys

        self.loop = asyncio.new_event_loop()
        self.recorded_output = state_recording.Output(loop=self.loop)
        self._file = asyncio_cmdline._File(self.recorded_output, mode='w')
        self.connect_future = self.loop.create_future()
        self.disconnect_future = self.loop.create_future()

        self.output = asyncio_cmdline.DumbOutput(
                partial(state_recording.Protocol,
                        connect=self.connect_future,
                        disconnect=self.disconnect_future),
                self.loop,
                self._file,
        )

        self.output.open()
        self.loop.run_until_complete(self.connect_future)
        self.protocol = self.connect_future.result()
        assert self.output.get_protocol() is self.protocol

    def tearDown(self):

        if not self.output.is_closing():
            self.output.close()

        self.loop.run_until_complete(self.disconnect_future)
        assert self.disconnect_future.result() is self.protocol
        assert self.output.get_protocol() is None

        assert not self.protocol.connected
        assert self.protocol.transport is not None
        assert not self.protocol.paused

        if self.protocol.exception is not None:
            raise self.protocol.exception

        self.recorded_output.close()  # FIXME: should not be necessary

    def test_let_it_dangle(self):

        pass

    def test_close(self):

        self.output.close()

    def test_write(self):

        self.output.write("foobar\n")
        self.output.close()
        self.loop.run_until_complete(self.disconnect_future)

        self.recorded_output.close()
        self.assertEqual(''.join(self.recorded_output.received), "foobar\n")


if __name__ == '__main__':
    main()
