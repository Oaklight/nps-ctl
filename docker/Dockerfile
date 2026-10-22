# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12
ARG REGISTRY_MIRROR
FROM ${REGISTRY_MIRROR:-docker.io}/python:${PYTHON_VERSION}-slim

# Install source: PyPI (PACKAGE_VERSION), TestPyPI (EXTRA_INDEX_URL), or a
# wheel placed in dist/ (LOCAL_WHEEL).
ARG PYPI_MIRROR=""
ARG EXTRA_INDEX_URL=""
ARG LOCAL_WHEEL=""
ARG PACKAGE_VERSION=""

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --uid "${UID}" \
    appuser

RUN mkdir -p /tmp/dist/
COPY dist/ /tmp/dist/

RUN set -eu; \
    PIP_FLAGS="--no-cache-dir"; \
    if [ -n "$PYPI_MIRROR" ]; then \
        PIP_FLAGS="$PIP_FLAGS -i $PYPI_MIRROR"; \
    fi; \
    if [ -n "$LOCAL_WHEEL" ] && [ -f "/tmp/dist/$LOCAL_WHEEL" ]; then \
        echo "Installing local wheel: $LOCAL_WHEEL"; \
        pip install $PIP_FLAGS "/tmp/dist/$LOCAL_WHEEL"; \
    elif [ -n "$EXTRA_INDEX_URL" ] && [ -n "$PACKAGE_VERSION" ]; then \
        echo "Installing nps-ctl==$PACKAGE_VERSION from $EXTRA_INDEX_URL"; \
        pip install $PIP_FLAGS --extra-index-url "$EXTRA_INDEX_URL" \
            --no-deps "nps-ctl==$PACKAGE_VERSION"; \
        pip install $PIP_FLAGS "nps-ctl==$PACKAGE_VERSION"; \
    elif [ -n "$PACKAGE_VERSION" ]; then \
        echo "Installing nps-ctl==$PACKAGE_VERSION from PyPI"; \
        pip install $PIP_FLAGS "nps-ctl==$PACKAGE_VERSION"; \
    else \
        echo "Installing latest nps-ctl from PyPI"; \
        pip install $PIP_FLAGS nps-ctl; \
    fi; \
    rm -rf /tmp/dist/

# Fail the build if the package is missing. Without this a pip failure could
# leave an image with no nps-ctl at all.
RUN nps-ctl --version

RUN mkdir -p /config && chown appuser:appuser /config

VOLUME /config

COPY --chmod=755 docker/entrypoint.sh /entrypoint.sh

USER appuser

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
