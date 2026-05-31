FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

RUN useradd -m -u 1000 fitops

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 https://github.com/BrunoV21/FitOps-CLI.git /app && \
    pip install --no-cache-dir -e "/app[server]"

USER 1000

EXPOSE 7860

CMD ["uvicorn", "fitops.cloud.deploy_api:app", "--host", "0.0.0.0", "--port", "7860"]
