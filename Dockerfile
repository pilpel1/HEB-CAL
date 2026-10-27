# syntax=docker/dockerfile:1
# תמונה אחת לאפליקציה, ל-reminder_worker, ול-gcal_sync_worker.
# סודות לא נכנסים לבנייה: אין COPY של .env, ואין ARG לטוקן.

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH" \
    FLASK_APP=app \
    FLASK_DEBUG=0 \
    HEB_CAL_DOCKER=1 \
    HEB_CAL_UPDATE_MODE=docker \
    TZ=Asia/Jerusalem \
    LANG=C.UTF-8

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 hebcal \
    && useradd --uid 1000 --gid 1000 --home-dir /app --no-create-home --shell /bin/sh hebcal

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY scripts ./scripts
COPY VERSION CHANGELOG.md ./
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod 755 /entrypoint.sh \
    && mkdir -p /app/data /app/logs /app/backups \
    && chown hebcal:hebcal /app/data /app/logs /app/backups

LABEL org.opencontainers.image.source="https://github.com/pilpel1/HEB-CAL" \
      org.opencontainers.image.url="https://github.com/pilpel1/HEB-CAL" \
      org.opencontainers.image.title="heb-cal" \
      org.opencontainers.image.description="Hebrew-Gregorian household calendar"

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000", "--no-reload", "--no-debugger"]
