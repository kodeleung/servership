from pathlib import Path
from unittest.mock import patch

import pytest

from servership.batch import BatchCancelled, run_batch
from servership.models import KeyPair, Server, StepResult

KEY = KeyPair(Path('/tmp/local-key'), 'ssh-ed25519 fixture')


class FakeClient:
    instances = []
    def __init__(self, server):
        self.server = server
        self.identity = None
        self.workdir = '/tmp/servership.ABC12345'
        self.calls = []
        self.instances.append(self)

    def preflight(self):
        self.calls.append('preflight')
        return StepResult('preflight', 'failed' if self.server.name == 'bad' else 'success')

    def run_root(self, script, args):
        self.calls.append(script)
        return 0

    def fetch_results(self):
        return [StepResult('docker', 'success', 'ok')]

    def cleanup(self):
        self.calls.append('cleanup')
        return StepResult('cleanup', 'success')

    def use_key(self, key):
        self.identity = key.private_path

    def close(self):
        pass


@pytest.fixture(autouse=True)
def clear():
    FakeClient.instances = []


def authorized(client, key):
    client.calls.append('authorize')
    return StepResult('authorize', 'success')


def test_one_host_failure_next_continues():
    with patch('servership.batch.SSHClient', FakeClient), patch('servership.batch.authorize', authorized), patch('servership.batch.verify_access', return_value=StepResult('verify', 'success')):
        results = run_batch([Server('bad', 'localhost'), Server('good', 'localhost')], ['docker'], KEY)
    assert [r.server.name for r in results] == ['bad', 'good']
    assert FakeClient.instances[0].calls == ['preflight', 'cleanup']
    assert FakeClient.instances[1].calls == ['preflight', 'authorize', 'install.sh', 'cleanup']
    assert any(s.stage == 'docker' and s.status == 'not_run' for s in results[0].steps)


def test_publickey_failure_no_install():
    with patch('servership.batch.SSHClient', FakeClient), patch('servership.batch.authorize', authorized), patch('servership.batch.verify_access', return_value=StepResult('verify', 'failed')):
        results = run_batch([Server('good', 'localhost')], ['docker'], KEY)
    assert 'install.sh' not in FakeClient.instances[0].calls
    assert any(s.stage == 'verify' and s.status == 'failed' for s in results[0].steps)


def test_empty_software_still_authorizes():
    with patch('servership.batch.SSHClient', FakeClient), patch('servership.batch.authorize', authorized), patch('servership.batch.verify_access', return_value=StepResult('verify', 'success')):
        run_batch([Server('good', 'localhost')], [], KEY)
    assert FakeClient.instances[0].calls == ['preflight', 'authorize', 'cleanup']


def test_missing_report_is_failure():
    with patch('servership.batch.SSHClient', FakeClient), patch('servership.batch.authorize', authorized), patch('servership.batch.verify_access', return_value=StepResult('verify', 'success')), patch.object(FakeClient, 'fetch_results', return_value=[]):
        results = run_batch([Server('good', 'localhost')], ['docker'], KEY)
    assert any(s.status == 'failed' for s in results[0].steps)


def test_cancel_marks_remaining_not_run():
    with patch('servership.batch.SSHClient', FakeClient), patch('servership.batch.authorize', side_effect=KeyboardInterrupt):
        with pytest.raises(BatchCancelled) as exc:
            run_batch([Server('good', 'localhost'), Server('later', 'localhost')], ['docker'], KEY)
    assert len(FakeClient.instances) == 1
    assert len(exc.value.results) == 2
    assert all(step.status == 'not_run' for step in exc.value.results[1].steps)


def test_cancel_during_failed_host_cleanup_stops_batch():
    with patch('servership.batch.SSHClient', FakeClient), patch.object(FakeClient, 'cleanup', side_effect=KeyboardInterrupt):
        with pytest.raises(BatchCancelled):
            run_batch([Server('bad', 'localhost'), Server('later', 'localhost')], ['docker'], KEY)
    assert len(FakeClient.instances) == 1


def test_partial_report_preserves_completed_items():
    with patch('servership.batch.SSHClient', FakeClient), patch('servership.batch.authorize', authorized), patch('servership.batch.verify_access', return_value=StepResult('verify', 'success')), patch.object(FakeClient, 'fetch_results', return_value=[StepResult('caddy', 'success')]):
        results = run_batch([Server('good', 'localhost')], ['caddy', 'docker'], KEY)
    assert any(s.stage == 'caddy' and s.status == 'success' for s in results[0].steps)
