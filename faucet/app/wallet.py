import subprocess
import json
import os
import time
import re
from datetime import datetime
from pathlib import Path

class ZingoWallet:
    def __init__(self, data_dir=None, lightwalletd_uri=None):
        self.data_dir = data_dir or os.getenv('WALLET_DATA_DIR', '/var/zingo')
        self.lightwalletd_uri = lightwalletd_uri or os.getenv('LIGHTWALLETD_URI', 'http://lightwalletd:9067')
        self.history_file = Path(self.data_dir) / "faucet-history.json"
        
        print(f"🔧 ZingoWallet initialized:")
        print(f"  Data dir: {self.data_dir}")
        print(f"  Backend URI: {self.lightwalletd_uri}")
        
    def _run_zingo_cmd(self, command, timeout=30, nosync=True):
        """Run zingo-cli command via docker exec"""
        try:
            wallet_container = os.getenv('WALLET_CONTAINER', 'zeckit-zingo-wallet')
            
            sync_flag = "--nosync" if nosync else ""
            cmd_str = f'echo -e "{command}\\nquit" | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest {sync_flag}'
            
            cmd = ["docker", "exec", wallet_container, "bash", "-c", cmd_str]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            
            if result.returncode != 0:
                raise Exception(f"Command failed: {result.stderr}")
            
            output = result.stdout.strip()
            
            # Try to parse JSON lines
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('{') or line.startswith('['):
                    try:
                        return json.loads(line)
                    except:
                        continue
            
            return {"output": output}
            
        except subprocess.TimeoutExpired:
            raise Exception("Command timed out")
        except Exception as e:
            raise Exception(f"Failed to run command: {str(e)}")
    
    def get_balance(self):
        """Get wallet balance in ZEC"""
        try:
            result = self._run_zingo_cmd("balance", nosync=True)
            
            total_zatoshis = 0
            
            if isinstance(result, dict) and 'output' in result:
                output = result['output']
                
                patterns = [
                    r'confirmed_transparent_balance:\s*([\d_]+)',
                    r'confirmed_sapling_balance:\s*([\d_]+)',
                    r'confirmed_orchard_balance:\s*([\d_]+)'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, output)
                    if match:
                        balance_str = match.group(1).replace('_', '')
                        total_zatoshis += int(balance_str)
            
            return total_zatoshis / 100_000_000
            
        except Exception as e:
            print(f"❌ Error getting balance: {e}")
            return 0.0
    
    def get_address(self, address_type="unified"):
        """Get wallet address"""
        try:
            result = self._run_zingo_cmd("addresses", nosync=True)
            
            if isinstance(result, dict) and 'output' in result:
                output = result['output']
                match = re.search(r'uregtest1[a-z0-9]{70,}', output)
                if match:
                    return match.group(0)
            
            return None
            
        except Exception as e:
            print(f"❌ Error getting address: {e}")
            return None
    
    def send_to_address(self, to_address: str, amount: float, memo: str = None):
        """Send REAL transaction - quicksend only works with shielded funds!"""
        try:
            amount_sats = int(amount * 100_000_000)
            wallet_container = os.getenv('WALLET_CONTAINER', 'zeckit-zingo-wallet')
            
            print(f"📤 Sending {amount} ZEC to {to_address[:12]}...")
            
            # Step 1: Stop background sync
            print("🛑 Stopping background sync...")
            subprocess.run(["docker", "exec", wallet_container, "pkill", "-f", "zingo-cli"], capture_output=True)
            time.sleep(3)
            
            # Step 2: Shield all transparent funds (quicksend only works with shielded!)
            print("🛡️ Shielding transparent funds...")
            shield_cmd = f'echo -e "quickshield\\nquit" | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest'
            shield_result = subprocess.run(
                ["docker", "exec", wallet_container, "bash", "-c", shield_cmd],
                capture_output=True,
                text=True,
                timeout=120
            )
            print(f"🛡️ Shield result: {shield_result.stdout[:200]}")
            
            # Check if shielding succeeded
            shield_match = re.search(r'[0-9a-f]{64}', shield_result.stdout)
            if not shield_match:
                # Check if there's nothing to shield
                if "no transparent" in shield_result.stdout.lower() or "nothing to shield" in shield_result.stdout.lower():
                    print("ℹ️ No transparent funds to shield (already shielded)")
                else:
                    raise Exception(f"Shield failed: {shield_result.stdout[:300]}")
            else:
                print(f"✅ Shielded! TXID: {shield_match.group(0)[:16]}...")
            
            # Step 3: Wait for shielding to confirm
            print("⏳ Waiting 15s for shield tx to confirm...")
            time.sleep(15)
            
            # Step 4: Send from shielded pool
            print(f"💸 Sending {amount} ZEC from shielded pool...")
            if memo and not (to_address.startswith('tm') or to_address.startswith('t1') or to_address.startswith('t3')):
                send_cmd = f'echo -e "quicksend {to_address} {amount_sats} \\"{memo}\\"\\nquit" | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest'
            else:
                send_cmd = f'echo -e "quicksend {to_address} {amount_sats}\\nquit" | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest'
            
            result = subprocess.run(
                ["docker", "exec", wallet_container, "bash", "-c", send_cmd],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                raise Exception(f"Send command failed: {result.stderr}")
            
            output = result.stdout.strip()
            print(f"📋 Send result: {output[:300]}")
            
            # Extract TXID
            match = re.search(r'[0-9a-f]{64}', output)
            if match:
                txid = match.group(0)
                timestamp = datetime.utcnow().isoformat() + "Z"
                self._record_transaction(to_address, amount, txid, memo)
                print(f"✅ Transaction successful: {txid}")
                return {
                    "success": True,
                    "txid": txid,
                    "timestamp": timestamp
                }
            
            # Check for errors
            if "error" in output.lower():
                raise Exception(f"Send failed: {output}")
            
            raise Exception(f"No TXID in response: {output[:300]}")
            
        except Exception as e:
            print(f"❌ Send failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _record_transaction(self, to_address, amount, txid, memo=""):
        """Record transaction to history"""
        try:
            history = []
            if self.history_file.exists():
                history = json.loads(self.history_file.read_text())
            
            history.append({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "to_address": to_address,
                "amount": amount,
                "txid": txid,
                "memo": memo
            })
            
            self.history_file.write_text(json.dumps(history, indent=2))
        except Exception as e:
            print(f"⚠️ Failed to record transaction: {e}")
    
    def get_transaction_history(self, limit=100):
        """Get transaction history"""
        try:
            if not self.history_file.exists():
                return []
            
            history = json.loads(self.history_file.read_text())
            return history[-limit:]
        except Exception as e:
            print(f"❌ Error reading history: {e}")
            return []
    
    def get_stats(self):
        """Get wallet statistics"""
        try:
            balance = self.get_balance()
            address = self.get_address()
            history = self.get_transaction_history(limit=10)
            
            return {
                "balance": balance,
                "address": address,
                "transactions_count": len(history),
                "recent_transactions": history[-5:] if history else []
            }
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
            return {
                "balance": 0.0,
                "address": None,
                "transactions_count": 0,
                "recent_transactions": []
            }

# Singleton
_wallet = None

def get_wallet():
    global _wallet
    if _wallet is None:
        _wallet = ZingoWallet()
    return _wallet