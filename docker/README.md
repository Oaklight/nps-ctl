# Docker

Container images for nps-ctl are published to Docker Hub as
[`oaklight/nps-ctl`](https://hub.docker.com/r/oaklight/nps-ctl): a Python
image (`latest`) plus Nuitka binary images (`<version>-alpine`,
`<version>-glibc`) for amd64 and arm64.

- [English](README_en.md) — image tags, quick start, writes, Compose, TLS
- [中文](README_zh.md) — 镜像标签、快速开始、写操作、Compose、TLS

Example files:

- [`compose.example.yaml`](compose.example.yaml) — run the published image
- [`compose.dev.yaml`](compose.dev.yaml) — build and run from the working tree
