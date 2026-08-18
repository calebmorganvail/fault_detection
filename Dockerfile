FROM python:3.12-slim

# uv replaces pip in v3, so pull the binary straight from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

COPY server/ server/
COPY dashboard/ dashboard/
COPY pi/ pi/

# SQLite lives on a mounted volume so readings survive a restart.
ENV DB_PATH=/app/data/readings.db

EXPOSE 5001

CMD ["python", "server/server.py"]
