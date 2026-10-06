import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src/servership/remote'


def dispatch(tmp_path, software):
    # An isolated copy substitutes the privileged boundary and installers.
    # Only the real dispatch script executes, and all files stay in tmp_path.
    remote = tmp_path / 'remote'
    (remote / 'installers').mkdir(parents=True)
    shutil.copy(ROOT / 'install.sh', remote / 'install.sh')
    (remote / 'common.sh').write_text('require_root() { :; }\n')
    for name, function, status in [('caddy', 'caddy', 1), ('docker', 'docker', 0), ('sing-box', 'sing_box', 10), ('openssh', 'openssh', 0)]:
        (remote / 'installers' / f'{name}.sh').write_text(f'install_{function}() {{ echo {name} >> "{tmp_path}/calls"; return {status}; }}\n')
    # chown and getent are isolated stubs, not privileged production operations.
    tools = tmp_path / 'bin'
    tools.mkdir()
    for name, body in [('getent', f'printf "fixture:x:{os.getuid()}:{os.getgid()}::/tmp:/bin/sh\\n"'), ('chown', ':')]:
        tool = tools / name
        tool.write_text('#!/bin/sh\n' + body + '\n')
        tool.chmod(0o755)
    env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'])
    result = subprocess.run(['bash', str(remote / 'install.sh'), str(tmp_path / 'result.tsv'), 'fixture', *software], env=env, capture_output=True, text=True)
    return result, (tmp_path / 'result.tsv').read_text() if (tmp_path / 'result.tsv').exists() else '', (tmp_path / 'calls').read_text() if (tmp_path / 'calls').exists() else ''


def test_failure_continues_and_status_matches(tmp_path):
    result, report, calls = dispatch(tmp_path, ['caddy', 'docker', 'sing-box'])
    assert result.returncode != 0
    assert calls.splitlines() == ['caddy', 'docker', 'sing-box']
    assert 'caddy\tfailed\t' in report
    assert 'docker\tsuccess\t' in report
    assert 'sing-box\tskipped\t' in report


def test_empty_selection_no_installer(tmp_path):
    result, report, calls = dispatch(tmp_path, [])
    assert result.returncode == 0 and report == '' and calls == ''


def test_unknown_software_rejected(tmp_path):
    result, _, calls = dispatch(tmp_path, ['../../bad'])
    assert result.returncode != 0 and calls == ''


def installed_module(module, function, service_status=0):
    # Exercise production installer branches with controlled package/service boundaries.
    script = f'''
set -euo pipefail
source "{ROOT}/common.sh"
source "{ROOT}/installers/{module}.sh"
require_root() {{ :; }}
detect_platform() {{ :; }}
package_installed() {{ return 0; }}
require_service() {{ return {service_status}; }}
caddy() {{ :; }}
docker() {{ :; }}
sing-box() {{ :; }}
apt_install() {{ echo UNEXPECTED_APT; exit 91; }}
systemctl() {{ echo UNEXPECTED_SERVICE_CHANGE; exit 92; }}
{function}
'''
    return subprocess.run(['bash', '-c', script], capture_output=True, text=True)


def test_existing_caddy_skips_no_upgrade():
    result = installed_module('caddy', 'install_caddy')
    assert result.returncode == 10
    assert 'UNEXPECTED' not in result.stdout


def test_service_failure_not_success():
    result = installed_module('caddy', 'install_caddy', service_status=3)
    assert result.returncode == 3


def test_singbox_existing_never_started():
    result = installed_module('sing-box', 'install_sing_box')
    assert result.returncode == 10
    assert 'UNEXPECTED' not in result.stdout


def test_docker_existing_no_group_or_install_change():
    result = installed_module('docker', 'install_docker')
    assert result.returncode == 10
    assert 'UNEXPECTED' not in result.stdout


def test_apt_lock_error_propagates():
    script = f'source "{ROOT}/common.sh"; apt-get() {{ echo "lock held" >&2; return 100; }}; apt_install fixture'
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    assert result.returncode == 100 and 'lock held' in result.stderr
