"""Faucet API Routes Package"""
from .health import health_bp
from .faucet import faucet_bp
from .stats import stats_bp

__all__ = ['health_bp', 'faucet_bp', 'stats_bp']