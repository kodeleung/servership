import os
import subprocess
from pathlib import Path

from .models import SOFTWARE, Server, UserCancelled

HINT = 'Up/Down: move · Space: toggle · Ctrl+A: select/deselect all · Enter: confirm · Esc: cancel'


def _choose(options: list[str], header: str, multiple: bool = True) -> list[str]:
    args = ['gum', 'choose', '--header', header, '--no-show-help']
    if multiple:
        args += ['--no-limit', '--selected-prefix', '[x] ', '--unselected-prefix', '[ ] ', '--cursor-prefix', '[ ] ']
    args += ['--', *options]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('GUM_CHOOSE_'):
            del env[key]
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, text=True, env=env)
    except KeyboardInterrupt as exc:
        raise UserCancelled from exc
    if result.returncode in (1, 130, -2):
        raise UserCancelled
    if result.returncode:
        raise RuntimeError(f'gum failed ({result.returncode})')
    selected = [line for line in result.stdout.splitlines() if line]
    if len(selected) != len(set(selected)) or any(item not in options for item in selected):
        raise ValueError('The interface returned an invalid selection')
    return [item for item in options if item in selected]


def select_servers(servers: list[Server]) -> list[Server]:
    labels = [f'{s.name} · {s.user}@{s.host}:{s.port}' for s in servers]
    chosen = _choose(labels, 'Select servers\n' + HINT)
    return [server for server, label in zip(servers, labels) if label in chosen]


def select_software() -> list[str]:
    return _choose(list(SOFTWARE), 'Select software (selecting none still configures the SSH public key)\n' + HINT)


def choose_key(default_path: Path) -> tuple[str, Path]:
    choices = {'Generate a new key': 'generate', 'Reuse an existing key': 'reuse'}
    chosen = _choose(list(choices), 'Select a local SSH key', multiple=False)
    if not chosen:
        raise UserCancelled
    try:
        raw = input(f'Key path [{default_path}]: ').strip()
    except (KeyboardInterrupt, EOFError) as exc:
        raise UserCancelled from exc
    if raw and any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise ValueError('The key path cannot contain control characters')
    return choices[chosen[0]], Path(raw or default_path).expanduser().absolute()
