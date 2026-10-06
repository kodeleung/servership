from pathlib import Path
from unittest.mock import patch

import pytest

from servership.cli import main
from servership.models import Server


def test_empty_server_selection_no_key_or_connection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'servers.yaml').write_text('servers: [{name: one, host: localhost}]')
    with patch('servership.cli.check_environment'), patch('servership.cli.load_inventory', return_value=[Server('one', 'localhost')]), patch('servership.cli.select_servers', return_value=[]), patch('servership.cli.prepare_key') as key, patch('servership.cli.run_batch') as batch:
        assert main([]) == 0
        key.assert_not_called()
        batch.assert_not_called()


@pytest.mark.parametrize('filenames,expected', [
    (['servers.yaml'], 'servers.yaml'),
    (['servers.yml'], 'servers.yml'),
    (['servers.yaml', 'servers.yml'], 'servers.yaml'),
])
def test_default_inventory_discovery(tmp_path, monkeypatch, filenames, expected):
    monkeypatch.chdir(tmp_path)
    for filename in filenames:
        (tmp_path / filename).write_text('servers: [{name: one, host: localhost}]')
    with patch('servership.cli.check_environment'), patch('servership.cli.load_inventory', return_value=[Server('one', 'localhost')]) as load, patch('servership.cli.select_servers', return_value=[]):
        assert main([]) == 0
        load.assert_called_once_with(tmp_path / expected)


def test_explicit_inventory_overrides_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'servers.yaml').write_text('servers: []')
    custom = tmp_path / 'custom.yml'
    custom.write_text('servers: [{name: custom, host: localhost}]')
    with patch('servership.cli.check_environment'), patch('servership.cli.select_servers', return_value=[]) as select:
        assert main(['--inventory', str(custom)]) == 0
        assert select.call_args.args[0][0].name == 'custom'


def test_missing_default_inventory_reports_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with patch('servership.cli.check_environment'), patch('servership.cli.select_servers') as select:
        assert main([]) == 1
        select.assert_not_called()
    assert 'Create servers.yaml or servers.yml, or specify --inventory PATH.' in capsys.readouterr().err


def test_invalid_yaml_does_not_fall_back_to_yml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'servers.yaml').write_text('servers: []')
    (tmp_path / 'servers.yml').write_text('servers: [{name: fallback, host: localhost}]')
    with patch('servership.cli.check_environment'), patch('servership.cli.select_servers') as select:
        assert main([]) == 1
        select.assert_not_called()


def test_invalid_inventory_no_connection(tmp_path):
    config = tmp_path / 'bad.yaml'
    config.write_text('servers: []')
    with patch('servership.cli.check_environment'), patch('servership.cli.select_servers') as select, patch('servership.cli.run_batch') as batch:
        assert main(['--inventory', str(config)]) == 1
        select.assert_not_called()
        batch.assert_not_called()
