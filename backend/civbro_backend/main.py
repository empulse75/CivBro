"""CivBro backend package entry point.

The WebUI hook (scripts/!civbro.py) imports register_routes from here.
"""
from __future__ import annotations

import logging

from .routes import register_routes

__all__ = ["register_routes"]

logger = logging.getLogger("civbro.api")
