"""Optional real-terminal verification; requires gum on PATH."""
import fcntl
import os
import pty
import select
import shutil
import struct
import subprocess
import termios
import time

import pytest


@pytest.mark.skipif(shutil.which('gum') is None, reason='gum not installed')
@pytest.mark.parametrize('keys,expected,cancel', [
    (b'\r', [], False),
    (b' \r', ['caddy'], False),
    (b' \x1b[B \r', ['caddy', 'docker'], False),
    (b'\x01\r', ['caddy', 'docker', 'sing-box', 'openssh'], False),
    (b'\x01\x01\r', [], False),
    (b'\x1b', [], True),
])
def test_real_gum_keys(keys, expected, cancel):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 100, 0, 0))
    def terminal():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    process = subprocess.Popen(['gum', 'choose', '--no-limit', '--', 'caddy', 'docker', 'sing-box', 'openssh'], stdin=slave, stdout=subprocess.PIPE, stderr=slave, preexec_fn=terminal, env=dict(os.environ, TERM='xterm-256color'))
    os.close(slave)
    try:
        screen = b''
        deadline = time.monotonic() + 10
        while b'openssh' not in screen:
            assert time.monotonic() < deadline, 'gum did not render'
            if select.select([master], [], [], 0.1)[0]:
                screen += os.read(master, 65536)
        os.write(master, keys)
        output, _ = process.communicate(timeout=10)
        assert [line for line in output.decode().splitlines() if line] == expected
        assert (process.returncode != 0) == cancel
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
