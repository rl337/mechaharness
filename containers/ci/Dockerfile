# Local stand-in for .github/workflows/ci.yml
# GitHub Actions: ubuntu-latest (Ubuntu 24.04) + actions/setup-python 3.12
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        python3.12 \
        python3.12-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3.12 -m venv /opt/venv \
    && pip install -U pip

WORKDIR /src
COPY entrypoint.sh /usr/local/bin/mechaharness-ci
RUN chmod +x /usr/local/bin/mechaharness-ci

ENTRYPOINT ["/usr/local/bin/mechaharness-ci"]
