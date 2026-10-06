import shlex
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from servership.models import KeyPair, Server, UserCancelled
from servership.ssh import SSHClient


def test_sudo_denial_no_stage():
    client = SSHClient(Server('one', 'example.com', user='ubuntu'))
    with patch('servership.ssh.subprocess.run', return_value=subprocess.CompletedProcess([], 1)) as run:
        assert client.preflight().status == 'failed'
        with pytest.raises(RuntimeError):
            client.stage('ssh-ed25519 AAAA test')
        assert run.call_count == 1


def test_root_bypasses_sudo_and_nonroot_uses_sudo():
    for user in ('root', 'ubuntu'):
        client = SSHClient(Server('one', 'example.com', user=user))
        with patch('servership.ssh.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
            assert client.preflight().status == 'success'
            command = run.call_args.args[0][-1]
            assert ('sudo' in shlex.split(command)) == (user != 'root')


def test_ipv6_and_identity_arguments():
    client = SSHClient(Server('one', '2001:db8::1', 2222, 'ubuntu', Path('/tmp/key with space')))
    args = client.ssh_args()
    assert args[args.index('-p') + 1] == '2222'
    assert args[args.index('-i') + 1] == '/tmp/key with space'
    assert client.scp_target('/tmp/a') == 'ubuntu@[2001:db8::1]:/tmp/a'


def test_remote_arguments_quoted_and_privilege_rechecked():
    client = SSHClient(Server('one', 'localhost', user='ubuntu'))
    client.workdir = '/tmp/servership.ABC12345'
    values = ['a b', "a'b", '$(touch x); false']
    with patch('servership.ssh.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
        client.run_root('authorize.sh', values)
        remote = shlex.split(run.call_args.args[0][-1])
        assert remote[:3] == ['sudo', '--', 'bash']
        assert remote[-3:] == values
        assert '-tt' in run.call_args.args[0]


def test_cleanup_rejects_unregistered_path():
    client = SSHClient(Server('one', 'localhost'))
    client.workdir = '/tmp/../../etc'
    with patch('servership.ssh.subprocess.run') as run:
        assert client.cleanup().status == 'failed'
        run.assert_not_called()


def test_reports_reject_invalid_and_duplicate_status(tmp_path):
    client = SSHClient(Server('one', 'localhost'))
    client.workdir = '/tmp/servership.ABC12345'
    def download(args, **kwargs):
        Path(args[-1]).write_text('docker\tsuccess\tok\ndocker\tsuccess\tok\n')
        return subprocess.CompletedProcess(args, 0)
    with patch('servership.ssh.subprocess.run', side_effect=download):
        with pytest.raises(ValueError):
            client.fetch_results()


def test_remote_cancel_code_propagates():
    client = SSHClient(Server('one', 'localhost'))
    client.workdir = '/tmp/servership.ABC12345'
    with patch('servership.ssh.subprocess.run', return_value=subprocess.CompletedProcess([], 130)):
        with pytest.raises(UserCancelled):
            client.run_root('install.sh', [])


def test_use_key_isolates_identities_and_control_socket(tmp_path):
    keyfile = tmp_path / 'private with space'
    keyfile.write_text('fixture')
    client = SSHClient(Server('one', 'example.com'))
    effective = 'hostname example.com\nproxyjump bastion\nidentityfile /tmp/other\ncontrolmaster auto\ncontrolpath /tmp/master\n'
    with patch('servership.ssh.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stdout=effective)):
        client.use_key(KeyPair(keyfile, 'ssh-ed25519 AAAA fixture'))
        config = client.config_path.read_text()
        assert '/tmp/other' not in config
        assert '/tmp/master' not in config
        assert 'ControlPath none' in config and 'ControlMaster no' in config
        assert 'proxyjump bastion' in config
        assert client.identity != keyfile
        assert client.identity.with_name(client.identity.name + '.pub').read_text().strip() == 'ssh-ed25519 AAAA fixture'
    client.close()
