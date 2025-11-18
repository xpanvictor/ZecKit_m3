"""
ZecKit Faucet - Main Application with UA Fixtures Support
"""
from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime
import logging
import sys

from .config import get_config
from .zebra_rpc import ZebraRPCClient
from .wallet import FaucetWallet
from .ua_fixtures import UAFixtureManager, initialize_ua_fixtures
from .routes.health import health_bp
from .routes.faucet import faucet_bp
from .routes.stats import stats_bp


def setup_logging(log_level: str = "INFO"):
    """Configure application logging"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def create_app(config_name: str = None) -> Flask:
    """
    Application factory
    
    Args:
        config_name: Configuration environment (development/production/testing)
    
    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    
    # Load configuration
    config = get_config(config_name)
    app.config.from_object(config)
    
    # Setup logging
    setup_logging(app.config['LOG_LEVEL'])
    logger = logging.getLogger(__name__)
    
    # Enable CORS
    CORS(app, origins=app.config['CORS_ORIGINS'])
    
    # Initialize Zebra RPC client
    try:
        app.zebra_client = ZebraRPCClient(
            url=app.config['ZEBRA_RPC_URL'],
            username=app.config.get('ZEBRA_RPC_USER'),
            password=app.config.get('ZEBRA_RPC_PASS'),
            timeout=app.config['ZEBRA_RPC_TIMEOUT']
        )
        
        # Test connection
        if app.zebra_client.ping():
            block_height = app.zebra_client.get_block_count()
            logger.info(f"✓ Connected to Zebra (block height: {block_height})")
        else:
            logger.warning("⚠ Zebra not responding, will retry...")
    
    except Exception as e:
        logger.error(f"Failed to initialize Zebra client: {e}")
        app.zebra_client = None
    
    # Initialize Faucet Wallet
    try:
        if app.zebra_client:
            app.faucet_wallet = FaucetWallet(
                zebra_client=app.zebra_client,
                wallet_file=app.config['WALLET_FILE']
            )
            
            if app.faucet_wallet.is_loaded():
                balance = app.faucet_wallet.get_balance()
                address = app.faucet_wallet.get_address()
                logger.info(f"✓ Faucet wallet loaded")
                logger.info(f"  Address: {address}")
                logger.info(f"  Balance: {balance} ZEC")
                
                # Auto-fund if balance is 0
                if balance == 0:
                    logger.info("Faucet balance is 0, adding initial funds...")
                    app.faucet_wallet.add_funds(
                        amount=1000.0,
                        note="Initial faucet funding"
                    )
                    logger.info(f"✓ Added 1000 ZEC. New balance: {app.faucet_wallet.get_balance()} ZEC")
            else:
                logger.error("Failed to load faucet wallet")
                app.faucet_wallet = None
        else:
            logger.warning("Skipping wallet initialization (Zebra not available)")
            app.faucet_wallet = None
    
    except Exception as e:
        logger.error(f"Failed to initialize faucet wallet: {e}")
        app.faucet_wallet = None
    
    # Initialize UA Fixtures (M2 requirement)
    try:
        if app.zebra_client and app.faucet_wallet:
            logger.info("Initializing Unified Address (ZIP-316) fixtures...")
            app.ua_fixtures = initialize_ua_fixtures(
                zebra_client=app.zebra_client,
                faucet_wallet=app.faucet_wallet
            )
            logger.info(f"✓ UA fixtures ready ({len(app.ua_fixtures.get_all_fixtures())} fixtures)")
        else:
            logger.warning("Skipping UA fixtures (wallet not available)")
            app.ua_fixtures = None
    except Exception as e:
        logger.error(f"Failed to initialize UA fixtures: {e}")
        app.ua_fixtures = None
    
    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(faucet_bp)
    app.register_blueprint(stats_bp)
    
    # Add fixtures endpoint
    @app.route('/fixtures', methods=['GET'])
    def get_fixtures():
        """Get UA fixtures for testing"""
        if not app.ua_fixtures:
            return jsonify({
                "error": "UA fixtures not available",
                "code": "FIXTURES_UNAVAILABLE"
            }), 503
        
        return jsonify(app.ua_fixtures.export_for_testing()), 200
    
    # Root endpoint
    @app.route('/', methods=['GET'])
    def root():
        return jsonify({
            "name": "ZecKit Faucet",
            "version": "0.1.0",
            "description": "Zcash Regtest Faucet for ZecKit",
            "endpoints": {
                "health": "/health",
                "stats": "/stats",
                "request": "/request",
                "address": "/address",
                "fixtures": "/fixtures",
                "history": "/history"
            },
            "zebra_connected": app.zebra_client is not None and app.zebra_client.ping(),
            "wallet_loaded": app.faucet_wallet is not None and app.faucet_wallet.is_loaded(),
            "ua_fixtures_loaded": app.ua_fixtures is not None
        }), 200
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "error": "Not found",
            "code": "NOT_FOUND"
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500
    
    # Store app start time for uptime tracking
    app.start_time = datetime.utcnow()
    
    logger.info("✓ ZecKit Faucet initialized successfully")
    
    return app


# For direct execution
if __name__ == '__main__':
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=8080,
        debug=True
    )