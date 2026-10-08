# Installation

## Requirements

- **Python 3.11** or newer

## Install from PyPI

```bash
pip install nps-ctl
```

!!! tip "Use a virtual environment"
    It is good practice to install nps-ctl inside a virtual environment
    (venv, conda, etc.) to avoid conflicts with system packages:

    ```bash
    python -m venv .venv
    source .venv/bin/activate   # Linux / macOS
    pip install nps-ctl
    ```

## Optional: SOCKS5 proxy support

If you need to route API requests through a SOCKS5 proxy (for example, an
SSH tunnel to a private NPS server), install [PySocks](https://pypi.org/project/PySocks/)
alongside nps-ctl:

```bash
pip install "nps-ctl" PySocks
```

## Development install

To work on nps-ctl itself, clone the repository and install in editable mode
with development and test extras:

```bash
git clone https://github.com/Oaklight/nps-ctl.git
cd nps-ctl
pip install -e ".[dev,test]"
```

## Verify the installation

```bash
nps-ctl --version
```

You should see output like:

```
nps-ctl 0.7.0
```

## Troubleshooting

**`pip: command not found`**

Your Python installation may not include pip, or pip is not on your `PATH`.
Try `python -m pip install nps-ctl` instead, or install pip first with
`python -m ensurepip --upgrade`.

**`nps-ctl requires Python >=3.11`**

Check your Python version with `python --version`. If your system Python is
older than 3.11, install a newer version via your package manager, pyenv, or
conda, and create a virtual environment with that version.
