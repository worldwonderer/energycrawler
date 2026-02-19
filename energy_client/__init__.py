"""
Energy Browser Client Package

A Python client library for the Energy Browser Service,
providing browser automation capabilities through gRPC.
"""

from .client import BrowserClient, Cookie
from .browser_interface import (
    BrowserInterface,
    EnergyBrowserBackend,
    create_browser_backend
)

__version__ = '0.1.0'
__all__ = [
    'BrowserClient',
    'Cookie',
    'BrowserInterface',
    'EnergyBrowserBackend',
    'create_browser_backend',
]
