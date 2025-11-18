"""
ZecKit - Unified Address (ZIP-316) Fixtures
Generates and manages test UA vectors for E2E flows
"""
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from .zebra_rpc import ZebraRPCClient, ZebraRPCError

logger = logging.getLogger(__name__)


@dataclass
class UAFixture:
    """Unified Address test fixture"""
    name: str
    address: str
    address_type: str  # "unified", "sapling", "transparent"
    receivers: List[str]  # List of receiver types in the UA
    pre_funded: bool = False
    pre_fund_amount: float = 0.0
    created_at: str = ""
    notes: str = ""


class UAFixtureManager:
    """
    Manages Unified Address fixtures for testing
    
    ZIP-316 Test Scenarios:
    1. UA with all receivers (transparent + sapling + orchard)
    2. UA with transparent + sapling only
    3. UA with sapling only
    4. Pure sapling address (zs1...)
    5. Pure transparent address (t...)
    """
    
    def __init__(self, zebra_client: ZebraRPCClient, fixtures_file: str = "/var/faucet/ua_fixtures.json"):
        self.zebra_client = zebra_client
        self.fixtures_file = fixtures_file
        self.fixtures: List[UAFixture] = []
        
        # Try to load existing fixtures
        self._load_fixtures()
    
    def _load_fixtures(self) -> bool:
        """Load fixtures from file"""
        try:
            import os
            if not os.path.exists(self.fixtures_file):
                logger.info("No existing UA fixtures found, will generate new ones")
                return False
            
            with open(self.fixtures_file, 'r') as f:
                data = json.load(f)
            
            self.fixtures = [
                UAFixture(**fixture) for fixture in data.get('fixtures', [])
            ]
            
            logger.info(f"✓ Loaded {len(self.fixtures)} UA fixtures")
            return True
        
        except Exception as e:
            logger.warning(f"Could not load UA fixtures: {e}")
            return False
    
    def _save_fixtures(self) -> bool:
        """Save fixtures to file"""
        try:
            import os
            os.makedirs(os.path.dirname(self.fixtures_file), exist_ok=True)
            
            data = {
                'generated_at': datetime.utcnow().isoformat() + "Z",
                'fixtures': [asdict(f) for f in self.fixtures]
            }
            
            with open(self.fixtures_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"✓ Saved {len(self.fixtures)} UA fixtures")
            return True
        
        except Exception as e:
            logger.error(f"Failed to save UA fixtures: {e}")
            return False
    
    def generate_fixtures(self, force: bool = False) -> List[UAFixture]:
        """
        Generate standard set of UA test fixtures
        
        Returns:
            List of generated fixtures
        """
        if self.fixtures and not force:
            logger.info("UA fixtures already exist (use force=True to regenerate)")
            return self.fixtures
        
        logger.info("Generating UA fixtures for ZIP-316 testing...")
        
        self.fixtures = []
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Fixture 1: Unified Address (if Zebra supports it)
        try:
            ua = self.zebra_client.get_new_address("unified")
            self.fixtures.append(UAFixture(
                name="ua_full",
                address=ua,
                address_type="unified",
                receivers=["transparent", "sapling", "orchard"],
                created_at=timestamp,
                notes="Full UA with all receiver types"
            ))
            logger.info(f"✓ Generated unified address: {ua[:20]}...")
        except Exception as e:
            logger.warning(f"Could not generate unified address: {e}")
        
        # Fixture 2: Sapling Address
        try:
            sapling = self.zebra_client.get_new_address("sapling")
            self.fixtures.append(UAFixture(
                name="sapling_standalone",
                address=sapling,
                address_type="sapling",
                receivers=["sapling"],
                created_at=timestamp,
                notes="Standalone Sapling shielded address"
            ))
            logger.info(f"✓ Generated sapling address: {sapling[:20]}...")
        except Exception as e:
            logger.warning(f"Could not generate sapling address: {e}")
        
        # Fixture 3: Transparent Address
        try:
            transparent = self.zebra_client.get_new_address("transparent")
            self.fixtures.append(UAFixture(
                name="transparent_standalone",
                address=transparent,
                address_type="transparent",
                receivers=["transparent"],
                created_at=timestamp,
                notes="Standard transparent address (t-addr)"
            ))
            logger.info(f"✓ Generated transparent address: {transparent}")
        except Exception as e:
            logger.warning(f"Could not generate transparent address: {e}")
        
        # Fixture 4: Known regtest addresses (fallback)
        if not self.fixtures:
            logger.warning("No addresses generated via RPC, using fallback regtest addresses")
            self.fixtures.append(UAFixture(
                name="transparent_fallback",
                address="tmBsTi2xWTjUdEXnuTceL7fecEQKeWu4u6d",
                address_type="transparent",
                receivers=["transparent"],
                created_at=timestamp,
                notes="Fallback regtest transparent address"
            ))
        
        self._save_fixtures()
        logger.info(f"✓ Generated {len(self.fixtures)} UA fixtures")
        
        return self.fixtures
    
    def get_fixture(self, name: str) -> Optional[UAFixture]:
        """Get fixture by name"""
        for fixture in self.fixtures:
            if fixture.name == name:
                return fixture
        return None
    
    def get_all_fixtures(self) -> List[UAFixture]:
        """Get all fixtures"""
        return self.fixtures
    
    def pre_fund_fixtures(self, faucet_wallet, amount_per_address: float = 100.0) -> Dict[str, bool]:
        """
        Pre-fund all fixtures from faucet wallet
        
        Args:
            faucet_wallet: FaucetWallet instance
            amount_per_address: Amount to fund each fixture
        
        Returns:
            Dict mapping fixture names to funding success status
        """
        results = {}
        
        logger.info(f"Pre-funding {len(self.fixtures)} UA fixtures with {amount_per_address} ZEC each")
        
        for fixture in self.fixtures:
            if fixture.pre_funded:
                logger.info(f"  {fixture.name}: already funded, skipping")
                results[fixture.name] = True
                continue
            
            try:
                txid = faucet_wallet.send_funds(
                    to_address=fixture.address,
                    amount=amount_per_address,
                    memo=f"Pre-funding UA fixture: {fixture.name}"
                )
                
                if txid:
                    fixture.pre_funded = True
                    fixture.pre_fund_amount = amount_per_address
                    results[fixture.name] = True
                    logger.info(f"  ✓ {fixture.name}: funded {amount_per_address} ZEC (txid: {txid[:16]}...)")
                else:
                    results[fixture.name] = False
                    logger.error(f"  ✗ {fixture.name}: funding failed")
            
            except Exception as e:
                results[fixture.name] = False
                logger.error(f"  ✗ {fixture.name}: {e}")
        
        self._save_fixtures()
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"✓ Pre-funded {success_count}/{len(self.fixtures)} fixtures")
        
        return results
    
    def export_for_testing(self) -> Dict[str, Any]:
        """
        Export fixtures in format suitable for test suites
        
        Returns:
            Dict with fixtures organized by type
        """
        export = {
            'generated_at': datetime.utcnow().isoformat() + "Z",
            'unified_addresses': [],
            'sapling_addresses': [],
            'transparent_addresses': [],
            'all_fixtures': []
        }
        
        for fixture in self.fixtures:
            fixture_dict = asdict(fixture)
            export['all_fixtures'].append(fixture_dict)
            
            if fixture.address_type == 'unified':
                export['unified_addresses'].append(fixture_dict)
            elif fixture.address_type == 'sapling':
                export['sapling_addresses'].append(fixture_dict)
            elif fixture.address_type == 'transparent':
                export['transparent_addresses'].append(fixture_dict)
        
        return export


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Example usage in faucet startup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def initialize_ua_fixtures(zebra_client: ZebraRPCClient, faucet_wallet) -> UAFixtureManager:
    """
    Initialize UA fixtures at faucet startup
    
    This should be called after the faucet wallet is loaded
    """
    ua_manager = UAFixtureManager(zebra_client)
    
    # Generate fixtures if they don't exist
    fixtures = ua_manager.generate_fixtures()
    
    # Pre-fund them if faucet has enough balance
    faucet_balance = faucet_wallet.get_balance()
    
    if faucet_balance >= 300.0:  # Need at least 300 ZEC to fund 3 fixtures
        logger.info("Faucet has sufficient balance, pre-funding UA fixtures...")
        ua_manager.pre_fund_fixtures(faucet_wallet, amount_per_address=100.0)
    else:
        logger.warning(f"Faucet balance ({faucet_balance} ZEC) too low to pre-fund fixtures")
    
    return ua_manager