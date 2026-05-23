FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_CACHE_DIR=/tmp/poetry-cache \
    PATH="/workspace/.venv/bin:$PATH" \
    VIRTUAL_ENV="/workspace/.venv"

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
RUN chown appuser:appuser /workspace

USER appuser

COPY --chown=appuser:appuser pyproject.toml poetry.lock ./

RUN poetry install --no-root --no-ansi \
    && rm -rf "$POETRY_CACHE_DIR"

COPY --chown=appuser:appuser . .

WORKDIR /workspace/django

EXPOSE 8000

ENTRYPOINT ["bash", "/workspace/docker/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
