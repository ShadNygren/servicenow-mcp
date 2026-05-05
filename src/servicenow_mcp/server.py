"""ServiceNow MCP Server — FastMCP-based.

Phase 8 migration: replaces the previous ``mcp.server.lowlevel.Server``
implementation with :class:`mcp.server.fastmcp.FastMCP`.  Tools are still
registered through the central :func:`servicenow_mcp.utils.tool_utils.get_tool_definitions`
registry (kept as the canonical list of ~200 ServiceNow tools), but each entry
is adapted into a FastMCP-compatible wrapper at startup via
:func:`servicenow_mcp.utils.fastmcp_adapter.register_tool` so the underlying tool
functions don't need rewriting.

Tool packaging via the ``MCP_TOOL_PACKAGE`` environment variable still drives
which subset of tools is registered — selection now happens at *startup* (before
``add_tool`` is called) instead of at ``list_tools`` request time.

Resources (``servicenow://tables``, ``servicenow://tables/{table}``,
``servicenow://schema/{table}``) are now registered with FastMCP's
``@resource`` decorator pattern.
"""

import logging
import os
import sys
from typing import Any, Dict, List, Union

# Import importlib.resources for package resource loading
if sys.version_info >= (3, 9):
    from importlib.resources import files
else:
    try:
        from importlib_resources import files
    except ImportError:
        files = None

import yaml
from mcp.server.fastmcp import FastMCP

from servicenow_mcp.auth.auth_manager import AuthManager
from servicenow_mcp.resources.schema import SchemaResources
from servicenow_mcp.tools.knowledge_base import (
    create_category as create_kb_category_tool,
)
from servicenow_mcp.tools.knowledge_base import (
    list_categories as list_kb_categories_tool,
)
from servicenow_mcp.utils.config import ServerConfig
from servicenow_mcp.utils.fastmcp_adapter import register_tool
from servicenow_mcp.utils.tool_utils import get_tool_definitions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default location of the YAML that defines tool packages.  Overridable
# via env var (preserves the prior MCP_TOOL_PACKAGE_CONFIG_PATH escape hatch).
TOOL_PACKAGE_CONFIG_PATH = os.getenv("TOOL_PACKAGE_CONFIG_PATH", "config/tool_packages.yaml")


class ServiceNowMCP:
    """ServiceNow MCP Server — FastMCP-based since Phase 8.

    The class still owns ``ServerConfig``, ``AuthManager``, the
    ``MCP_TOOL_PACKAGE`` filter, and the schema-discovery resources.  It now
    wraps a :class:`FastMCP` instance instead of a low-level ``Server``.
    """

    def __init__(self, config: Union[Dict, ServerConfig]):
        if isinstance(config, dict):
            self.config = ServerConfig(**config)
        else:
            self.config = config

        self.auth_manager = AuthManager(self.config.auth, self.config.instance_url)
        self.mcp = FastMCP("ServiceNow")
        self.name = "ServiceNow"

        self.package_definitions: Dict[str, List[str]] = {}
        self.enabled_tool_names: List[str] = []
        self.current_package_name: str = "none"
        self._load_package_config()
        self._determine_enabled_tools()

        self.tool_definitions = get_tool_definitions(
            create_kb_category_tool, list_kb_categories_tool
        )

        self.schema_resources = SchemaResources(self.config, self.auth_manager)

        self._register_introspection_tool()
        self._register_tools()
        self._register_resources()

    @property
    def mcp_server(self) -> FastMCP:
        """Backward-compatible alias for tests/code that still references ``.mcp_server``."""
        return self.mcp

    def _load_package_config(self) -> None:
        """Load tool package definitions from the YAML configuration file.

        Supports both package installations (uvx/pip via importlib.resources)
        and development mode (file path fallback).
        """
        config_loaded = False

        if files is not None:
            try:
                config_file = files("servicenow_mcp").joinpath("config/tool_packages.yaml")
                with config_file.open("r") as f:
                    loaded_config = yaml.safe_load(f)
                    if isinstance(loaded_config, dict):
                        self.package_definitions = loaded_config
                        logger.info("Loaded tool package config from package resources")
                        config_loaded = True
                    else:
                        logger.error(
                            "Invalid format in package resources config: expected dict, got %s",
                            type(loaded_config),
                        )
            except (FileNotFoundError, ModuleNotFoundError, AttributeError) as e:
                logger.debug("Could not load from package resources: %s. Trying file path.", e)
        else:
            try:
                import pkg_resources  # type: ignore[import-not-found]
                config_path = pkg_resources.resource_filename(
                    "servicenow_mcp", "config/tool_packages.yaml"
                )
                with open(config_path, "r") as f:
                    loaded_config = yaml.safe_load(f)
                    if isinstance(loaded_config, dict):
                        self.package_definitions = loaded_config
                        logger.info("Loaded tool package config from pkg_resources")
                        config_loaded = True
            except Exception as e:
                logger.debug("Could not load from pkg_resources: %s. Trying file path.", e)

        if not config_loaded:
            config_path = TOOL_PACKAGE_CONFIG_PATH
            if not os.path.isabs(config_path):
                config_path = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "..", config_path)
                )
            try:
                with open(config_path, "r") as f:
                    loaded_config = yaml.safe_load(f)
                    if isinstance(loaded_config, dict):
                        self.package_definitions = loaded_config
                        logger.info("Loaded tool package config from %s", config_path)
                        config_loaded = True
                    else:
                        logger.error(
                            "Invalid format in %s: expected dict, got %s",
                            config_path,
                            type(loaded_config),
                        )
            except FileNotFoundError:
                logger.error("Tool package config not found at %s", config_path)
            except yaml.YAMLError as e:
                logger.error("Error parsing %s: %s", config_path, e)
            except Exception as e:
                logger.error("Unexpected error loading %s: %s", config_path, e)

        if not config_loaded:
            self.package_definitions = {}

    def _determine_enabled_tools(self) -> None:
        """Apply MCP_TOOL_PACKAGE to pick the enabled tool subset."""
        requested_package = os.getenv("MCP_TOOL_PACKAGE", "full").strip()

        if not requested_package:
            self.current_package_name = "full"
            logger.info("MCP_TOOL_PACKAGE empty, defaulting to 'full'.")
        elif requested_package in self.package_definitions:
            self.current_package_name = requested_package
            logger.info("MCP_TOOL_PACKAGE set to '%s'.", self.current_package_name)
        else:
            self.current_package_name = "none"
            logger.warning(
                "MCP_TOOL_PACKAGE '%s' is not a valid package name. "
                "Valid: %s. Loading 'none'.",
                requested_package,
                list(self.package_definitions.keys()),
            )

        if self.package_definitions:
            self.enabled_tool_names = self.package_definitions.get(self.current_package_name, [])
        else:
            self.enabled_tool_names = []

        logger.info(
            "Loading package '%s' with %d tools.",
            self.current_package_name,
            len(self.enabled_tool_names),
        )

    def _register_introspection_tool(self) -> None:
        """Expose ``list_tool_packages`` so the LLM can discover the package layout.

        Suppressed when the loaded package is ``none`` (no tools at all).
        """
        if self.current_package_name == "none":
            return

        package_definitions = self.package_definitions
        current_package_name = self.current_package_name

        @self.mcp.tool(
            name="list_tool_packages",
            description="Lists available tool packages and the currently loaded one.",
        )
        def list_tool_packages() -> Dict[str, Any]:
            available = list(package_definitions.keys())
            return {
                "current_package": current_package_name,
                "available_packages": available,
                "message": (
                    f"Currently loaded package: '{current_package_name}'. "
                    f"Set MCP_TOOL_PACKAGE env var to one of {available} to switch."
                ),
            }

    def _register_tools(self) -> None:
        """Register every enabled tool with FastMCP."""
        registered = 0
        for tool_name in self.enabled_tool_names:
            definition = self.tool_definitions.get(tool_name)
            if definition is None:
                logger.warning(
                    "Tool '%s' listed in package '%s' but not found in registry.",
                    tool_name,
                    self.current_package_name,
                )
                continue
            impl_func, params_model, _return_annotation, description, _serialization = definition
            try:
                register_tool(
                    self.mcp,
                    name=tool_name,
                    description=description,
                    impl=impl_func,
                    params_model=params_model,
                    config=self.config,
                    auth_manager=self.auth_manager,
                )
                registered += 1
            except Exception as e:
                logger.error("Failed to register tool '%s': %s", tool_name, e, exc_info=True)
        logger.info("Registered %d tools with FastMCP.", registered)

    def _register_resources(self) -> None:
        """Register the schema-discovery resources with FastMCP.

        Three URIs are exposed:

        - ``servicenow://tables`` — list of tables on the connected instance.
        - ``servicenow://tables/{table}`` — sample records (limit 10) from a table.
        - ``servicenow://schema/{table}`` — column metadata from sys_dictionary.
        """
        schema_resources = self.schema_resources

        @self.mcp.resource(
            "servicenow://tables",
            name="ServiceNow tables",
            description="List of tables in the connected ServiceNow instance.",
            mime_type="application/json",
        )
        def list_servicenow_tables() -> str:
            return schema_resources.read("servicenow://tables")

        @self.mcp.resource(
            "servicenow://tables/{table}",
            name="ServiceNow table records",
            description="Sample records (limit 10) from the named table.",
            mime_type="application/json",
        )
        def list_servicenow_table_records(table: str) -> str:
            return schema_resources.read(f"servicenow://tables/{table}")

        @self.mcp.resource(
            "servicenow://schema/{table}",
            name="ServiceNow table schema",
            description="Column metadata for the named table from sys_dictionary.",
            mime_type="application/json",
        )
        def get_servicenow_table_schema(table: str) -> str:
            return schema_resources.read(f"servicenow://schema/{table}")

    def start(self) -> FastMCP:
        """Return the configured FastMCP instance.

        Caller is responsible for running the server on the appropriate
        transport — ``cli.py`` uses ``run_stdio_async``; ``server_http.py``
        uses ``streamable_http_app`` mounted under our SecurityMiddleware.
        """
        logger.info(
            "ServiceNowMCP configured on FastMCP. Returning instance for transport runner."
        )
        return self.mcp
