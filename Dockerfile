# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tini ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 spire

WORKDIR /app

# 1. Deps first — cached layer until requirements.txt changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 2. Source, metadata, ports file. personas.yaml is NOT copied —
#    it is bind-mounted at runtime because it rotates weekly.
COPY --chown=spire:spire src/ ./src/
COPY --chown=spire:spire pyproject.toml README.md ./
COPY --chown=spire:spire SPIRE-PORTS.env ./

# 3. Editable install: puts spire / spire-api / spire-ui on PATH while
#    keeping config.py's Path(__file__).parents[2] == /app so that
#    personas.yaml and SPIRE-PORTS.env resolve at runtime.
RUN pip install -e . --no-deps

USER spire
EXPOSE 5000 5001 5002 4001 4002 4003

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "spire.api.server"]
