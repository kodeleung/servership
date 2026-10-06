import re
import shlex
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from .models import SOFTWARE, Server, StepResult

WORKDIR = re.compile(r'/tmp/servership\.[A-Za-z0-9]{8,16}')


class SSHClient:
    def __init__(self, server: Server, identity: Path | None = None):
        self.server = server
        self.identity = identity or server.identity_file
        self.workdir: str | None = None
        self.ready = False

    def _options(self) -> list[str]:
        args = ['-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2']
        if self.identity:
            args += ['-i', str(self.identity), '-o', 'IdentitiesOnly=yes']
        return args

    def ssh_args(self, tty: bool = False) -> list[str]:
        return ['ssh', *self._options(), *(['-tt'] if tty else []), '-p', str(self.server.port), '-l', self.server.user, self.server.host]

    def scp_args(self) -> list[str]:
        return ['scp', *self._options(), '-P', str(self.server.port)]

    def scp_target(self, path: str) -> str:
        host = f'[{self.server.host}]' if ':' in self.server.host else self.server.host
        return f'{self.server.user}@{host}:{path}'

    def _root(self, argv: list[str]) -> str:
        if self.server.user != 'root':
            argv = ['sudo', '--', *argv]
        return shlex.join(argv)

    def preflight(self) -> StepResult:
        code = files('servership').joinpath('remote/preflight.sh').read_text()
        result = subprocess.run([*self.ssh_args(tty=True), self._root(['bash', '-c', code])])
        self.ready = result.returncode == 0
        return StepResult('preflight', 'success' if self.ready else 'failed', '系统及 root 权限验证通过' if self.ready else f'连接、系统或提权失败（{result.returncode}）')

    def stage(self, public_key: str) -> None:
        if not self.ready:
            raise RuntimeError('必须先验证服务器 root 权限')
        result = subprocess.run([*self.ssh_args(), 'umask 077; mktemp -d /tmp/servership.XXXXXXXX'], text=True, stdout=subprocess.PIPE, check=True)
        path = result.stdout.strip()
        if not WORKDIR.fullmatch(path):
            raise RuntimeError('服务器返回了无效临时目录')
        self.workdir = path
        remote = Path(str(files('servership').joinpath('remote')))
        subprocess.run([*self.scp_args(), '-r', '--', str(remote), self.scp_target(path + '/')], check=True)
        with tempfile.TemporaryDirectory(prefix='servership-') as local:
            public = Path(local) / 'public.key'
            public.write_text(public_key + '\n', encoding='utf-8')
            subprocess.run([*self.scp_args(), '--', str(public), self.scp_target(path + '/public.key')], check=True)

    def run_root(self, script: str, args: list[str]) -> int:
        if not self.workdir or not WORKDIR.fullmatch(self.workdir) or script not in {'authorize.sh', 'install.sh'}:
            raise ValueError('无效远程模块或临时目录')
        command = self._root(['bash', f'{self.workdir}/remote/{script}', *args])
        return subprocess.run([*self.ssh_args(tty=True), command]).returncode

    def fetch_results(self) -> list[StepResult]:
        if not self.workdir or not WORKDIR.fullmatch(self.workdir):
            raise ValueError('无效临时目录')
        with tempfile.TemporaryDirectory(prefix='servership-report-') as local:
            report = Path(local) / 'result.tsv'
            subprocess.run([*self.scp_args(), '--', self.scp_target(self.workdir + '/result.tsv'), str(report)], check=True)
            if report.stat().st_size > 65536:
                raise ValueError('远程结果过大')
            results, stages = [], set()
            for line in report.read_text(encoding='utf-8').splitlines():
                columns = line.split('\t')
                if len(columns) != 3:
                    raise ValueError('无效远程结果')
                stage, status, detail = columns
                if stage not in SOFTWARE or status not in {'success', 'skipped', 'failed'} or stage in stages:
                    raise ValueError('无效或重复远程状态')
                if any(ord(c) < 32 or ord(c) == 127 for c in detail):
                    raise ValueError('结果包含控制字符')
                stages.add(stage)
                results.append(StepResult(stage, status, detail))
            return results

    def cleanup(self) -> StepResult:
        if not self.workdir:
            return StepResult('cleanup', 'skipped', '无临时目录')
        if not WORKDIR.fullmatch(self.workdir):
            return StepResult('cleanup', 'failed', '拒绝清理未登记的目录')
        # No recursive root deletion; all temporary output belongs to login user.
        try:
            command = shlex.join(['rm', '-rf', '--', self.workdir])
            rc = subprocess.run([*self.ssh_args(), command], timeout=30).returncode
        except (subprocess.SubprocessError, OSError) as exc:
            return StepResult('cleanup', 'failed', f'{self.workdir}: {type(exc).__name__}')
        return StepResult('cleanup', 'success' if rc == 0 else 'failed', self.workdir)
