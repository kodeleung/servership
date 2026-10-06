from pathlib import Path
from unittest.mock import patch

from servership.cli import main
from servership.models import Server


def test_empty_server_selection_no_key_or_connection():
    with patch('servership.cli.check_environment'), patch('servership.cli.load_inventory', return_value=[Server('one', 'localhost')]), patch('servership.cli.select_servers', return_value=[]), patch('servership.cli.prepare_key') as key, patch('servership.cli.run_batch') as batch:
        assert main([]) == 0
        key.assert_not_called()
        batch.assert_not_called()


def test_invalid_inventory_no_connection(tmp_path):
    config = tmp_path / 'bad.yaml'
    config.write_text('servers: []')
    with patch('servership.cli.check_environment'), patch('servership.cli.select_servers') as select, patch('servership.cli.run_batch') as batch:
        assert main(['--inventory', str(config)]) == 1
        select.assert_not_called()
        batch.assert_not_called()
