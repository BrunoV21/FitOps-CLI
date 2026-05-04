FROM python:3.12-slim

RUN useradd -m -u 1000 fitops && \
    mkdir -p /home/fitops/.fitops && \
    chown fitops:fitops /home/fitops/.fitops

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/BrunoV21/FitOps-CLI.git /app && \
    pip install --no-cache-dir -e "/app[server]"

COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

USER 1000
ENV HOME=/home/fitops

EXPOSE 7860

CMD ["/startup.sh"]
