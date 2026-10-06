import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .batch import BatchCancelled, run_batch
from .inventory import load_inventory
from .keys import prepare_key
from .models import UserCancelled
from .ui import choose_key, select_servers, select_software

LABELS = {'success': 'Success', 'skipped': 'Already satisfied / skipped', 'failed': 'Failed', 'not_run': 'Not run'}


def check_environment():
    if os.geteuid() == 0:
        raise RuntimeError('Run locally as a regular user; server privileges are obtained through SSH/sudo')
    missing = [tool for tool in ['ssh', 'scp', 'ssh-keygen', 'gum'] if shutil.which(tool) is None]
    if missing:
        raise RuntimeError('Missing local tools: ' + ', '.join(missing) + '. Install OpenSSH with your system package manager; for gum see https://github.com/charmbracelet/gum')
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError('Run in an interactive terminal; SSH, sudo, and checkboxes require terminal input')


def summary(results):
    print('\nResults:')
    for result in results:
        print(f'\n{result.server.name} ({result.server.host})')
        for step in result.steps:
            print(f'  {step.stage}: {LABELS[step.status]} — {step.detail}')


def resolve_inventory(path: Path | None) -> Path:
    if path is not None:
        return path
    for name in ('servers.yaml', 'servers.yml'):
        candidate = Path.cwd() / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        'No inventory found in the current directory. '
        'Create servers.yaml or servers.yml, or specify --inventory PATH.'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Initialize Debian / Ubuntu servers in batches from your computer')
    parser.add_argument('--inventory', type=Path, help='YAML inventory (default: servers.yaml, then servers.yml in the current directory)')
    args = parser.parse_args(argv)
    try:
        check_environment()
        servers = load_inventory(resolve_inventory(args.inventory))
        selected = select_servers(servers)
        if not selected:
            print('No servers selected. Exiting.')
            return 0
        software = select_software()
        mode, path = choose_key(Path.home() / '.ssh/servership_ed25519')
        key = prepare_key(mode, path)
        print('\nExecution summary:')
        for server in selected:
            print(f'  {server.name}: {server.user}@{server.host}:{server.port}')
        print('Software: ' + (', '.join(software) if software else 'No software installation; configure the SSH public key only'))
        print(f'Local private key: {key.private_path} (kept locally)', flush=True)
        results = run_batch(selected, software, key)
        summary(results)
        return 1 if any(step.status == 'failed' for result in results for step in result.steps) else 0
    except BatchCancelled as exc:
        summary(exc.results)
        print('\nBatch cancelled; completed authorization and installations are preserved.', file=sys.stderr)
        return 130
    except (KeyboardInterrupt, UserCancelled):
        print('\nCancelled.', file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
