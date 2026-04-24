ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ARG NETBOX_VERSION=4.5.8

ENV NETBOX_ROOT=/opt/netbox \
    VIRTUAL_ENV=/opt/netbox/venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/netbox/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libjpeg62-turbo-dev \
        libmagic-dev \
        libpq-dev \
        unzip \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/netbox

RUN python -m venv "${VIRTUAL_ENV}" \
    && mkdir -p /opt/netbox/plugins /opt/netbox/runtime

RUN curl -fsSL -o /tmp/netbox.zip "https://github.com/netbox-community/netbox/archive/refs/tags/v${NETBOX_VERSION}.zip" \
    && unzip -q /tmp/netbox.zip -d /tmp \
    && mv "/tmp/netbox-${NETBOX_VERSION}" /opt/netbox/netbox \
    && rm -f /tmp/netbox.zip

RUN "${VIRTUAL_ENV}/bin/pip" install --upgrade pip wheel setuptools \
    && "${VIRTUAL_ENV}/bin/pip" install --no-cache-dir -r /opt/netbox/netbox/requirements.txt croniter

WORKDIR /opt/netbox/plugins/netbox-proxbox

COPY setup.py pyproject.toml MANIFEST.in README.md /opt/netbox/plugins/netbox-proxbox/
COPY netbox_proxbox /opt/netbox/plugins/netbox-proxbox/netbox_proxbox
COPY proxbox_runner.sh /usr/local/bin/proxbox_runner.sh
COPY docker/entrypoint/scanner-runner.sh /usr/local/bin/scanner-runner.sh
COPY docker/entrypoint/scanner_scheduler.py /usr/local/bin/scanner_scheduler.py

RUN "${VIRTUAL_ENV}/bin/pip" install --no-cache-dir -e /opt/netbox/plugins/netbox-proxbox \
    && chmod +x /usr/local/bin/proxbox_runner.sh /usr/local/bin/scanner-runner.sh \
    && mkdir -p /opt/netbox/netbox/media

RUN cd /opt/netbox/plugins/netbox-proxbox/ && python setup.py install

WORKDIR /opt/netbox/netbox
