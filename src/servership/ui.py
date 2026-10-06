import os
import subprocess
from pathlib import Path

from .models import SOFTWARE, Server, UserCancelled

HINT = '↑/↓ 移动 · Space 选择 · Ctrl+A 全选/取消全选 · Enter 确认 · Esc 取消'


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
        raise RuntimeError(f'gum 执行失败（{result.returncode}）')
    selected = result.stdout.splitlines()
    if len(selected) != len(set(selected)) or any(item not in options for item in selected):
        raise ValueError('界面返回了无效选择')
    return [item for item in options if item in selected]


def select_servers(servers: list[Server]) -> list[Server]:
    labels = [f'{s.name} · {s.user}@{s.host}:{s.port}' for s in servers]
    chosen = _choose(labels, '选择服务器\n' + HINT)
    return [server for server, label in zip(servers, labels) if label in chosen]


def select_software() -> list[str]:
    return _choose(list(SOFTWARE), '选择软件（全部不选仍会配置 SSH 公钥）\n' + HINT)


def choose_key(default_path: Path) -> tuple[str, Path]:
    choices = {'生成新密钥': 'generate', '复用已有密钥': 'reuse'}
    chosen = _choose(list(choices), '选择本机 SSH 密钥', multiple=False)
    if not chosen:
        raise UserCancelled
    try:
        raw = input(f'密钥路径 [{default_path}]: ').strip()
    except (KeyboardInterrupt, EOFError) as exc:
        raise UserCancelled from exc
    if raw and any(ord(c) < 32 or ord(c) == 127 for c in raw):
        raise ValueError('密钥路径不能包含控制字符')
    return choices[chosen[0]], Path(raw or default_path).expanduser().absolute()
