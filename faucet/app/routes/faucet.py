"""
ZecKit Faucet - Funding Request Endpoint
Handles POST /request for funding test addresses
"""
from flask import Blueprint, jsonify, request, current_app
from datetime import datetime
import logging
import re

from ..zebra_rpc import ZebraRPCError

logger = logging.getLogger(__name__)

faucet_bp = Blueprint('faucet', __name__)


def validate_address(address: str) -> tuple[bool, str]:
    """
    Validate Zcash address format
    
    Args:
        address: Address to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not address:
        return False, "Address is required"
    
    # Basic format validation
    # Transparent: t1 or t3 (mainnet), tm (testnet/regtest)
    # Shielded Sapling: zs1
    # Unified: u1
    
    if address.startswith('t'):
        # Transparent address
        if not re.match(r'^t[13m][a-zA-Z0-9]{33}$', address):
            return False, "Invalid transparent address format"
    elif address.startswith('zs1'):
        # Sapling address
        if len(address) < 78:
            return False, "Invalid sapling address format"
    elif address.startswith('u1'):
        # Unified address
        if len(address) < 100:
            return False, "Invalid unified address format"
    else:
        return False, "Unsupported address type (must be t, zs1, or u1)"
    
    return True, ""


@faucet_bp.route('/request', methods=['POST'])
def request_funds():
    """
    Request test funds from faucet
    
    Request Body:
        {
            "address": "t1abc...",
            "amount": 10.0  // optional, default from config
        }
    
    Returns:
        200: Success with txid
        400: Invalid request
        429: Rate limit exceeded
        503: Faucet unavailable
    """
    # Get request data
    data = request.get_json()
    if not data:
        return jsonify({
            "error": "Invalid JSON",
            "code": "INVALID_JSON"
        }), 400
    
    # Validate address
    to_address = data.get('address')
    is_valid, error_msg = validate_address(to_address)
    if not is_valid:
        return jsonify({
            "error": error_msg,
            "code": "INVALID_ADDRESS"
        }), 400
    
    # Get amount (with validation)
    try:
        amount = float(data.get('amount', current_app.config['FAUCET_AMOUNT_DEFAULT']))
        
        min_amount = current_app.config['FAUCET_AMOUNT_MIN']
        max_amount = current_app.config['FAUCET_AMOUNT_MAX']
        
        if amount < min_amount or amount > max_amount:
            return jsonify({
                "error": f"Amount must be between {min_amount} and {max_amount} ZEC",
                "code": "INVALID_AMOUNT"
            }), 400
    
    except (ValueError, TypeError):
        return jsonify({
            "error": "Invalid amount",
            "code": "INVALID_AMOUNT"
        }), 400
    
    # Check faucet is ready
    wallet = current_app.faucet_wallet
    if not wallet or not wallet.is_loaded():
        return jsonify({
            "error": "Faucet wallet not available",
            "code": "FAUCET_UNAVAILABLE"
        }), 503
    
    # Check balance
    balance = wallet.get_balance()
    if balance < amount:
        return jsonify({
            "error": f"Insufficient faucet balance (available: {balance} ZEC)",
            "code": "INSUFFICIENT_BALANCE"
        }), 503
    
    # Send funds
    try:
        logger.info(f"Processing funding request: {amount} ZEC to {to_address}")
        
        txid = wallet.send_funds(
            to_address=to_address,
            amount=amount,
            memo=data.get('memo')
        )
        
        if not txid:
            return jsonify({
                "error": "Failed to send transaction",
                "code": "TRANSACTION_FAILED"
            }), 500
        
        # Success response
        response = {
            "txid": txid,
            "address": to_address,
            "amount": amount,
            "status": "sent",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "new_balance": wallet.get_balance()
        }
        
        logger.info(f"✓ Funded {to_address} with {amount} ZEC (txid: {txid})")
        
        return jsonify(response), 200
    
    except ZebraRPCError as e:
        logger.error(f"RPC error: {e}")
        return jsonify({
            "error": f"RPC error: {e.message}",
            "code": "RPC_ERROR"
        }), 500
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500


@faucet_bp.route('/address', methods=['GET'])
def get_faucet_address():
    """
    Get the faucet's receiving address
    Useful for funding the faucet
    
    Returns:
        200: Faucet address
        503: Wallet not loaded
    """
    wallet = current_app.faucet_wallet
    
    if not wallet or not wallet.is_loaded():
        return jsonify({
            "error": "Faucet wallet not available",
            "code": "FAUCET_UNAVAILABLE"
        }), 503
    
    return jsonify({
        "address": wallet.get_address(),
        "balance": wallet.get_balance()
    }), 200


@faucet_bp.route('/admin/add-funds', methods=['POST'])
def admin_add_funds():
    """
    Admin endpoint to manually add funds to faucet
    For development/testing only
    
    Request Body:
        {
            "amount": 1000.0,
            "secret": "dev-secret"  // Required for security
        }
    
    Returns:
        200: Funds added
        401: Unauthorized
        400: Invalid request
    """
    data = request.get_json()
    if not data:
        return jsonify({
            "error": "Invalid JSON",
            "code": "INVALID_JSON"
        }), 400
    
    # Simple secret check (for dev only!)
    secret = data.get('secret')
    if secret != current_app.config.get('SECRET_KEY'):
        return jsonify({
            "error": "Unauthorized",
            "code": "UNAUTHORIZED"
        }), 401
    
    try:
        amount = float(data.get('amount', 0))
        if amount <= 0:
            return jsonify({
                "error": "Amount must be positive",
                "code": "INVALID_AMOUNT"
            }), 400
        
        wallet = current_app.faucet_wallet
        if not wallet or not wallet.is_loaded():
            return jsonify({
                "error": "Faucet wallet not available",
                "code": "FAUCET_UNAVAILABLE"
            }), 503
        
        wallet.add_funds(amount)
        
        return jsonify({
            "success": True,
            "amount_added": amount,
            "new_balance": wallet.get_balance(),
            "message": f"Added {amount} ZEC to faucet"
        }), 200
    
    except Exception as e:
        logger.error(f"Error adding funds: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500