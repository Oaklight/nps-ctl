# Installation

## Basic Installation

Requires **Python >= 3.11**.

```bash
pip install nps-ctl
```

## Optional: SOCKS5 Proxy Support

If you need to connect to NPS servers through a SOCKS5 proxy (e.g., via SSH tunnel):

```bash
pip install nps-ctl PySocks
```

## Development Installation

```bash
git clone https://github.com/Oaklight/nps-ctl.git
cd nps-ctl
pip install -e ".[dev,test]"
```
