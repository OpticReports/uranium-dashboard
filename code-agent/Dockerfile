FROM python:3.11-slim
# git is the product here, not a build tool: the agent clones, diffs and pushes.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
COPY pytest.ini .
# The agent commits; git refuses without an identity.
RUN git config --global user.email "code-agent@users.noreply.github.com" \
    && git config --global user.name "code-agent" \
    && git config --global --add safe.directory '*'
ENV PORT=8000 WORKDIR=/app/data/repo
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
