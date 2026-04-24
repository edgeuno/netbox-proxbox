#!/bin/bash

# Example:
#   ./portscanner_runner.sh EdgeUno
#   ./portscanner_runner.sh TenantA TenantB

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <tenant> [<tenant> ...]" >&2
    exit 1
fi

MANAGE_PY=""

for candidate in \
    /opt/netbox/netbox/netbox/manage.py \
    /opt/netbox/netbox/manage.py \
    /opt/netbox/netbox/netbox/manage.py
do
    if [ -f "$candidate" ]; then
        MANAGE_PY="$candidate"
        break
    fi
done

if [ -z "$MANAGE_PY" ]; then
    echo "Unable to locate NetBox manage.py" >&2
    exit 1
fi

/opt/netbox/venv/bin/python "$MANAGE_PY" proxboxscrapper
