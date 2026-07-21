"""Load .env file and resolve ${ENV_VAR} references in config."""

import logging
import os
from pathlib import Path

logger = logging.getLogger("vesper.secrets")

ENV_FILE = Path(__file__).parent.parent / ".env"


def load_secrets():
    """Load .env into os.environ. Does not override existing env vars."""
    if not ENV_FILE.exists():
        logger.warning("No .env file found. Using environment variables only.")
        return

    loaded = 0
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = value
                loaded += 1

    logger.info("Loaded %d secrets from .env", loaded)


def resolve_env_refs(config):
    """Recursively replace ${ENV_VAR} strings with os.environ values."""
    if isinstance(config, dict):
        return {k: resolve_env_refs(v) for k, v in config.items()}
    if isinstance(config, list):
        return [resolve_env_refs(v) for v in config]
    if isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        key = config[2:-1]
        val = os.environ.get(key, "")
        if not val:
            logger.warning("Environment variable %s is not set", key)
        return val
    return config