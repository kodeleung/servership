import subprocess
from unittest.mock import patch

import pytest

from servership.models import Server, UserCancelled
from servership.ui import select_servers, select_software


def result(out='', code=0):
    return subprocess.CompletedProcess([], code, stdout=out)


def test_empty_choices():
    with patch('servership.ui.subprocess.run', return_value=result()):
        assert select_servers([Server('a', 'localhost')]) == []
        assert select_software() == []


def test_server_selection_preserves_inventory_order():
    servers = [Server('a', 'localhost'), Server('b', 'example.com')]
    with patch('servership.ui.subprocess.run', return_value=result('b · root@example.com:22\na · root@localhost:22\n')):
        assert select_servers(servers) == servers


@pytest.mark.parametrize('code', [1, 130])
def test_cancel_is_not_empty(code):
    with patch('servership.ui.subprocess.run', return_value=result(code=code)):
        with pytest.raises(UserCancelled):
            select_software()


def test_unknown_choice_rejected():
    with patch('servership.ui.subprocess.run', return_value=result('unknown\n')):
        with pytest.raises(ValueError):
            select_software()


def test_checkbox_arguments():
    with patch('servership.ui.subprocess.run', return_value=result()) as run:
        select_software()
        argv = run.call_args.args[0]
        assert '--no-limit' in argv
        assert '[x] ' in argv and '[ ] ' in argv
        assert run.call_args.kwargs.get('shell', False) is False
