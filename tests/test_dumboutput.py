#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest import TestCase, main

import asyncio

from functools import partial

from . import state_recording

from .context import asyncio_cmdline


class TestDumbOutput(TestCase):

    def setUp(self):

        self.old_loop = asyncio.get_event_loop()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
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
        transport, self.protocol = self.connect_future.result()
        assert self.output is transport
        assert self.output.get_protocol() is self.protocol

    def tearDown(self):

        if not self.output.is_closing():
            self.output.close()

        self.loop.run_until_complete(self.disconnect_future)
        assert self.disconnect_future.result() is None
        assert self.output.get_protocol() is None

        assert self.protocol.state == self.protocol.STATE_DISCONNECTED
        assert self.protocol.transport is not None
        assert not self.protocol.paused

        if self.protocol.exception is not None:
            raise self.protocol.exception

        self.recorded_output.close()  # FIXME: should not be necessary

        self.loop.close()
        asyncio.set_event_loop(self.old_loop)

    def test_let_it_dangle(self):

        pass

    def test_close(self):

        self.output.close()

    def test_write(self):

        self.output.write("foobar\n")
        self.output.write("blafasel")
        self.output.close()
        self.loop.run_until_complete(self.disconnect_future)

        self.recorded_output.close()
        self.assertTrue(self.recorded_output.is_eof_last_only())
        self.assertEqual(b''.join(self.recorded_output.data_sequence(0)),
                         b"foobar\nblafasel")


if __name__ == '__main__':
    main()
