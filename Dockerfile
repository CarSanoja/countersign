# syntax=docker/dockerfile:1

# Build and runtime are split for one reason: the build needs a git client to
# resolve the autocurricula dependency, and a service that renders vendor files
# has no business shipping a VCS client to production.
FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /build

# README.md is not documentation here: pyproject names it as the long
# description, so the build fails without it.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --prefix=/install .


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY --from=builder /install /usr/local

# Nothing in this image needs to write to it, and a compromised renderer should
# not be able to. The uid is fixed so the layer is reproducible.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin countersign
USER countersign
WORKDIR /home/countersign

EXPOSE 8080

# Shell form, deliberately: Cloud Run injects $PORT and the container has to
# honour whatever it is handed rather than a number baked in here. `exec` leaves
# uvicorn as PID 1, so SIGTERM ends a revision instead of being swallowed by a
# shell that keeps the platform waiting out the grace period.
CMD exec uvicorn countersign.api.main:app --host 0.0.0.0 --port ${PORT:-8080}
