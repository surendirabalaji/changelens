FROM python:3.12-slim AS Builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build


RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim AS runtime

# Logs go straight to stdout (no buffering). No .pyc files written at runtime.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user: fixed uid 10001, no home folder, no login shell.
RUN useradd --system --uid 10001 --user-group \
            --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Only the finished venv comes over. No pip cache, no compilers, no build files.
COPY --from=builder /opt/venv /opt/venv

# App code. Files are owned by root and readable by everyone. That is fine,
# because the app never writes to /app. No chown is needed.
COPY main.py ./
COPY changelens/ ./changelens/

# Everything after this line (and the running process) uses the non-root user.
USER 10001:10001

# Documentation only. It does not publish a port.
EXPOSE 8080

# Shell form through sh -c, so ${PORT} is expanded. "exec" replaces the shell
# with uvicorn, so uvicorn becomes PID 1 and receives SIGTERM directly.
# No --workers flag: one worker on purpose (see Code references).
CMD ["sh", "-c", "exec uvicorn changelens.api:app --host 0.0.0.0 --port ${PORT:-8080}"]