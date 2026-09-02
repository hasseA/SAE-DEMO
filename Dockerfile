FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    SAE_DEMO_MEMORY_FILE=demo_memory/despair_profile.json

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY LICENSE ./LICENSE
COPY sae_demo ./sae_demo
# The web app currently imports these two public synthetic scenario builders.
COPY tests/fixtures ./tests/fixtures
COPY demo_memory/despair_profile.json ./demo_memory/despair_profile.json

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn sae_demo.web_app:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
