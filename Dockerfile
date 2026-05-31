# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — builder: sync the locked environment with uv's official image.
#
# We pin to a uv release built on Python 3.14 (matching requires-python) so the
# interpreter baked into the venv lines up with the runtime stage below. The
# build only needs uv, the lockfile, and the source — nothing from this stage
# ships except the resulting /app/.venv.
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim@sha256:d9fb7d2b1c1922d191f1f77cb68b119c0a231f876f3affcce9bfac86e564c20a AS builder

# Fail fast, build a self-contained venv, and never reach back out to PyPI for
# anything not already pinned in uv.lock.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=never

# Git is needed at build time to clone the Litestar repo; the slim uv image
# ships without it. Drop the apt lists afterward so nothing leaks into the
# layer cache (this stage isn't shipped, but keeping it tidy is cheap).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first, against only the lockfile + project metadata, so
# this layer caches across source-only changes. --no-install-project keeps the
# app itself out until its code is present; --no-dev drops the dev/test groups.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Now bring in the source and install the project itself into the same venv.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---------------------------------------------------------------------------
# Stage 2 — runtime: Python's slim image, hardened.
#
# slim is the smallest official Python base with a real interpreter (vs. the
# full image's build toolchain). We harden it further: drop apt lists, run as a
# non-root user, and copy in only the prebuilt venv — no uv, no compilers, no
# source build artifacts.
# ---------------------------------------------------------------------------
FROM python:3.14-slim-trixie@sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97 AS runtime

# Predictable, unbuffered Python; put the venv first on PATH so `uvicorn` and
# the interpreter resolve to the synced environment.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Patch the base image and create an unprivileged user to run as. No package
# manager state or caches are left behind in the final layer.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home --home-dir /app app

WORKDIR /app

# Copy the application and its virtual environment from the builder, owned by
# the unprivileged user. Nothing from the build toolchain comes with it.
COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 8000

# Serve the Litestar app. Bind to all interfaces so the published port is
# reachable from outside the container.
CMD ["uvicorn", "mundane.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
