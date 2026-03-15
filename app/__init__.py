"""
Smart Helmet Application
------------------------
Top-level application entry-point.

Wires together all modules (navigation, localization, embedded,
communication, hardware) and starts the main loop.
"""

from .main import SmartHelmetApp

__all__ = ["SmartHelmetApp"]
