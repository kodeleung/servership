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

LABELS = {'success': '成功', 'skipped': '已满足/跳过', 'failed': '失败', 'not_run': '未执行'}


def check_environment():
    if os.geteuid() == 0:
        raise RuntimeError('请在自己的电脑以普通用户运行；服务器权限由 SSH/sudo 获取')
    missing = [tool for tool in ['ssh', 'scp', 'ssh-keygen', 'gum'] if shutil.which(tool) is None]
    if missing:
        raise RuntimeError('缺少本机工具：' + ', '.join(missing) + '。OpenSSH 请用系统包管理器安装；gum 见 https://github.com/charmbracelet/gum')
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError('请在交互终端运行，SSH、sudo 和复选框需要终端输入')


def summary(results):
    print('\n执行结果：')
    for result in results:
        print(f'\n{result.server.name} ({result.server.host})')
        for step in result.steps:
            print(f'  {step.stage}: {LABELS[step.status]} — {step.detail}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='从本机批量初始化 Debian / Ubuntu 服务器')
    parser.add_argument('--inventory', type=Path, default=Path('servers.yaml'), help='YAML 服务器清单（默认 servers.yaml）')
    args = parser.parse_args(argv)
    try:
        check_environment()
        servers = load_inventory(args.inventory)
        selected = select_servers(servers)
        if not selected:
            print('未选择服务器，已结束。')
            return 0
        software = select_software()
        mode, path = choose_key(Path.home() / '.ssh/servership_ed25519')
        key = prepare_key(mode, path)
        print('\n执行摘要：')
        for server in selected:
            print(f'  {server.name}: {server.user}@{server.host}:{server.port}')
        print('软件：' + (', '.join(software) if software else '不安装软件，仅配置 SSH 公钥'))
        print(f'本机私钥：{key.private_path}（保留在本机）', flush=True)
        results = run_batch(selected, software, key)
        summary(results)
        return 1 if any(step.status == 'failed' for result in results for step in result.steps) else 0
    except BatchCancelled as exc:
        summary(exc.results)
        print('\n批处理已取消；已完成的授权和安装保留。', file=sys.stderr)
        return 130
    except (KeyboardInterrupt, UserCancelled):
        print('\n已取消。', file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 1
