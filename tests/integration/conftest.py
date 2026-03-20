# tests/integration/conftest.py
import os
import pytest
from dotenv import load_dotenv

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.utils.config import AuthConfig, AuthType, BasicAuthConfig, ServerConfig

# Load .env from the project root (servicenow-mcp/)
load_dotenv()


def _build_config() -> ServerConfig:
    """Build a real ServerConfig from environment variables."""
    instance_url = os.environ.get("SERVICENOW_INSTANCE_URL", "").rstrip("/")
    username = os.environ.get("SERVICENOW_USERNAME", "")
    password = os.environ.get("SERVICENOW_PASSWORD", "")

    if not all([instance_url, username, password]):
        pytest.skip(
            "Integration test requires SERVICENOW_INSTANCE_URL, "
            "SERVICENOW_USERNAME, and SERVICENOW_PASSWORD env vars."
        )

    auth = AuthConfig(
        type=AuthType.BASIC,
        basic=BasicAuthConfig(username=username, password=password),
    )
    return ServerConfig(instance_url=instance_url, auth=auth)


@pytest.fixture(scope="session")
def live_config() -> ServerConfig:
    """Real ServerConfig loaded from environment variables."""
    return _build_config()


@pytest.fixture(scope="session")
def live_auth(live_config) -> AuthManager:
    """Real AuthManager for the live instance."""
    return AuthManager(live_config.auth)


@pytest.fixture(scope="session")
def pdi_guard(live_config):
    """
    Guard fixture for write tests — refuses to run against non-PDI instances.
    Add this fixture to any test that creates or modifies records.
    """
    url = live_config.instance_url
    if "dev" not in url:
        pytest.skip(
            f"Write integration tests only run against a PDI (dev*.service-now.com). "
            f"Current instance: {url}"
        )
    return live_config
