import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src/servership/remote'
TARGET = 2 * 1024 * 1024 * 1024


def run_swap(tmp_path, *, swaps_body='Filename\tType\tSize\tUsed\tPriority\n', fstab_body='# fstab\n',
             create_swapfile_size=None, fallocate_ok=True):
    work = tmp_path / 'work'
    work.mkdir()
    swaps = work / 'swaps'
    fstab = work / 'fstab'
    path = work / 'swapfile'
    swaps.write_text(swaps_body)
    fstab.write_text(fstab_body)
    if create_swapfile_size is not None:
        path.write_bytes(b'\0' * create_swapfile_size)

    tools = tmp_path / 'bin'
    tools.mkdir()
    calls = tmp_path / 'calls'
    size_file = work / 'reported-size'
    # Avoid allocating a real 2G file in tests; report the expected size via a stub.
    size_file.write_text(str(create_swapfile_size if create_swapfile_size is not None else TARGET))

    fallocate_body = (
        f'echo fallocate "$@" >> "{calls}"; : > "$4"; echo {TARGET} > "{size_file}"'
        if fallocate_ok else
        f'echo fallocate "$@" >> "{calls}"; exit 1'
    )
    for name, body in {
        'mkswap': f'echo mkswap "$@" >> "{calls}"',
        'swapon': f'echo swapon "$@" >> "{calls}"',
        'fallocate': fallocate_body,
        'dd': f'echo dd "$@" >> "{calls}"; : > "$of"; echo {TARGET} > "{size_file}"',
        'df': 'printf "Avail\\n999999999999\\n"',
        'stat': f'if [ "$1" = -c%s ]; then cat "{size_file}"; else command -p stat "$@"; fi',
    }.items():
        tool = tools / name
        # dd receives of=PATH as an operand; expand it for the stub.
        if name == 'dd':
            body = f'for arg; do case $arg in of=*) of=${{arg#of=}};; esac; done\n{body}'
        tool.write_text('#!/bin/sh\n' + body + '\n')
        tool.chmod(0o755)

    script = f'''
set -euo pipefail
source "{ROOT}/swap.sh" --source-only
require_root() {{ :; }}
configure_swap "{path}" "{fstab}" "{swaps}"
'''
    env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'])
    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
    return result, path, fstab, calls.read_text() if calls.exists() else ''


def test_existing_sufficient_swap_skips(tmp_path):
    # 2GiB reported in /proc/swaps KiB units.
    body = 'Filename\tType\tSize\tUsed\tPriority\n/dev/sda2\tpartition\t2097152\t0\t-2\n'
    result, path, fstab, calls = run_swap(tmp_path, swaps_body=body)
    assert result.returncode == 10
    assert not path.exists()
    assert calls == ''
    assert fstab.read_text() == '# fstab\n'


def test_creates_swapfile_and_fstab(tmp_path):
    result, path, fstab, calls = run_swap(tmp_path)
    assert result.returncode == 0, result.stderr
    assert path.exists()
    assert oct(path.stat().st_mode & 0o777) == '0o600'
    assert f'{path} none swap sw 0 0' in fstab.read_text()
    assert 'mkswap' in calls and 'swapon' in calls and 'fallocate' in calls


def test_wrong_size_existing_swapfile_preserved(tmp_path):
    result, path, fstab, calls = run_swap(tmp_path, create_swapfile_size=1024)
    assert result.returncode != 0
    assert path.stat().st_size == 1024
    assert 'mkswap' not in calls and 'swapon' not in calls
    assert 'preserving' in result.stderr
