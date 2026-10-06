import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from servership.keys import prepare_key, verify_access
from servership.models import KeyPair, Server


def fake_generate(args, **kwargs):
    if '-f' in args:
        path = Path(args[args.index('-f') + 1])
        path.write_text('fixture private')
        path.with_name(path.name + '.pub').write_text('ssh-ed25519 AAAA fixture\n')
        return subprocess.CompletedProcess(args, 0)
    return subprocess.CompletedProcess(args, 0, stdout='ssh-ed25519 AAAA fixture\n')


def test_generate_no_overwrite(tmp_path):
    path = tmp_path / 'key with space'
    with patch('servership.keys.subprocess.run', side_effect=fake_generate):
        pair = prepare_key('generate', path)
        assert pair.private_path == path
        assert path.stat().st_mode & 0o777 == 0o600
        before = path.read_bytes()
        with pytest.raises(ValueError):
            prepare_key('generate', path)
        assert path.read_bytes() == before


def test_real_ed25519_reuse_derives_public_key(tmp_path):
    path = tmp_path / 'key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(path)], check=True)
    path.with_name(path.name + '.pub').write_text('stale .pub')
    pair = prepare_key('reuse', path)
    assert pair.public_key.startswith('ssh-ed25519 ')
    assert path.with_name(path.name + '.pub').read_text() == 'stale .pub'


def test_symlink_rejected(tmp_path):
    original = tmp_path / 'original'
    original.write_text('untouched')
    link = tmp_path / 'link'
    link.symlink_to(original)
    with pytest.raises(ValueError):
        prepare_key('reuse', link)
    assert original.read_text() == 'untouched'


def test_publickey_only_verification():
    with patch('servership.keys.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
        result = verify_access(Server('x', 'localhost'), KeyPair(Path('/tmp/key'), 'ssh-ed25519 AAAA'))
        assert result.status == 'success'
        args = run.call_args.args[0]
        for option in ['PreferredAuthentications=publickey', 'PasswordAuthentication=no', 'KbdInteractiveAuthentication=no', 'IdentitiesOnly=yes']:
            assert option in args
        assert 'BatchMode=yes' not in args


def test_key_failure_not_printed(tmp_path, capsys):
    path = tmp_path / 'key'
    path.write_text('SECRET_PRIVATE_CONTENT')
    os.chmod(path, 0o600)
    with patch('servership.keys.subprocess.run', return_value=subprocess.CompletedProcess([], 1, stdout='')):
        with pytest.raises(ValueError):
            prepare_key('reuse', path)
    assert 'SECRET_PRIVATE_CONTENT' not in str(capsys.readouterr())
