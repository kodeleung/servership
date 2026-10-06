# Servership

快速完成 Linux 服务器初始化，批量安装常用软件、配置远程访问，让新服务器轻松就绪。

Servership 在你的 macOS / Linux 电脑上运行，通过 SSH 管理多台服务器。用一份 YAML 清单定义服务器，在终端勾选目标和软件，即可完成初始化。

## 功能

- **交互式批量操作**：复选框选择服务器和软件，支持全选、部分选择和空选择。
- **常用软件安装**：支持 Caddy、Docker、sing-box 和 OpenSSH，使用官方签名软件源。
- **SSH 密钥配置**：在本机生成或复用密钥，追加服务器公钥授权，并验证登录。
- **远程提权**：root 直接执行，普通账号通过 sudo 获取权限；服务器无需安装 Python。
- **逐台执行与结果汇总**：单台失败继续处理后续服务器，报告各步骤结果。
- **保留已有配置**：已满足要求的安装会跳过，不自动升级或覆盖配置。

## 快速开始

### 环境要求

本机需要 Python 3.10+、OpenSSH（`ssh`、`scp`、`ssh-keygen`）、[gum](https://github.com/charmbracelet/gum#installation) 和交互终端。macOS 可通过 `brew install gum` 安装 gum。

服务器需要已能通过 SSH 登录，运行 systemd，并使用 root 账号或具有 sudo 权限的账号。

### 安装与运行

```sh
git clone https://github.com/kodeleung/servership.git
cd servership

python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

cp servers.example.yaml servers.yaml
# 编辑 servers.yaml，填写服务器地址和登录账号
servership
```

也可以通过 `python -m servership` 启动。请以普通用户在本机运行，提权发生在服务器端。

默认查找**当前目录**的 `servers.yaml`，不存在时使用 `servers.yml`。两者同时存在时优先使用 `servers.yaml`；所选文件无效时直接报错，不切换到另一份清单。

指定其他清单：

```sh
servership --inventory /path/to/servers.yaml
```

## 服务器清单

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

| 字段 | 说明 |
| --- | --- |
| `name` | 必填，服务器唯一名称 |
| `host` | 必填，域名、IPv4 或 IPv6 地址 |
| `port` | SSH 端口，覆盖 `defaults.port`，默认 `22` |
| `user` | 登录账号，覆盖 `defaults.user`，默认 `root` |
| `identity_file` | 可选，首次登录使用的已有本机私钥 |

省略 `identity_file` 时使用 OpenSSH 的正常认证方式，包括 ssh-agent、SSH 配置和密码提示。路径支持 `~`；相对路径以清单所在目录为基准。清单验证通过后才连接服务器。

清单不保存密码或私钥内容。提交代码前检查本地清单，避免将真实服务器信息上传到仓库。

## 交互流程

1. 选择目标服务器。
2. 选择需要安装的软件。
3. 生成新密钥或复用已有密钥。
4. 逐台检查系统和 root 权限、配置公钥、验证密钥登录，再安装所选软件。
5. 查看各服务器的执行结果。

| 按键 | 操作 |
| --- | --- |
| ↑ / ↓ | 移动 |
| Space | 勾选 / 取消 |
| Ctrl+A | 全选 / 取消全选 |
| Enter | 确认 |
| Esc / Ctrl+C | 取消 |

默认均不勾选。不选服务器直接结束；不选软件仍配置 SSH 公钥。

密钥默认路径为 `~/.ssh/servership_ed25519`，私钥始终保留在本机，已有密钥文件不会被覆盖。整批服务器使用同一把密钥。带口令的密钥可提前通过 `ssh-add /path/to/key` 加入 ssh-agent。

密码、主机身份确认和 sudo 使用原生终端交互，不同会话可能重复提示。执行失败返回非零状态，取消返回 `130`；取消保留已完成的变更，并尝试清理临时文件。

## 支持范围

安装器支持 Debian 12 / 13、Ubuntu 22.04 / 24.04 / 26.04，以及 amd64 / arm64 架构。

| 软件 | 安装后的状态 |
| --- | --- |
| Caddy | 安装官方包并验证服务运行；站点需自行配置 |
| Docker | 安装 Engine、CLI、Buildx、Compose 插件并验证 daemon；不修改用户组 |
| sing-box | 安装官方稳定包并验证版本；需自行配置和启动服务 |
| OpenSSH | 安装 server 包、检查配置及服务；不改变端口或登录策略，不主动重启已有服务 |

已有安装满足要求时跳过；冲突或损坏状态会报告失败，不自动卸载或修复。新装 OpenSSH / sing-box 时临时阻止服务启动或重启；已有 `policy-rc.d` 会保留并报告失败。包管理器锁冲突不会通过删锁或终止其他进程解决。

实际 Linux 验证覆盖 Ubuntu 24.04 和 Debian 13 的 arm64 环境。完整验证范围及未覆盖项见[集成验证记录](tests/integration/README.md)。

## 开发与贡献

客户端使用 Python，远程模块使用 Bash。源码位于 `src/servership/`，软件安装器位于 `src/servership/remote/installers/`，测试位于 `tests/`。

在已激活的虚拟环境中：

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q src
shellcheck -x -P SCRIPTDIR src/servership/remote/*.sh src/servership/remote/installers/*.sh
```

ShellCheck 需单独安装。测试使用临时目录和受控命令替身，不连接清单中的真实服务器；gum 可用时会运行真实终端交互测试。远程安装变更应在可丢弃的 Linux 环境验证。

欢迎通过 Issue 报告问题或提出需求，通过 PR 贡献改进。请说明行为变化、测试结果和验证限制；提交约定和项目结构见 [AGENTS.md](AGENTS.md)。
