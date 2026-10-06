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
        raise ValueError('不能使用符号链接作为私钥')
    if mode == 'generate':
        public_path = path.with_name(path.name + '.pub')
        if os.path.lexists(path) or os.path.lexists(public_path):
            raise ValueError(f'密钥文件已存在，请选择复用或其他路径：{path}')
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
        raise ValueError('无效密钥模式')
    if not path.is_file() or path.stat().st_uid != os.getuid():
        raise ValueError('私钥必须是当前用户拥有的普通文件')
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(f'私钥权限过宽，请执行 chmod 600 {path}')
    result = subprocess.run(['ssh-keygen', '-y', '-f', str(path)], stdout=subprocess.PIPE, text=True)
    public = result.stdout.strip()
    if result.returncode or '\n' in public or len(public.split()) < 2:
        raise ValueError('无法从私钥提取公钥')
    return KeyPair(path, public)


def authorize(client: SSHClient, key: KeyPair) -> StepResult:
    client.stage(key.public_key)
    rc = client.run_root('authorize.sh', [client.workdir + '/public.key', client.server.user])
    return StepResult('authorize', 'success' if rc == 0 else 'failed', '公钥授权文件已配置' if rc == 0 else f'公钥配置失败（{rc}）')


def verify_access(server: Server, key: KeyPair) -> StepResult:
    client = SSHClient(server, key.private_path)
    try:
        client.use_key(key)
        args = client.ssh_args()
        host = args.pop()
        args += ['-o', 'PreferredAuthentications=publickey', '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no', host, 'true']
        rc = _run(args).returncode
        return StepResult('verify', 'success' if rc == 0 else 'failed', '新密钥登录验证通过' if rc == 0 else '公钥已添加，但新密钥登录失败；未安装软件')
    finally:
        client.close()
