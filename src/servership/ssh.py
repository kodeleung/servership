import re
import shlex
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from .models import SOFTWARE, KeyPair, Server, StepResult, UserCancelled

WORKDIR = re.compile(r'/tmp/servership\.[A-Za-z0-9]{8,16}')

# Preserve connection routing/trust from `ssh -G`, but never its identities or masters.
CONNECTION_OPTIONS = {
    'hostname', 'addressfamily', 'bindaddress', 'bindinterface', 'proxycommand',
    'proxyjump', 'proxyusefdpass', 'connecttimeout', 'connectionattempts',
    'serveraliveinterval', 'serveralivecountmax', 'hostkeyalias', 'hostkeyalgorithms',
    'userknownhostsfile', 'globalknownhostsfile', 'knownhostscommand',
    'stricthostkeychecking', 'checkhostip', 'verifyhostkeydns', 'hashknownhosts',
    'identityagent', 'compression', 'ipqos', 'tcpkeepalive',
    'ciphers', 'macs', 'kexalgorithms', 'pubkeyacceptedalgorithms',
}


def _config_quote(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _run(argv, **kwargs):
    check = kwargs.pop('check', False)
    result = subprocess.run(argv, **kwargs)
    if result.returncode in (130, 143, -2, -15):
        raise UserCancelled
    if check:
        result.check_returncode()
    return result


class SSHClient:
    def __init__(self, server: Server, identity: Path | None = None):
        self.server = server
        self.identity = identity or server.identity_file
        self._original_identity = self.identity
        self.workdir: str | None = None
        self.ready = False
        self.config_path: Path | None = None
        self._credentials = None

    def _options(self) -> list[str]:
        args = ['-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2']
        if self.config_path:
            args += ['-F', str(self.config_path)]
        if self.identity:
            args += ['-i', str(self.identity), '-o', 'IdentitiesOnly=yes']
        return args

    def use_key(self, key: KeyPair) -> None:
        """Offer exactly this key on a fresh connection, retaining host/proxy settings."""
        self.close()
        args = self.ssh_args()
        host = args.pop()
        source_configs = [Path.home() / '.ssh/config', Path('/etc/ssh/ssh_config')]
        if '-F' in args:
            source_configs = [Path(args[args.index('-F') + 1])]
        effective = _run([args[0], '-G', *args[1:], host], text=True, stdout=subprocess.PIPE, check=True).stdout
        credentials = tempfile.TemporaryDirectory(prefix='servership-identity-')
        self._credentials = credentials
        directory = Path(credentials.name)
        identity = directory / 'identity'
        identity.symlink_to(key.private_path)
        identity.with_name('identity.pub').write_text(key.public_key + '\n', encoding='utf-8')
        self.config_path = directory / 'config'
        lines = [f'Host {self.server.host}', '  CanonicalizeHostname no']
        for line in effective.splitlines():
            option, _, value = line.partition(' ')
            if option in CONNECTION_OPTIONS and value and value != 'none':
                lines.append(f'  {option} {value}')
        lines += [
            f'  IdentityFile {_config_quote(str(identity))}',
            '  CertificateFile none', '  IdentitiesOnly yes',
            '  PreferredAuthentications publickey', '  PasswordAuthentication no',
            '  KbdInteractiveAuthentication no', '  ControlMaster no',
            '  ControlPath none', '  ControlPersist no',
            # Jump hosts may still need their original config and identities.
            f'Host * !{self.server.host}',
            *[f'  Include {_config_quote(str(path))}' for path in source_configs],
        ]
        self.config_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.identity = identity

    def close(self):
        if self._credentials:
            self._credentials.cleanup()
            self._credentials = None
            self.config_path = None
            self.identity = self._original_identity

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
        result = _run([*self.ssh_args(tty=True), self._root(['bash', '-c', code])])
        self.ready = result.returncode == 0
        return StepResult('preflight', 'success' if self.ready else 'failed', 'System and root privileges verified' if self.ready else f'Connection, system check, or privilege escalation failed ({result.returncode})')

    def stage(self, public_key: str) -> None:
        if not self.ready:
            raise RuntimeError('Server root privileges must be verified first')
        result = _run([*self.ssh_args(), 'umask 077; mktemp -d /tmp/servership.XXXXXXXX'], text=True, stdout=subprocess.PIPE, check=True)
        path = result.stdout.strip()
        if not WORKDIR.fullmatch(path):
            raise RuntimeError('Server returned an invalid temporary directory')
        self.workdir = path
        remote = Path(str(files('servership').joinpath('remote')))
        _run([*self.scp_args(), '-r', '--', str(remote), self.scp_target(path + '/')], check=True)
        with tempfile.TemporaryDirectory(prefix='servership-') as local:
            public = Path(local) / 'public.key'
            public.write_text(public_key + '\n', encoding='utf-8')
            _run([*self.scp_args(), '--', str(public), self.scp_target(path + '/public.key')], check=True)

    def run_root(self, script: str, args: list[str]) -> int:
        if not self.workdir or not WORKDIR.fullmatch(self.workdir) or script not in {'authorize.sh', 'install.sh'}:
            raise ValueError('Invalid remote module or temporary directory')
        command = self._root(['bash', f'{self.workdir}/remote/{script}', *args])
        return _run([*self.ssh_args(tty=True), command]).returncode

    def fetch_results(self, noninteractive: bool = False) -> list[StepResult]:
        if not self.workdir or not WORKDIR.fullmatch(self.workdir):
            raise ValueError('Invalid temporary directory')
        with tempfile.TemporaryDirectory(prefix='servership-report-') as local:
            report = Path(local) / 'result.tsv'
            _run([*self.scp_args(), *(['-o', 'BatchMode=yes'] if noninteractive else []), '--', self.scp_target(self.workdir + '/result.tsv'), str(report)], check=True)
            if report.stat().st_size > 65536:
                raise ValueError('Remote results are too large')
            results, stages = [], set()
            for line in report.read_text(encoding='utf-8').splitlines():
                columns = line.split('\t')
                if len(columns) != 3:
                    raise ValueError('Invalid remote results')
                stage, status, detail = columns
                if stage not in SOFTWARE or status not in {'success', 'skipped', 'failed'} or stage in stages:
                    raise ValueError('Invalid or duplicate remote status')
                if any(ord(c) < 32 or ord(c) == 127 for c in detail):
                    raise ValueError('Results contain control characters')
                stages.add(stage)
                results.append(StepResult(stage, status, detail))
            return results

    def cleanup(self) -> StepResult:
        if not self.workdir:
            return StepResult('cleanup', 'skipped', 'No temporary directory')
        if not WORKDIR.fullmatch(self.workdir):
            return StepResult('cleanup', 'failed', 'Refusing to clean up an unregistered directory')
        # No recursive root deletion; all temporary output belongs to login user.
        try:
            command = shlex.join(['rm', '-rf', '--', self.workdir])
            rc = subprocess.run([*self.ssh_args(), command], timeout=30).returncode
        except (subprocess.SubprocessError, OSError) as exc:
            return StepResult('cleanup', 'failed', f'{self.workdir}: {type(exc).__name__}')
        return StepResult('cleanup', 'success' if rc == 0 else 'failed', self.workdir)
