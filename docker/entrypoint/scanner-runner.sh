#!/bin/sh
set -eu

exec /opt/netbox/venv/bin/python /usr/local/bin/scanner_scheduler.py
