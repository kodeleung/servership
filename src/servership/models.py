from dataclasses import dataclass, field
from pathlib import Path

SOFTWARE = ('caddy', 'docker', 'sing-box', 'openssh')


@dataclass(frozen=True)
class Server:
    name: str
    host: str
    port: int = 22
    user: str = 'root'
    identity_file: Path | None = None


@dataclass(frozen=True)
class KeyPair:
    private_path: Path
    public_key: str


@dataclass(frozen=True)
class StepResult:
    stage: str
    status: str
    detail: str = ''


@dataclass
class ServerResult:
    server: Server
    steps: list[StepResult] = field(default_factory=list)


class UserCancelled(Exception):
    pass
