# Expense & Reimbursement Agent: container image for hosting the demo.
#   docker build -t expense-agent .
#   docker run --rm -p 8000:8000 --env-file .env -v expense-runtime:/app/backend/runtime expense-agent
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1

WORKDIR /app

# Dependencies first so this layer is cached when only the code changes.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend
COPY data data
COPY tools tools

# Run as an unprivileged user; backend/runtime holds uploads, the finance SQLite file and the runtime policy copy.
RUN useradd --create-home appuser && mkdir -p backend/runtime && chown -R appuser /app
USER appuser

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
