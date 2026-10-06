# Servership

从自己的 macOS / Linux 电脑，通过 SSH 批量初始化 Debian / Ubuntu 服务器。客户端使用 Python，服务器只执行 Bash 和系统命令，无需 Python。

## 使用

本机需要 Python 3.10+、OpenSSH（ssh、scp、ssh-keygen）、gum 和交互终端。macOS 可用 `brew install gum`；其他系统见 [gum 安装文档](https://github.com/charmbracelet/gum#installation)。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
cp servers.example.yaml servers.yaml
# 编辑 servers.yaml，填写自己的服务器
servership --inventory servers.yaml
```

也可以运行 `python -m servership --inventory servers.yaml`。缺少本机依赖时会停止并给出提示；不要在电脑上用 sudo 启动客户端。

## 清单

```yaml
defaults:
  port: 22
  user: root
servers:
  - name: singapore-01
    host: 203.0.113.10
  - name: tokyo-01
    host: server.example.com
    port: 2222
    user: ubuntu
    identity_file: ~/.ssh/existing_key
```

`name`、`host` 必填，名称唯一。单台的 `port` / `user` 覆盖 defaults；两处均省略时为 22 / root。支持域名、IPv4、IPv6。

`identity_file` 是**首次登录已有的本机私钥**，可省略，届时使用 OpenSSH 的正常认证（包括 ssh-agent、用户 SSH 配置、密码提示）。支持 `~`、空格路径；相对路径以清单所在目录为基准。清单不存密码或私钥内容，不支持未知字段。整份清单验证通过后才连接服务器。

## 交互和执行

先选择服务器，再选择软件。↑/↓ 移动，Space 勾选/取消，Ctrl+A 全选/取消全选，Enter 确认，Esc / Ctrl+C 取消。默认都不勾选；不选服务器直接结束，不选软件仍配置公钥。

选择生成 Ed25519 密钥或复用已有密钥。默认路径 `~/.ssh/servership_ed25519`，已有私钥及 `.pub` 不会覆盖；口令由 ssh-keygen 提示。整批共用这把密钥，私钥只保留在电脑。可预先用 `ssh-add /path/to/key` 将带口令密钥加入自己的 ssh-agent。

服务器按清单顺序处理，密码、主机身份确认和 sudo 提示使用 OpenSSH 原生交互。一台失败继续其他服务器。每台在任何远程修改前验证 root 权限；普通账号需要 sudo，root 直接执行。不同会话可能重复提示密码。

公钥追加到登录账号的 `~/.ssh/authorized_keys`，保留原内容并去重、校正权限和归属。验证新密钥登录成功后才安装软件。结果按服务器与步骤汇总；失败返回非零，取消返回 130。取消后已完成的授权和安装会保留，临时内容会尝试清理。

## 软件与系统

首版安装器支持 Debian 12/13、Ubuntu 22.04/24.04/26.04，amd64 / arm64，服务器需要运行 systemd。其他发行版本/架构会明确报告不支持。

| 软件 | 安装内容与验证 |
| --- | --- |
| Caddy | 官方包、运行中的服务；站点由用户后续配置 |
| Docker | 官方 Engine、CLI、Buildx、Compose 插件，验证 daemon；不修改用户组 |
| sing-box | 官方稳定包、二进制版本；新安装不启动服务，节点配置后另行启用 |
| OpenSSH | server 包、配置检查及服务；不改变端口或登录策略，不主动重启现有服务 |

有效已有安装会跳过，不自动升级、卸载、覆盖或修复损坏状态。新装 OpenSSH / sing-box 通过临时 policy-rc.d 阻止包管理器启动或重启服务；已有该策略时保留原文件并报告失败，交由用户处理。包管理器锁冲突不会删锁或终止其他进程。

安装步骤依据 [Caddy 官方文档](https://caddyserver.com/docs/install)、[Docker Debian 文档](https://docs.docker.com/engine/install/debian/)、[Docker Ubuntu 文档](https://docs.docker.com/engine/install/ubuntu/) 和 [sing-box 官方文档](https://sing-box.sagernet.org/installation/package-manager/)。仅配置官方签名软件源，不下载执行第三方安装脚本。

## 开发与验证

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q src
shellcheck -x -P SCRIPTDIR src/servership/remote/*.sh src/servership/remote/installers/*.sh
```

测试使用临时目录和受控命令替身，不连接清单中的真实服务器。实际 Linux SSH、权限和安装验收见 [验证记录](tests/integration/README.md)。
