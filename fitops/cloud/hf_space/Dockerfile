FROM python:3.12-slim

RUN useradd -m -u 1000 fitops && \
    mkdir -p /home/fitops/.fitops && \
    chown fitops:fitops /home/fitops/.fitops

WORKDIR /app

RUN pip install --no-cache-dir "fitops[server]"

COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

USER 1000
ENV HOME=/home/fitops

EXPOSE 7860

CMD ["/startup.sh"]
