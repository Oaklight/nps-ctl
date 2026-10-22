# Docker images

[中文](README_zh.md) | [Back to the Docker index](README.md)

Three image variants are published to Docker Hub as
[`oaklight/nps-ctl`](https://hub.docker.com/r/oaklight/nps-ctl):

| Tags | Base | Size | Notes |
| --- | --- | --- | --- |
| `latest`, `latest-python`, `<version>`, `<version>-python` | `python:3.12-slim` | ~130 MB | Installs the wheel from PyPI; full CLI |
| `<version>-alpine` (and `latest-alpine` on releases) | `alpine` | ~22 MB | Nuitka musl binary; no Python runtime |
| `<version>-glibc` (and `latest-glibc` on releases) | `scratch` + glibc runtime | ~28 MB | Nuitka glibc binary; no Python runtime |

All images run as a non-root user (uid 10001), listen on `8080`, and keep
configuration in `/config`. `latest` points at the Python image; on a release
it moves together with `latest-python`, `latest-alpine` and `latest-glibc`.

The glibc variant is assembled `FROM scratch`: the image carries only the
glibc runtime pieces from Ubuntu 24.04 (the version its binary links against),
zlib, CA certificates, and a static busybox for the entrypoint. It is close to
the Alpine image in size while running on glibc hosts. Use `-alpine` on musl
systems, `-glibc` on glibc systems, and the default `python` image when you
want the most portable build.

## Quick start

Create a config directory with `edges.toml` and, for authentication, a users
file:

```bash
mkdir -p config
cp /etc/nps-ctl/edges.toml config/
nps-ctl util hash-password          # paste into config/web-users.toml

docker run -d --name nps-ctl-web \
  -p 8080:8080 \
  -v "$PWD/config:/config" \
  oaklight/nps-ctl:latest
```

Then open `http://127.0.0.1:8080/` and log in with a users-file account.

The dashboard **requires authentication** when it binds to a non-loopback
address, so the container refuses to start without either
`/config/web-users.toml` or `NPS_WEB_USERNAME`/`NPS_WEB_PASSWORD`:

```bash
docker run -d --name nps-ctl-web \
  -p 8080:8080 \
  -v "$PWD/config:/config" \
  -e NPS_WEB_USERNAME=admin \
  -e NPS_WEB_PASSWORD='choose-a-password' \
  oaklight/nps-ctl:latest
```

## Writes

The dashboard is read-only by default. To enable sync, add-edge and
edit/delete actions, pass `--allow-writes`; the entrypoint appends flags to
the default `web` invocation:

```bash
docker run ... oaklight/nps-ctl:latest --allow-writes
```

The container user must be able to write `/config/edges.toml` (the Add edge
action appends to it). Either `chown -R 10001:10001 config` on the host or
run the container with `--user "$(id -u):$(id -g)"`.

## Other commands

Anything passed to the container is executed as `nps-ctl` with
`--config /config/edges.toml` prepended:

```bash
docker run --rm -v "$PWD/config:/config" oaklight/nps-ctl:latest edge status
docker run --rm oaklight/nps-ctl:latest --version
```

## Compose

[`compose.example.yaml`](compose.example.yaml) is a commented starting point:

```bash
docker compose -f docker/compose.example.yaml up -d
```

Environment variables: `IMAGE_TAG`, `NPS_CTL_PORT`, `NPS_CTL_CONFIG`,
`NPS_WEB_USERNAME`, `NPS_WEB_PASSWORD`. Uncomment the `command:` line to run
with `--allow-writes`.

For a local build from the working tree:

```bash
python -m build
LOCAL_WHEEL=$(basename "$(ls dist/*.whl | head -1)") \
  docker compose -f docker/compose.dev.yaml up --build
```

## TLS

The image serves plain HTTP, like the systemd deployment. Terminate TLS in a
reverse proxy (Caddy, nginx, Traefik) in front of the published port; the app
already sends CSP, `X-Frame-Options: DENY`, `Cache-Control: no-store`, and
`nosniff`.

## Building the binary images

The binary images use Nuitka output; build it first:

```bash
make build-binary          # glibc
make build-binary-musl     # musl (Docker required)
make build-docker-alpine   # or: make build-docker-glibc
```

See `make help` for the Docker targets. The release workflow
(`.github/workflows/docker.yml`) builds and pushes every variant for amd64
and arm64, and runs each image's `--version` as a smoke test.
