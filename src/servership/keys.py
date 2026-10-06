import os
import stat
import subprocess
import tempfile
from pathlib import Path

from .models import KeyPair, Server, StepResult
from .ssh import SSHClient, _run


def prepare_key(mode: str, path: Path) -> KeyPair:
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise ValueError('A private key cannot be a symbolic link')
    if mode == 'generate':
        public_path = path.with_name(path.name + '.pub')
        if os.path.lexists(path) or os.path.lexists(public_path):
            raise ValueError(f'Key file already exists; choose reuse or another path: {path}')
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Generate in a private directory; publish without replacing existing files.
        with tempfile.TemporaryDirectory(prefix='.servership-', dir=path.parent) as work:
            temporary = Path(work) / 'key'
            subprocess.run(['ssh-keygen', '-t', 'ed25519', '-f', str(temporary)], check=True)
            os.chmod(temporary, 0o600)
            os.link(temporary, path)
            try:
                os.link(temporary.with_name('key.pub'), public_path)
            except BaseException:
                path.unlink()
                raise
    elif mode != 'reuse':
        raise ValueError('Invalid key mode')
    if not path.is_file() or path.stat().st_uid != os.getuid():
        raise ValueError('The private key must be a regular file owned by the current user')
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(f'Private key permissions are too broad; run chmod 600 {path}')
    result = subprocess.run(['ssh-keygen', '-y', '-f', str(path)], stdout=subprocess.PIPE, text=True)
    public = result.stdout.strip()
    if result.returncode or '\n' in public or len(public.split()) < 2:
        raise ValueError('Could not extract the public key from the private key')
    return KeyPair(path, public)


def authorize(client: SSHClient, key: KeyPair) -> StepResult:
    client.stage(key.public_key)
    rc = client.run_root('authorize.sh', [client.workdir + '/public.key', client.server.user])
    return StepResult('authorize', 'success' if rc == 0 else 'failed', 'Public key authorization configured' if rc == 0 else f'Public key configuration failed ({rc})')


def verify_access(server: Server, key: KeyPair) -> StepResult:
    client = SSHClient(server, key.private_path)
    try:
        client.use_key(key)
        args = client.ssh_args()
        host = args.pop()
        args += ['-o', 'PreferredAuthentications=publickey', '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no', host, 'true']
        rc = _run(args).returncode
        return StepResult('verify', 'success' if rc == 0 else 'failed', 'Key login verified' if rc == 0 else 'Public key added, but key login failed; software was not installed')
    finally:
        client.close()
