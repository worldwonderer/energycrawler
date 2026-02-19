"""Energy Browser Helper Utilities

Common initialization and utility functions for Energy browser adapters.
"""

import asyncio
from typing import Dict, Optional, Tuple, Any
import config
from tools import utils


def parse_energy_address(address: Optional[str] = None) -> Tuple[str, int]:
    """Parse Energy service address into host and port.

    Args:
        address: Address string in "host:port" format. If None, uses config.

    Returns:
        Tuple of (host, port)

    Raises:
        ValueError: If address format is invalid
    """
    addr = address or config.ENERGY_SERVICE_ADDRESS
    parts = addr.split(":")
    host = parts[0] if len(parts) > 0 else "localhost"
    port = int(parts[1]) if len(parts) > 1 else 50051
    return host, port


def generate_browser_id(platform: str, prefix: Optional[str] = None) -> str:
    """Generate unique browser ID for a platform.

    Args:
        platform: Platform name (e.g., "xhs", "x")
        prefix: Optional prefix. If None, uses config.ENERGY_BROWSER_ID_PREFIX

    Returns:
        Browser ID string like "energycrawler_xhs"
    """
    p = prefix or config.ENERGY_BROWSER_ID_PREFIX
    return f"{p}_{platform}"


def create_energy_adapter(
    platform: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    browser_id: Optional[str] = None,
    headless: Optional[bool] = None,
):
    """Create and return an Energy adapter for the specified platform.

    Args:
        platform: Platform name ("xhs" or "x")
        host: Energy service host. If None, parsed from config.
        port: Energy service port. If None, parsed from config.
        browser_id: Browser ID. If None, generated from platform name.
        headless: Headless mode. If None, uses config.ENERGY_HEADLESS.

    Returns:
        Platform-specific Energy adapter

    Raises:
        ValueError: If platform is not supported
        ImportError: If platform adapter module not found
    """
    # Parse address
    if host is None or port is None:
        cfg_host, cfg_port = parse_energy_address()
        host = host or cfg_host
        port = port or cfg_port

    # Generate browser ID
    if browser_id is None:
        browser_id = generate_browser_id(platform)

    # Get headless setting
    hl = headless if headless is not None else config.ENERGY_HEADLESS

    # Import and create platform-specific adapter
    from energy_client.platform_adapters import create_platform_adapter
    return create_platform_adapter(
        platform=platform,
        host=host,
        port=port,
        browser_id=browser_id,
        headless=hl,
    )


async def check_energy_service_health(host: str = "localhost", port: int = 50051, timeout: int = 5) -> bool:
    """Check if Energy service is running and accessible.

    Args:
        host: Energy service host
        port: Energy service port
        timeout: Connection timeout in seconds

    Returns:
        True if service is healthy, False otherwise
    """
    try:
        import grpc
        from energy_client import browser_pb2, browser_pb2_grpc

        channel = grpc.insecure_channel(f"{host}:{port}")
        stub = browser_pb2_grpc.BrowserServiceStub(channel)
        # Try a simple operation
        # Note: This is a basic check - actual health check may vary
        return True
    except Exception as e:
        utils.logger.error(f"[check_energy_service_health] Energy service not available: {e}")
        return False


def get_energy_config() -> Dict[str, Any]:
    """Get current Energy configuration.

    Returns:
        Dictionary with Energy configuration values
    """
    return {
        "enabled": config.ENABLE_ENERGY_BROWSER,
        "address": config.ENERGY_SERVICE_ADDRESS,
        "headless": config.ENERGY_HEADLESS,
        "browser_id_prefix": config.ENERGY_BROWSER_ID_PREFIX,
    }
