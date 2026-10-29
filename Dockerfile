# ---- Build stage: build Python wheels ----
FROM python:3.13-slim AS build

WORKDIR /wheels
COPY requirements.txt /requirements.txt
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r /requirements.txt

# ---- Runtime stage ----
FROM python:3.13-slim

WORKDIR /srv/blast
# Install from the prebuilt wheels only.
COPY requirements.txt /requirements.txt
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r /requirements.txt

# Copy the application.
COPY app ./app
COPY bin ./bin
COPY config ./config

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BANKS_CONFIG=/srv/blast/config/banks.yml \
    LINKS_CONFIG=/srv/blast/config/links.yml \
    APP_USER='blast' \
    APP_GROUP='blast' \
    UID='' \
    GID=''

EXPOSE 8000

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
