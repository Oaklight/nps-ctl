# 安装

## 基本安装

需要 **Python >= 3.11**。

```bash
pip install nps-ctl
```

## 可选：SOCKS5 代理支持

如果需要通过 SOCKS5 代理（如 SSH 隧道）连接 NPS 服务器：

```bash
pip install nps-ctl PySocks
```

## 开发安装

```bash
git clone https://github.com/Oaklight/nps-ctl.git
cd nps-ctl
pip install -e ".[dev,test]"
```
