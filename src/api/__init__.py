# src/api/__init__.py
# API package initialization
# RESTful API routes for metrics, predictions, alerts, and system endpoints
# Implements authentication, rate limiting, and request validation

from .routes import metrics, predictions, alerts, system

__all__ = ['metrics', 'predictions', 'alerts', 'system']
