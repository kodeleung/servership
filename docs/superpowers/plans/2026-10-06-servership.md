# Servership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在用户电脑以 Python 驱动 YAML 清单、复选框、SSH 密钥和多个 Debian / Ubuntu 服务器的顺序初始化。

**Architecture:** Python 客户端调用系统 OpenSSH 并保留原生密码/口令交互；gum 提供成熟终端复选框，PyYAML 负责安全解析清单。服务器仅执行系统命令和 Bash 模块，不安装或依赖 Python。每台单独提权、配置公钥、验证新密钥再安装，失败隔离并汇总。

**Tech Stack:** 客户端 Python >=3.10、PyYAML、gum、ssh/scp/ssh-keygen；服务端 Bash、apt、systemd、账号及文件工具；pytest 和 ShellCheck 为开发验证依赖。

**Spec:** `docs/superpowers/specs/2026-10-06-servership-design.md`（已确认电脑端执行、YAML 批量清单、客户端 Python / 服务端命令版）。此计划整体替代旧服务器内执行计划。

## Global Constraints

- 本机以当前用户运行，不要求 root；服务器在任何远程写入或安装前取得 root 权限。
- 服务器支持 Debian / Ubuntu；服务端不要求 Python，客户端兼容 macOS / Linux。
- 清单为 servers.yaml，可指定路径；整份清单在任何远程操作前完成验证。
- defaults 仅支持 port、user，默认分别为 22、root；servers 是非空列表，name 与 host 必填且 name 唯一。
- identity_file 仅用于首次登录，支持 ~、空格和相对清单目录路径；未填写沿用 SSH 正常认证。
- 服务器和软件均用 ↑/↓、Space、Ctrl+A、Enter 复选框；默认全不选，Esc/Ctrl+C 取消。
- 未选服务器时正常结束，不生成密钥或连接；未选软件仍配置选中服务器的公钥。
- 私钥在用户电脑生成/复用，默认 ~/.ssh/servership_ed25519，不覆盖、不上传、不打印、不导出。
- 每台顺序执行；root 直接使用，普通用户 sudo 提权；不能假定跨会话 sudo 缓存。
- 公钥保留原内容并按类型/主体去重；.ssh 为 700、authorized_keys 为 600，归登录账号。
- 公钥验证禁止回退服务器密码/键盘交互认证，允许私钥口令提示；失败不安装。
- 单台失败继续其他服务器；单项安装失败继续其他独立软件；整体有失败非零，取消 130。
- 既有软件不自动升级/卸载/覆盖；不删 apt 锁、不改 SSH 策略、不主动重启现有 SSH 服务。
- sing-box 无配置仅安装验证并标注待配置；本机缺依赖给出指引，不自动安装。

## Review Focus

- YAML 重复键、布尔端口和未知字段不能被悄悄接受；错误定位到服务器/字段（任务 1）。
- 空服务器选择、空软件选择与取消的副作用不同，未选服务器没有连接（任务 2、6）。
- IPv6、空格身份路径、远程命令特殊字符不能变成选项或代码（任务 1、3）。
- sudo 被拒绝或私钥有口令时不能混淆登录结果，公钥验证不能密码回退（任务 3、4）。
- 单台失联、apt 锁冲突、服务验证失败或取消时，汇总不能误报成功或继续不该执行的阶段（任务 5、6）。

## 文件结构与公共模型

```text
pyproject.toml                  包、依赖和 servership 命令入口
src/servership/__init__.py
src/servership/__main__.py       python -m servership 入口
src/servership/models.py         Server、KeyPair、StepResult、ServerResult
src/servership/inventory.py      YAML 安全加载和结构验证
src/servership/ui.py             gum 交互适配
src/servership/ssh.py            OpenSSH 提权、传输、远程执行和清理
src/servership/keys.py           本机密钥生成/复用和公钥验证
src/servership/batch.py          顺序批处理与失败隔离
src/servership/cli.py            参数、环境预检、汇总
src/servership/remote/           随 Python 包分发的 Bash 模块
  preflight.sh common.sh authorize.sh install.sh
  installers/caddy.sh docker.sh sing-box.sh openssh.sh
servers.example.yaml            文档示例，无真实账号或密码
README.md                       使用与验证边界
.gitignore                      测试/构建缓存、本机清单
 tests/conftest.py               临时目录和受控命令替身
 tests/test_inventory.py
 tests/test_ui.py
 tests/test_ssh.py
 tests/test_keys.py
 tests/test_installers.py
 tests/test_batch.py
 tests/integration/README.md     可丢弃 Linux 环境验收
```

代码在 src/servership，测试在 tests；文件树中的空格只用于展示。核心 dataclass：`Server(name: str, host: str, port: int, user: str, identity_file: Path | None)`；`KeyPair(private_path: Path, public_key: str)`；`StepResult(stage: str, status: str, detail: str)`；`ServerResult(server: Server, steps: list[StepResult])`。status 为 success/skipped/failed/not_run，stage 为 preflight/authorize/verify/caddy/docker/sing-box/openssh/cleanup。

测试不得连接真实用户服务器或修改真实 ~/.ssh；通过临时目录、命令替身与可丢弃 Linux 环境验证。生产代码不提供跳过权限/系统校验的测试后门。SSH 使用参数列表，进入远程 shell 的参数统一使用 shlex.quote。服务器身份确认和密码提示沿用标准 OpenSSH，不设置忽略主机身份检查的选项。

## Task 1: Python 项目与 YAML 清单

**Files:** pyproject.toml、models.py、inventory.py、包入口文件、servers.example.yaml、.gitignore、tests/conftest.py、tests/test_inventory.py。

**Interfaces:** `load_inventory(path: Path) -> list[Server]`；配置错误抛 `InventoryError`，包含服务器、字段或 YAML 行号。defaults 应用后生成 Server，identity_file 为展开且解析到清单目录的绝对路径。

- [ ] 写失败测试：`test_defaults_and_overrides` 断言 port/user 的省略与覆盖；`test_duplicate_keys_names_unknown_fields` 分别拒绝 YAML 重复键、重复 name 和未知字段；`test_types_and_range` 拒绝布尔/字符串端口、空服务器列表、无效账号/主机和控制字符，接受合法 IPv6。
- [ ] 写失败测试：`test_identity_paths` 验证 ~、相对路径及空格路径，缺失/不可读私钥明确报错；`test_unsafe_yaml_tag_rejected` 拒绝自定义对象标签并无执行副作用。
- [ ] 运行 `python3 -m pytest tests/test_inventory.py -q`，确认因尚无实现失败。
- [ ] 实现包元数据、模型和 PyYAML SafeLoader 结构校验；重复键检测只扩展库的映射构造，不自行解析 YAML；拒绝未知字段，错误包含上下文。示例使用文档地址，不提交真实清单。
- [ ] 重跑测试，预期通过。若目录仍非 Git 仓库则初始化，仅提交已批准文档和任务文件，提交说明 `feat: add Python client and YAML inventory`。

## Task 2: 服务器与软件复选框

**Files:** ui.py、cli.py 的环境预检、tests/test_ui.py。

**Interfaces:** `select_servers(servers: list[Server]) -> list[Server]` 按清单顺序返回；`select_software() -> list[str]` 仅返回 caddy/docker/sing-box/openssh；`choose_key(default_path: Path) -> tuple[str, Path]` 返回 generate/reuse 和路径；取消抛 `UserCancelled`。

- [ ] 写失败测试：`test_empty_server_selection_no_side_effect` 断言空列表正常结束；`test_empty_software_is_valid` 断言空软件选择不视为取消；`test_selection_order_and_allowlist` 验证部分/全部结果按输入顺序、无未知软件；`test_gum_abort_is_cancel` 验证 Esc/Ctrl+C 与成功空输出不同。
- [ ] 运行 `python3 -m pytest tests/test_ui.py -q`，确认失败。
- [ ] 实现 gum subprocess 适配，保留终端输入；stdout 仅捕获选择结果；默认全不选，显示中文 Space/方向键/Ctrl+A/Enter 提示。核对实际 gum 发布版本和退出码，不依据 main 分支猜测。
- [ ] 实现客户端依赖与终端检查，缺失给出指引。Python 的 Ctrl+C 与 gum 取消统一为 UserCancelled，最终 130。
- [ ] 重跑测试并在真实终端验证全部按键、部分/全选/清空；提交任务文件，说明 `feat: add interactive server and software checkboxes`。

## Task 3: SSH、服务器提权和远程模块传输

**Files:** ssh.py、remote/preflight.sh、remote/common.sh、tests/test_ssh.py。

**Interfaces:** `SSHClient(server: Server, identity: Path | None = None)`；`preflight() -> StepResult`；`stage(public_key: str) -> None` 记录工作目录；`run_root(script: str, args: list[str]) -> int`；`fetch_results() -> list[StepResult]`；`cleanup() -> StepResult`。script 必须是打包的受控模块名。

- [ ] 写失败测试：`test_sudo_denial_no_stage` 断言失败后无 mkdir/scp/公钥写入；`test_root_no_sudo` 断言 root 不调用 sudo；`test_each_root_command_rechecks_privilege` 断言每次变更会话通过 sudo/root 路径；`test_host_port_ipv6_identity_arguments` 断言所有 SSH/scp 参数传递准确。
- [ ] 写失败测试：`test_remote_arguments_quoted` 验证空格、单引号、分号和命令替换字符只作为数据；`test_private_file_never_transferred` 检查传输清单仅有模块与公钥；`test_cleanup_failure_preserves_original_failure` 保留原错误并报告临时路径。
- [ ] 运行 `python3 -m pytest tests/test_ssh.py -q`，确认失败。
- [ ] 实现只读 SSH 系统检查和 sudo 原生终端提权验证；用 SSH 分配终端运行 sudo，不用 sudo -S、不在命令行传密码。检查发行版、apt、systemd、Bash 与账号/文件工具，服务器不检查或安装 Python。
- [ ] 实现提权成功后才创建权限 700 的临时目录、scp 打包模块与公钥、分终端执行 root 模块。安装结果写受控 result.tsv，由远程模块设为登录用户可读，通过 scp 取回；安装输出直接显示，不解析带密码提示的终端日志作为状态。
- [ ] 清理仅操作本次登记并校验的临时路径，失败/取消也尝试清理；重跑测试。提交任务文件，说明 `feat: add SSH transport and remote privilege checks`。

## Task 4: 本机密钥与服务器公钥配置

**Files:** keys.py、remote/authorize.sh、tests/test_keys.py。

**Interfaces:** `prepare_key(mode: str, path: Path) -> KeyPair`；`authorize(client: SSHClient, key: KeyPair) -> StepResult`；`verify_access(server: Server, key: KeyPair) -> StepResult`。authorize.sh 接收受控公钥文件和登录账号，从 getent 解析 home/UID/GID。

- [ ] 写失败测试：`test_real_ed25519_pair` 使用真实 ssh-keygen 在临时目录生成与提取，断言类型和私钥 600；`test_existing_key_not_overwritten` 比较已有私钥/.pub 的内容；`test_reuse_derives_public_key` 断言不盲信已有 .pub；`test_private_content_not_logged` 捕获输出不含私钥正文。
- [ ] 写失败测试：`test_publickey_only_verification` 断言指定私钥、IdentitiesOnly、公钥认证且禁用服务器密码和 keyboard-interactive；不能用 BatchMode 禁止带口令私钥交互；`test_verification_failure_blocks_install` 验证后续被阻止。
- [ ] 写远程授权测试：`test_authorized_keys_preserve_deduplicate` 保留原内容并处理缺末尾换行、同主体不同 comment；`test_symlink_nonregular_rejected` 不跟随链接；`test_target_home_and_ownership` 根据账号数据库定位且 .ssh 700、文件 600、UID/GID 正确。实际权限测试需要 Linux 可丢弃环境，否则明确 skip。
- [ ] 运行 `python3 -m pytest tests/test_keys.py -q`，确认失败。
- [ ] 实现 ssh-keygen 原生口令交互、umask 077、禁止覆盖，匹配已有/生成公钥；私钥始终本机保留。实现远程合法公钥检查和按类型/主体去重，保留已有授权选项与配置。
- [ ] 实现新密钥公钥限定登录验证，验证失败提示公钥已添加且软件未安装。重跑测试并在 Linux SSH 环境验证带口令密钥；提交说明 `feat: provision and verify SSH key access`。

## Task 5: 远程软件安装器

**Files:** remote/install.sh、remote/installers/{caddy,docker,sing-box,openssh}.sh、remote/common.sh、tests/test_installers.py。

**Interfaces:** 每个模块 `install_<id>()` 返回 0 新安装并验证、10 已满足、其他失败；install.sh 调度并输出 result.tsv（固定 stage/status/detail 三列，detail 禁止制表符/换行），返回任一失败的整体非零状态。每个安装模块自身检查 root，不因其他项失败提前停止独立项。

- [ ] 写失败测试：`test_selected_only_and_empty` 空软件列表无 apt 操作；`test_failure_continues` 失败仍运行其他项；`test_existing_valid_not_upgraded` 无升级/重装；`test_lock_failure_preserved` 无删锁/强杀；`test_service_failure_not_success` 包安装成功但服务失败仍失败。
- [ ] 写失败测试：`test_singbox_no_config_not_started` 验证仅安装和版本；`test_openssh_no_config_change_or_restart` 比较配置且无 restart；`test_docker_no_group_changes` 无普通用户组修改；`test_corrupt_existing_reports_failure` 不自动修复。
- [ ] 运行 `python3 -m pytest tests/test_installers.py -q`，确认失败。
- [ ] 实施前核对四个项目当前官方软件源、支持系统版本/架构和签名机制，记录文档链接。缺少支持的组合在修改源前拒绝，不使用未经校验的下载执行管道。
- [ ] 实现 Caddy 包和服务、Docker 官方 Engine/CLI/Compose 和 daemon、sing-box 包和版本/OpenSSH server 配置与服务验证。保护现有配置，核对 Debian/Ubuntu 的服务名与包维护脚本行为，避免重启现有 SSH 或隐式启动无配置 sing-box。
- [ ] 重跑测试、Bash 语法与 ShellCheck；在可丢弃 Linux 环境验证真实安装/再次执行，记录未验证边界。提交说明 `feat: add modular remote software installers`。

## Task 6: 批处理入口、汇总和文档

**Files:** batch.py、cli.py、__main__.py、README.md、tests/test_batch.py、tests/integration/README.md。

**Interfaces:** `run_batch(servers: list[Server], software: list[str], key: KeyPair) -> list[ServerResult]`；`main(argv: list[str] | None = None) -> int`。命令默认读取 servers.yaml，通过 --inventory PATH 指定；没有隐藏并发或自动重试。server 结果保持清单顺序。

- [ ] 写失败测试：`test_bad_inventory_no_connection` 非法清单无远程操作；`test_one_host_failure_next_continues` 首台提权失败第二台仍执行；`test_publickey_failure_no_install` 断言失败阶段正确；`test_empty_software_still_authorizes` 断言密钥步骤继续；`test_unselected_hosts_never_connected` 未选服务器无连接。
- [ ] 写失败测试：`test_cancel_marks_remaining_not_run` 取消停止整批且返回 130；`test_missing_remote_report_is_failure` 取回结果失败不误报成功；`test_summary_and_exit_status` 逐台状态对应准确，任一失败非零，全部成功/跳过为 0。
- [ ] 运行 `python3 -m pytest tests/test_batch.py -q`，确认失败。
- [ ] 实现顺序为本机预检→清单验证→服务器选择→软件选择→密钥准备→摘要→逐台 preflight/authorize/verify/install/cleanup→汇总。每个阶段提示服务器名称，单台失败阻断依赖步骤且继续下一台；KeyboardInterrupt 停止当前子进程与后续调度并尝试清理。
- [ ] 运行全部 pytest、Python 编译检查、全部 Bash 语法和 ShellCheck；已通过后仅针对新问题重复检查。真实终端验证 gum，在至少两台可丢弃 SSH/systemd 服务器验证 Debian/Ubuntu、root/sudo、失败隔离、带口令密钥、重复运行。
- [ ] 编写 README：本机安装依赖/入口、YAML 字段/路径规则、按键、首连和 sudo 提示、私钥保留、安装范围、错误恢复；提供示例和运行验收记录，明确模拟测试与未完成真实验证。
- [ ] 自查与设计一致性并确保提交不含真实清单、密码/私钥/缓存。仅提交任务文件，说明 `feat: complete sequential multi-server initialization`。

## 执行交接

推荐在当前会话由我逐任务实施，再独立审阅整体改动；客户端模型、SSH 生命周期和批处理状态紧密依赖，顺序实施易于保持一致。也可由子代理逐任务实施与审阅。

开始实施前由用户审阅计划并选择执行方式。最终交付包括可运行 Python 客户端、远程模块、示例清单、文档、测试/实际验收边界和提交记录。不存在可用测试服务器时不操作真实用户服务器，明确尚未验证的服务行为。
