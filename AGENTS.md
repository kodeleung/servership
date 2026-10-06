# Repository Guidelines

## Project Structure & Module Organization

Servership is a Python client that initializes Linux servers over OpenSSH. Servers execute Bash and system commands; they do not require Python.

- `src/servership/`: CLI, inventory validation, terminal selection, SSH transport, key management, and sequential batch execution.
- `src/servership/remote/`: privilege checks, authorization, and installation orchestration; `installers/` contains one script per software package.
- `tests/`: pytest tests; `tests/integration/README.md` records Linux integration verification.
- `servers.example.yaml`: inventory template. `docs/superpowers/` contains design and implementation documents.

## Build, Test, and Development Commands

Use Python 3.10+ in a virtual environment. Local execution also requires OpenSSH, gum, and an interactive terminal.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m compileall -q src
shellcheck -x -P SCRIPTDIR src/servership/remote/*.sh src/servership/remote/installers/*.sh
```

These commands install an editable development environment, run tests, check Python compilation, and lint shell scripts. To build distributions, install `build` and run `python -m build`.

Run `servership` or `python -m servership`. Inventory discovery checks the current directory for `servers.yaml`, then `servers.yml`; override with `--inventory PATH`.

## Coding Style & Naming Conventions

Follow existing four-space indentation in Python and Bash. Use `snake_case` for modules and functions, `PascalCase` for classes, and uppercase constants. Keep CLI logic separate from transport and remote installation logic. Use type annotations where practical, quote shell expansions, and keep user-facing prompts and errors in English. No Python formatter is currently configured.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. Cover meaningful behavior changes, especially inventory precedence, SSH identity verification, cancellation, and installer status reporting. Tests use temporary files and controlled command substitutes; terminal tests require gum. No numeric coverage threshold is configured. Validate remote changes in disposable Linux environments and record any unverified scenarios.

## Commit & Pull Request Guidelines

Follow existing commit prefixes: `feat:`, `fix:`, and `test:` with concise imperative descriptions. Keep commits focused. PR descriptions should explain resulting behavior, relevant validation, and limitations; link related issues when available.

## Security & Configuration

Run the client as a regular local user; obtain root privileges remotely. Keep private keys local and secrets out of inventories and commits. Preserve existing authorization, configuration, and installations. Verify key login before installing software, and use official signed package repositories.
