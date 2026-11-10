FROM python:3.11-slim
# git is the product here, not a build tool: the agent clones, diffs and pushes.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# BUILD CONTEXT IS THE REPO ROOT, not code-agent/. The test gate runs the
# REPO's suite, so this image needs every dependency those tests import -
# and it can only reach btc-executor/requirements.txt from the root.
COPY code-agent/requirements.txt ./requirements.txt
COPY btc-executor/requirements.txt ./requirements-executor.txt
# The gated suite's dependencies. Without these the gate cannot RUN, and a
# gate that cannot run refuses everything - which is safe, and useless.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-executor.txt

COPY code-agent/app ./app
COPY code-agent/tests ./tests
COPY code-agent/pytest.ini .
# The agent commits; git refuses without an identity.
RUN git config --global user.email "code-agent@users.noreply.github.com" \
    && git config --global user.name "code-agent" \
    && git config --global --add safe.directory '*'
ENV PORT=8000 WORKDIR=/app/data/repo
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
