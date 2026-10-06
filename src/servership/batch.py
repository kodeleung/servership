import subprocess
import sys

from .keys import authorize, verify_access
from .models import KeyPair, Server, ServerResult, StepResult, UserCancelled
from .ssh import SSHClient


class BatchCancelled(UserCancelled):
    def __init__(self, results: list[ServerResult]):
        self.results = results


class _ServerStopped(Exception):
    """Stop dependencies without bypassing cancellation handling after cleanup."""


def _remaining(result: ServerResult, software: list[str]):
    present = {step.stage for step in result.steps}
    for stage in ['preflight', 'authorize', 'verify', *software]:
        if stage not in present:
            result.steps.append(StepResult(stage, 'not_run', 'A prerequisite failed or was cancelled'))


def run_batch(servers: list[Server], software: list[str], key: KeyPair) -> list[ServerResult]:
    results = []
    for index, server in enumerate(servers):
        print(f'\n[{index + 1}/{len(servers)}] {server.name} · {server.user}@{server.host}:{server.port}', file=sys.stderr, flush=True)
        result = ServerResult(server)
        results.append(result)
        client = SSHClient(server)
        stage = 'preflight'
        cancelled = False
        try:
            result.steps.append(client.preflight())
            if result.steps[-1].status != 'success':
                raise _ServerStopped
            stage = 'authorize'
            result.steps.append(authorize(client, key))
            if result.steps[-1].status != 'success':
                raise _ServerStopped
            stage = 'verify'
            print(f'[{server.name}] Verifying login with the local key', file=sys.stderr, flush=True)
            result.steps.append(verify_access(server, key))
            if result.steps[-1].status != 'success':
                raise _ServerStopped
            client.use_key(key)
            if software:
                stage = 'install'
                print(f'[{server.name}] Installing selected software (sudo may request your password again)', file=sys.stderr, flush=True)
                rc = client.run_root('install.sh', [client.workdir + '/result.tsv', server.user, *software])
                report = client.fetch_results()
                if not {step.stage for step in report} <= set(software):
                    raise ValueError('Remote installation results contain unselected software')
                result.steps.extend(report)
                if {step.stage for step in report} != set(software):
                    raise ValueError('Remote installation results are missing or do not match the selection')
                if rc != 0 and not any(step.status == 'failed' for step in report):
                    result.steps.append(StepResult('install', 'failed', f'Remote execution exited unsuccessfully ({rc})'))
        except _ServerStopped:
            pass
        except (KeyboardInterrupt, UserCancelled):
            cancelled = True
            if stage == 'install':
                try:
                    report = client.fetch_results(noninteractive=True)
                    if {step.stage for step in report} <= set(software):
                        result.steps.extend(report)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, UserCancelled, KeyboardInterrupt):
                    pass
            result.steps.append(StepResult(stage, 'not_run', 'Cancelled by user; this step may have made partial changes'))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            result.steps.append(StepResult(stage, 'failed', str(exc)))
        finally:
            _remaining(result, software)
            try:
                result.steps.append(client.cleanup())
            except (KeyboardInterrupt, UserCancelled):
                cancelled = True
                result.steps.append(StepResult('cleanup', 'failed', 'Cleanup cancelled; the remote temporary directory may remain'))
            finally:
                client.close()
        if cancelled:
            for pending in servers[index + 1:]:
                remainder = ServerResult(pending)
                _remaining(remainder, software)
                results.append(remainder)
            raise BatchCancelled(results)
    return results
