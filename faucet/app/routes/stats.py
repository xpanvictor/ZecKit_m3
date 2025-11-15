"""
ZecKit Faucet - Statistics Endpoint
Provides faucet usage statistics
"""
from flask import Blueprint, jsonify, current_app
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

stats_bp = Blueprint('stats', __name__)


@stats_bp.route('/stats', methods=['GET'])
def get_stats():
    """
    Get faucet statistics
    
    Returns:
        200: Statistics
        503: Wallet not available
    """
    wallet = current_app.faucet_wallet
    
    if not wallet or not wallet.is_loaded():
        return jsonify({
            "error": "Faucet wallet not available",
            "code": "FAUCET_UNAVAILABLE"
        }), 503
    
    # Get wallet stats
    wallet_stats = wallet.get_stats()
    
    # Calculate additional metrics
    tx_history = wallet.get_transaction_history(limit=1000)
    
    # Get last request timestamp
    last_request = None
    if tx_history:
        last_request = tx_history[-1].get('timestamp')
    
    stats = {
        "faucet_address": wallet_stats['address'],
        "current_balance": wallet_stats['current_balance'],
        "total_requests": wallet_stats['total_transactions'],
        "total_sent": wallet_stats['total_sent'],
        "created_at": wallet_stats['created_at'],
        "last_request": last_request,
        "uptime": "N/A",  # TODO: Track app start time
        "version": "0.1.0"
    }
    
    return jsonify(stats), 200


@stats_bp.route('/history', methods=['GET'])
def get_history():
    """
    Get recent transaction history
    
    Query Parameters:
        limit: Number of transactions to return (default: 100, max: 1000)
    
    Returns:
        200: Transaction history
        503: Wallet not available
    """
    wallet = current_app.faucet_wallet
    
    if not wallet or not wallet.is_loaded():
        return jsonify({
            "error": "Faucet wallet not available",
            "code": "FAUCET_UNAVAILABLE"
        }), 503
    
    # Get limit from query params
    from flask import request
    try:
        limit = int(request.args.get('limit', 100))
        limit = min(max(1, limit), 1000)  # Clamp between 1-1000
    except ValueError:
        limit = 100
    
    history = wallet.get_transaction_history(limit=limit)
    
    return jsonify({
        "count": len(history),
        "limit": limit,
        "transactions": history
    }), 200