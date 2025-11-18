"""
ZecKit Faucet - Fixed Wallet Management
Proper balance tracking with funding history
"""
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import os
import hashlib

from .zebra_rpc import ZebraRPCClient, ZebraRPCError

logger = logging.getLogger(__name__)


class FaucetWallet:
    """
    Simple wallet for faucet operations with proper balance tracking
    """
    
    def __init__(self, zebra_client: ZebraRPCClient, wallet_file: str = "/var/faucet/wallet.json"):
        self.zebra_client = zebra_client
        self.wallet_file = wallet_file
        self.address = None
        self.created_at = None
        # Separate transaction types for clear accounting
        self.funding_history: List[Dict[str, Any]] = []
        self.spending_history: List[Dict[str, Any]] = []
        
        if os.path.exists(wallet_file):
            self._load_wallet()
        else:
            self._create_wallet()
    
    def _load_wallet(self) -> bool:
        try:
            logger.info(f"Loading wallet from {self.wallet_file}")
            with open(self.wallet_file, 'r') as f:
                data = json.load(f)
            
            self.address = data.get('address')
            self.created_at = data.get('created_at')
            self.funding_history = data.get('funding_history', [])
            self.spending_history = data.get('spending_history', [])
            
            if not self.address:
                logger.error("Wallet file missing address")
                return False
            
            logger.info(f"✓ Wallet loaded: {self.address}")
            logger.info(f"  Funding events: {len(self.funding_history)}")
            logger.info(f"  Spending events: {len(self.spending_history)}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to load wallet: {e}")
            return False
    
    def _create_wallet(self) -> bool:
        try:
            logger.info("Creating new faucet wallet")
            
            try:
                self.address = self.zebra_client.get_new_address("transparent")
                logger.info(f"✓ Generated new address from Zebra: {self.address}")
            except Exception as e:
                logger.warning(f"Could not generate address from Zebra: {e}")
                logger.info("Using fallback regtest address")
                self.address = "tmBsTi2xWTjUdEXnuTceL7fecEQKeWu4u6d"
            
            self.created_at = datetime.utcnow().isoformat() + "Z"
            self.funding_history = []
            self.spending_history = []
            
            self._save_wallet()
            logger.info(f"✓ New wallet created: {self.address}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to create wallet: {e}")
            return False
    
    def _save_wallet(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.wallet_file), exist_ok=True)
            
            data = {
                'address': self.address,
                'created_at': self.created_at,
                'funding_history': self.funding_history[-1000:],
                'spending_history': self.spending_history[-1000:],
                # Store computed balance for quick reference
                'last_computed_balance': self.get_balance()
            }
            
            with open(self.wallet_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to save wallet: {e}")
            return False
    
    def is_loaded(self) -> bool:
        return self.address is not None
    
    def get_address(self) -> Optional[str]:
        return self.address
    
    def get_balance(self) -> float:
        """
        Calculate balance: total_funded - total_spent
        """
        try:
            if not self.is_loaded():
                return 0.0
            
            total_funded = sum(tx.get('amount', 0.0) for tx in self.funding_history)
            total_spent = sum(tx.get('amount', 0.0) for tx in self.spending_history)
            
            balance = total_funded - total_spent
            return max(0.0, balance)
        
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0
    
    def add_funds(self, amount: float, txid: Optional[str] = None, note: str = "Admin funding") -> bool:
        """
        Add funds to wallet (funding event)
        """
        try:
            funding_record = {
                'txid': txid or f"funding-{datetime.utcnow().timestamp()}",
                'amount': amount,
                'timestamp': datetime.utcnow().isoformat() + "Z",
                'note': note
            }
            
            self.funding_history.append(funding_record)
            self._save_wallet()
            
            logger.info(f"✓ Added {amount} ZEC. New balance: {self.get_balance()} ZEC")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add funds: {e}")
            return False
    
    def send_funds(
        self,
        to_address: str,
        amount: float,
        memo: Optional[str] = None
    ) -> Optional[str]:
        """
        Send funds from faucet (spending event)
        MOCK MODE: Simulated transactions for regtest
        """
        try:
            if not self.is_loaded():
                logger.error("Wallet not loaded")
                return None
            
            balance = self.get_balance()
            if balance < amount:
                logger.error(f"Insufficient balance: {balance} < {amount}")
                return None
            
            # Generate mock TXID
            mock_data = f"{to_address}{amount}{datetime.utcnow().isoformat()}"
            txid = hashlib.sha256(mock_data.encode()).hexdigest()
            
            logger.warning(f"⚠ MOCK TRANSACTION (Zebra has no wallet) - TXID: {txid}")
            
            # Record spending
            spending_record = {
                'txid': txid,
                'to_address': to_address,
                'amount': amount,
                'timestamp': datetime.utcnow().isoformat() + "Z",
                'memo': memo,
                'mock': True
            }
            
            self.spending_history.append(spending_record)
            self._save_wallet()
            
            logger.info(f"✓ Sent {amount} ZEC to {to_address}. New balance: {self.get_balance()} ZEC")
            return txid
        
        except Exception as e:
            logger.error(f"Failed to send funds: {e}")
            return None
    
    def get_transaction_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get combined transaction history (funding + spending)
        """
        # Combine and sort by timestamp
        all_txs = []
        
        for tx in self.funding_history:
            all_txs.append({**tx, 'type': 'funding'})
        
        for tx in self.spending_history:
            all_txs.append({**tx, 'type': 'spending'})
        
        # Sort by timestamp descending
        all_txs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return all_txs[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        total_funded = sum(tx['amount'] for tx in self.funding_history)
        total_spent = sum(tx['amount'] for tx in self.spending_history)
        
        return {
            'address': self.address,
            'created_at': self.created_at,
            'current_balance': self.get_balance(),
            'total_funding_events': len(self.funding_history),
            'total_spending_events': len(self.spending_history),
            'total_funded': total_funded,
            'total_spent': total_spent
        }