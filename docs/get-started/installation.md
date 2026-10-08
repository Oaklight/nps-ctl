# 安装

## 环境要求

- **Python 3.11** 或更高版本

## 从 PyPI 安装

```bash
pip install nps-ctl
```

!!! tip "使用虚拟环境"
    建议在虚拟环境（venv、conda 等）中安装 nps-ctl，以避免与系统包产生冲突：

    ```bash
    python -m venv .venv
    source .venv/bin/activate   # Linux / macOS
    pip install nps-ctl
    ```

## 可选：SOCKS5 代理支持

如果你需要通过 SOCKS5 代理发送 API 请求（例如通过 SSH 隧道访问私有 NPS 服务器），请在安装 nps-ctl 的同时安装 [PySocks](https://pypi.org/project/PySocks/)：

```bash
pip install "nps-ctl" PySocks
```

## 开发安装

如果你想参与 nps-ctl 本身的开发，请克隆仓库并以可编辑模式安装，同时包含开发和测试依赖：

```bash
git clone https://github.com/Oaklight/nps-ctl.git
cd nps-ctl
pip install -e ".[dev,test]"
```

## 验证安装

```bash
nps-ctl --version
```

你应该看到类似以下的输出：

```
nps-ctl 0.7.0
```

## 常见问题

**`pip: command not found`**

你的 Python 安装可能未包含 pip，或者 pip 不在 `PATH` 中。请尝试使用 `python -m pip install nps-ctl`，或先通过 `python -m ensurepip --upgrade` 安装 pip。

**`nps-ctl requires Python >=3.11`**

请使用 `python --version` 检查 Python 版本。如果系统 Python 版本低于 3.11，请通过包管理器、pyenv 或 conda 安装更新的版本，并使用该版本创建虚拟环境。
