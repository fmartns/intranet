FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry-cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==1.8.4"

RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --shell /bin/bash appuser

WORKDIR /workspace

COPY pyproject.toml poetry.lock ./

RUN poetry install --no-root --no-ansi \
    && rm -rf "$POETRY_CACHE_DIR"

COPY --chown=appuser:appuser . .

RUN chmod +x /workspace/docker/entrypoint.sh

USER appuser

WORKDIR /workspace/django

EXPOSE 8000

ENTRYPOINT ["bash", "/workspace/docker/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
