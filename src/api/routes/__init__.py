# src/api/routes/__init__.py
# API routes package
# Organizes route modules by domain
# Each module handles specific resource endpoints

from . import metrics, predictions, alerts, system

__all__ = ['metrics', 'predictions', 'alerts', 'system']
