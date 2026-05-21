FROM python:3.12-slim

RUN useradd --system --uid 1001 --home-dir /app --no-create-home hermes \
 && mkdir -p /app /data /logs \
 && chown -R hermes:hermes /app /data /logs

WORKDIR /app
COPY agent.py /app/agent.py
USER hermes

EXPOSE 8443
ENV HERMES_BIND_ADDR=0.0.0.0 \
    HERMES_PORT=8443 \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "/app/agent.py"]
