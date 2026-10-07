FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# Native pronunciation fallback for words outside Prosodic's dictionary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng libespeak-ng1 \
    && rm -rf /var/lib/apt/lists/*
