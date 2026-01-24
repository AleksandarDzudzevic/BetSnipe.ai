"""
BetSnipe.ai v2.0 API Module

FastAPI-based REST API and WebSocket server.
"""

from .main import app, create_app

__all__ = ['app', 'create_app']
