# ---- Build stage: install Python dependencies ----
FROM python:3.13-slim AS build

WORKDIR /wheels
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir --wheel-dir=/wheels -r /requirements.txt

# ---- Runtime stage ----
FROM python:3.13-slim

WORKDIR /srv/blast

# Copy the installed wheels.
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Copy the application.
COPY app ./app
COPY bin ./bin
COPY config ./config

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BANKS_CONFIG=/srv/blast/config/banks.yml \
    LINKS_CONFIG=/srv/blast/config/links.yml

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
