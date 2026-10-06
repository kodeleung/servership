from pathlib import Path

import pytest

from servership.inventory import InventoryError, load_inventory


def write(tmp_path, text):
    path = tmp_path / 'servers.yaml'
    path.write_text(text)
    return path


def test_defaults_and_overrides(tmp_path):
    servers = load_inventory(write(tmp_path, '''defaults: {user: ubuntu, port: 2222}
servers:
  - {name: one, host: '2001:db8::1'}
  - {name: two, host: example.com, user: root, port: 22}
'''))
    assert [(s.user, s.port) for s in servers] == [('ubuntu', 2222), ('root', 22)]


@pytest.mark.parametrize('text', [
    'servers: []',
    'servers: [{name: x, host: localhost, port: true}]',
    'servers: [{name: x, host: localhost, port: 65536}]',
    'servers: [{name: x, host: localhost, user: "-root"}]',
    'servers: [{name: x, host: "-oProxyCommand=x"}]',
    'servers: [{name: x, host: localhost, password: secret}]',
    'servers: [{name: x, host: localhost}, {name: x, host: other}]',
    'servers: [{name: x, host: localhost, host: other}]',
    'servers: !!python/object/apply:os.system ["touch SHOULD_NOT_EXIST"]',
    'defaults: {identity_file: key}\nservers: [{name: x, host: localhost}]',
])
def test_reject_invalid_inventory(tmp_path, text):
    with pytest.raises(InventoryError):
        load_inventory(write(tmp_path, text))


def test_identity_paths(tmp_path, monkeypatch):
    key = tmp_path / 'my key'
    key.write_text('test fixture')
    monkeypatch.setenv('HOME', str(tmp_path))
    for spelling in ['my key', '~/my key']:
        server = load_inventory(write(tmp_path, f'servers: [{{name: x, host: localhost, identity_file: "{spelling}"}}]'))[0]
        assert server.identity_file == key


def test_missing_identity_error_context(tmp_path):
    with pytest.raises(InventoryError, match='x.*identity_file'):
        load_inventory(write(tmp_path, 'servers: [{name: x, host: localhost, identity_file: missing}]'))
