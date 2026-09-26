# One-shot verification image: runs backend tests, the frontend production
# build and a smoke test against the live restoration API.
FROM node:20-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /verify

# Python dependencies (backend runtime + test tooling) in a virtualenv.
COPY api/requirements.txt api/requirements.txt
COPY verify/requirements-verify.txt verify/requirements-verify.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir \
      -r api/requirements.txt \
      -r verify/requirements-verify.txt

# Frontend dependencies (cached unless manifests change).
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci

# Full sources.
COPY api/ api/
COPY web/ web/
COPY verify/ verify/

ENV PATH="/opt/venv/bin:${PATH}" \
    API_BASE_URL="http://web" \
    API_DIRECT_URL="http://api:8000"

CMD ["bash", "verify/run.sh"]
