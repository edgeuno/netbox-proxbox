import os
import runpy
import shlex
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from croniter import croniter


DEFAULT_CONFIG_PATH = "/opt/netbox/runtime/scanner.env"
DEFAULT_NETBOX_CONFIG_PATH = "/opt/netbox/netbox/netbox/netbox/configuration.py"
DEFAULT_INTERVAL_SECONDS = 900
DEFAULT_RESTART_DELAY_SECONDS = 0
WAIT_TIMEOUT_SECONDS = 300
WAIT_POLL_SECONDS = 2


def log(message):
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    print(f"[proxbox-runner] {timestamp} {message}", flush=True)


def parse_env_file(path):
    values = {}
    config_path = Path(path)
    if not config_path.exists():
        return values

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def effective_env():
    values = dict(os.environ)
    config_path = values.get("PROXBOX_CONFIG_FILE", values.get("SCANNER_CONFIG_FILE", DEFAULT_CONFIG_PATH))
    values.update(parse_env_file(config_path))
    values["PROXBOX_CONFIG_FILE"] = config_path
    return values


def get_config_value(env, key, default=None):
    proxbox_key = f"PROXBOX_{key}"
    scanner_key = f"SCANNER_{key}"
    return env.get(proxbox_key, env.get(scanner_key, default))


def load_netbox_configuration():
    candidates = (
        os.environ.get("NETBOX_CONFIGURATION_FILE"),
        "/opt/netbox/netbox/netbox/netbox/configuration.py",
        "/opt/netbox/netbox/netbox/configuration.py",
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            config = runpy.run_path(candidate)
            config["_CONFIG_FILE"] = candidate
            return config
    raise RuntimeError("Unable to locate NetBox configuration.py")


def parse_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def wait_for_socket(host, port, label):
    log(f"waiting for {label} on {host}:{port}")
    deadline = time.time() + WAIT_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                log(f"{label} is reachable on {host}:{port}")
                return
        except OSError:
            time.sleep(WAIT_POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for {label} on {host}:{port}")


def wait_for_dependencies():
    netbox_config = load_netbox_configuration()
    database = netbox_config.get("DATABASE", {})
    redis = netbox_config.get("REDIS", {})
    db_host = database.get("HOST")
    db_port = parse_int(database.get("PORT"), 5432)
    redis_tasks = redis.get("tasks", {})
    redis_cache = redis.get("caching", {})
    redis_host = redis_tasks.get("HOST")
    redis_port = parse_int(redis_tasks.get("PORT"), 6379)
    redis_cache_host = redis_cache.get("HOST", redis_host)
    redis_cache_port = parse_int(redis_cache.get("PORT"), redis_port)

    log(f"loaded NetBox config from: {netbox_config.get('_CONFIG_FILE', DEFAULT_NETBOX_CONFIG_PATH)}")
    if db_host:
        wait_for_socket(db_host, db_port, "database")
    if redis_host:
        wait_for_socket(redis_host, redis_port, "redis tasks")
    if redis_cache_host:
        wait_for_socket(redis_cache_host, redis_cache_port, "redis cache")


def run_scanner_once():
    env = effective_env()
    command = ["/usr/local/bin/proxbox_runner.sh"]
    log("------------------------------------------------------------")
    log("starting proxbox sync run")
    log(f"command: {' '.join(command)}")
    result = subprocess.run(command, check=False)
    log(f"proxbox sync finished with exit code {result.returncode}")
    log("execution cycle completed")
    log("------------------------------------------------------------")
    return result.returncode


def sleep_until(timestamp):
    while True:
        remaining = timestamp - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 1))


def run_off_mode():
    log("running off-mode implementation")
    log("PROXBOX_MODE=off; scheduler is idle")
    while True:
        time.sleep(3600)


def run_continuous_mode():
    log("running continuous-mode implementation")
    while True:
        env = effective_env()
        restart_delay = parse_int(
            get_config_value(env, "RESTART_DELAY_SECONDS"),
            DEFAULT_RESTART_DELAY_SECONDS,
        )
        run_scanner_once()
        if restart_delay > 0:
            log(f"sleeping {restart_delay}s before next continuous run")
            time.sleep(restart_delay)
        else:
            log("no restart delay configured; starting next continuous run immediately")


def run_interval_mode():
    log("running interval-mode implementation")
    while True:
        env = effective_env()
        interval_seconds = parse_int(
            get_config_value(env, "INTERVAL_SECONDS"),
            DEFAULT_INTERVAL_SECONDS,
        )
        run_scanner_once()
        if interval_seconds > 0:
            log(f"sleeping {interval_seconds}s before next interval run")
            time.sleep(interval_seconds)
        else:
            log("interval is 0s; starting next interval run immediately")


def run_cron_mode():
    log("running cron-mode implementation")
    while True:
        env = effective_env()
        expression = get_config_value(env, "CRON_EXPRESSION", "").strip()
        if not expression:
            raise RuntimeError("PROXBOX_CRON_EXPRESSION is required when PROXBOX_MODE=cron")
        base = datetime.now().astimezone()
        next_run = croniter(expression, base).get_next(datetime)
        log(
            "next cron run scheduled for "
            f"{next_run.isoformat(timespec='seconds')} using {shlex.quote(expression)}"
        )
        sleep_until(next_run.timestamp())
        run_scanner_once()


def main():
    log("proxbox scheduler starting")
    env = effective_env()
    raw_mode = get_config_value(env, "MODE", "off")
    mode = raw_mode.strip().lower()
    log(f"loaded scheduler config from: {env.get('PROXBOX_CONFIG_FILE', DEFAULT_CONFIG_PATH)}")
    log(f"PROXBOX_MODE raw value: {raw_mode!r}")
    log(f"PROXBOX_MODE normalized value: {mode}")
    wait_for_dependencies()

    if mode == "off":
        run_off_mode()
    if mode == "continuous":
        run_continuous_mode()
    if mode == "interval":
        run_interval_mode()
    if mode == "cron":
        run_cron_mode()
    raise RuntimeError(f"Unsupported PROXBOX_MODE: {mode}")


if __name__ == "__main__":
    main()
