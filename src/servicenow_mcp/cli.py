"""
Command-line interface for the ServiceNow MCP server.
"""

import argparse
import logging
import os
import sys

import anyio
from dotenv import load_dotenv

from servicenow_mcp.server import ServiceNowMCP
from servicenow_mcp.utils.config import (
    ApiKeyConfig,
    AuthConfig,
    AuthType,
    BasicAuthConfig,
    OAuthConfig,
    ServerConfig,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="ServiceNow MCP Server")

    # Server configuration
    parser.add_argument(
        "--instance-url",
        help="ServiceNow instance URL (e.g., https://instance.service-now.com)",
        default=os.environ.get("SERVICENOW_INSTANCE_URL"),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
        default=os.environ.get("SERVICENOW_DEBUG", "false").lower() == "true",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="Request timeout in seconds",
        default=int(os.environ.get("SERVICENOW_TIMEOUT", "30")),
    )

    # Authentication
    auth_group = parser.add_argument_group("Authentication")
    auth_group.add_argument(
        "--auth-type",
        choices=["basic", "oauth", "api_key"],
        help="Authentication type",
        default=os.environ.get("SERVICENOW_AUTH_TYPE", "basic"),
    )

    # Basic auth
    basic_group = parser.add_argument_group("Basic Authentication")
    basic_group.add_argument(
        "--username",
        help="ServiceNow username",
        default=os.environ.get("SERVICENOW_USERNAME"),
    )
    basic_group.add_argument(
        "--password",
        help="ServiceNow password",
        default=os.environ.get("SERVICENOW_PASSWORD"),
    )

    # OAuth
    oauth_group = parser.add_argument_group("OAuth Authentication")
    oauth_group.add_argument(
        "--client-id",
        help="OAuth client ID",
        default=os.environ.get("SERVICENOW_CLIENT_ID"),
    )
    oauth_group.add_argument(
        "--client-secret",
        help="OAuth client secret",
        default=os.environ.get("SERVICENOW_CLIENT_SECRET"),
    )
    oauth_group.add_argument(
        "--token-url",
        help="OAuth token URL",
        default=os.environ.get("SERVICENOW_TOKEN_URL"),
    )

    # API Key
    api_key_group = parser.add_argument_group("API Key Authentication")
    api_key_group.add_argument(
        "--api-key",
        help="ServiceNow API key",
        default=os.environ.get("SERVICENOW_API_KEY"),
    )
    api_key_group.add_argument(
        "--api-key-header",
        help="API key header name",
        default=os.environ.get("SERVICENOW_API_KEY_HEADER", "X-ServiceNow-API-Key"),
    )

    # Script execution API resource path
    script_execution_group = parser.add_argument_group("Script Execution API")
    script_execution_group.add_argument(
        "--script-execution-api-resource-path",
        help="Script execution API resource path",
        default=os.environ.get("SCRIPT_EXECUTION_API_RESOURCE_PATH"),
    )

    return parser.parse_args()


def create_config(args) -> ServerConfig:
    """
    Create server configuration from command-line arguments.

    Args:
        args: Command-line arguments.

    Returns:
        ServerConfig: Server configuration.

    Raises:
        ValueError: If required configuration is missing.
    """
    # NOTE: This assumes the ServerConfig model takes instance_url, auth, debug, timeout etc.
    # The ServiceNowMCP class now expects a ServerConfig object matching this.

    # Instance URL validation
    instance_url = args.instance_url
    api_path = os.getenv("SERVICENOW_API_PATH", "api")
    if not instance_url:
        # Attempt to load from .env if not provided via args/env vars directly in parse_args
        instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
        if not instance_url:
            raise ValueError(
                "ServiceNow instance URL is required (--instance-url or SERVICENOW_INSTANCE_URL env var)"
            )

    # Create authentication configuration based on args
    auth_type = AuthType(args.auth_type.lower())
    # This will hold the final AuthConfig instance for ServerConfig
    final_auth_config: AuthConfig

    if auth_type == AuthType.BASIC:
        username = args.username or os.getenv("SERVICENOW_USERNAME")
        password = args.password or os.getenv("SERVICENOW_PASSWORD")  # Get password from arg or env
        if not username or not password:
            raise ValueError(
                "Username and password are required for basic authentication (--username/SERVICENOW_USERNAME, --password/SERVICENOW_PASSWORD)"
            )
        # Create the specific config (without instance_url)
        basic_cfg = BasicAuthConfig(
            username=username,
            password=password,
        )
        # Create the main AuthConfig wrapper
        final_auth_config = AuthConfig(type=auth_type, basic=basic_cfg)

    elif auth_type == AuthType.OAUTH:
        # client_credentials is the recommended (and primary) OAuth grant
        # since Phase 3.1; password grant remains as a fallback when the
        # legacy username+password env vars are set, but is deprecated by
        # OAuth Best Current Practice — see Issue #43 finding #2.
        client_id = args.client_id or os.getenv("SERVICENOW_CLIENT_ID")
        client_secret = args.client_secret or os.getenv("SERVICENOW_CLIENT_SECRET")
        username = args.username or os.getenv("SERVICENOW_USERNAME")
        password = args.password or os.getenv("SERVICENOW_PASSWORD")
        token_url = args.token_url or os.getenv("SERVICENOW_TOKEN_URL")
        resource_url = os.getenv("SERVICENOW_RESOURCE_URL")  # Azure AD-style flows

        if not client_id or not client_secret:
            raise ValueError(
                "OAuth requires client_id and client_secret "
                "(--client-id/SERVICENOW_CLIENT_ID, --client-secret/SERVICENOW_CLIENT_SECRET). "
                "Username and password are optional and only used for the deprecated "
                "password grant fallback."
            )
        if not token_url:
            # Attempt to construct default if not provided
            token_url = f"{instance_url}/oauth_token.do"
            logger.warning(f"OAuth token URL not provided, defaulting to: {token_url}")

        # Create the specific config (without instance_url)
        oauth_cfg = OAuthConfig(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            token_url=token_url,
            resource_url=resource_url,
        )
        # Create the main AuthConfig wrapper
        final_auth_config = AuthConfig(type=auth_type, oauth=oauth_cfg)

    elif auth_type == AuthType.API_KEY:
        api_key = args.api_key or os.getenv("SERVICENOW_API_KEY")
        api_key_header = args.api_key_header or os.getenv(
            "SERVICENOW_API_KEY_HEADER", "X-ServiceNow-API-Key"
        )
        if not api_key:
            raise ValueError(
                "API key is required for API key authentication (--api-key or SERVICENOW_API_KEY)"
            )
        # Create the specific config (without instance_url)
        api_key_cfg = ApiKeyConfig(
            api_key=api_key,
            header_name=api_key_header,
        )
        # Create the main AuthConfig wrapper
        final_auth_config = AuthConfig(type=auth_type, api_key=api_key_cfg)
    else:
        # Should not happen if choices are enforced by argparse
        raise ValueError(f"Unsupported authentication type: {args.auth_type}")

    # Script execution path
    script_execution_api_resource_path = args.script_execution_api_resource_path or os.getenv(
        "SCRIPT_EXECUTION_API_RESOURCE_PATH"
    )
    if not script_execution_api_resource_path:
        logger.warning(
            "Script execution API resource path not set (--script-execution-api-resource-path or SCRIPT_EXECUTION_API_RESOURCE_PATH). ExecuteScriptInclude tool may fail."
        )

    # Create the final ServerConfig
    # Ensure ServerConfig model expects 'auth' as a nested object
    return ServerConfig(
        instance_url=instance_url,  # Add instance_url directly here
        auth=final_auth_config,  # Pass the correctly structured AuthConfig instance
        # Include other server config fields if they exist on ServerConfig model
        debug=args.debug,
        timeout=args.timeout,
        api_path=api_path,
        script_execution_api_resource_path=script_execution_api_resource_path,
    )


async def arun_server(mcp_instance):
    """Run the FastMCP server over the stdio transport."""
    logger.info("Starting FastMCP server with stdio transport...")
    await mcp_instance.run_stdio_async()
    logger.info("Stdio server finished.")


def main():
    """Main entry point for the CLI."""
    # Load environment variables from .env file
    load_dotenv()

    try:
        # Parse command-line arguments
        args = parse_args()

        # Configure logging level based on debug flag
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.info("Debug logging enabled.")
        else:
            logging.getLogger().setLevel(logging.INFO)

        # Create server configuration
        config = create_config(args)
        # Log the instance URL being used (mask sensitive parts of config if needed)
        logger.info(f"Initializing ServiceNow MCP server for instance: {config.instance_url}")

        # Create server controller instance
        mcp_controller = ServiceNowMCP(config)

        # Get the configured FastMCP instance and run on stdio.
        mcp_instance = mcp_controller.start()
        anyio.run(arun_server, mcp_instance)

    except ValueError as e:
        logger.error(f"Configuration or runtime error: {e}")
        sys.exit(1)

    except Exception as e:
        logger.exception(f"Unexpected error starting or running server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
