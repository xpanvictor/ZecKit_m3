import subprocess
import json
import os
from datetime import datetime
from pathlib import Path

class ZingoWallet:
    def __init__(self, data_dir="/var/zingo", lightwalletd_uri="http://lightwalletd:9067"):
        self.data_dir = data_dir
        self.lightwalletd_uri = lightwalletd_uri
        self.history_file = Path(data_dir) / "faucet-history.json"
        
    def _run_zingo_cmd(self, command):
        """Run zingo-cli command via docker exec to zingo-wallet container"""
        try:
            # Build the command to run in zingo-wallet container
            cmd = [
                "docker", "exec", "zeckit-zingo-wallet",
                "zingo-cli",
                "--data-dir", self.data_dir,
                "--server", self.lightwalletd_uri,
                "--nosync"
            ]
            
            # Send command via stdin
            result = subprocess.run(
                cmd,
                input=f"{command}\nquit\n",
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"Command failed: {result.stderr}")
            
            # Parse JSON output
            output = result.stdout.strip()
            
            # Find JSON in output
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
            result = self._run_zingo_cmd("balance")
            
            # Sum all balance types
            total_zatoshis = 0
            if isinstance(result, dict):
                total_zatoshis += result.get('transparent_balance', 0)
                total_zatoshis += result.get('sapling_balance', 0)
                total_zatoshis += result.get('orchard_balance', 0)
            
            # Convert zatoshis to ZEC
            return total_zatoshis / 100_000_000
            
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0.0
    
    def get_address(self, address_type="unified"):
        """Get wallet address"""
        try:
            result = self._run_zingo_cmd("addresses")
            
            if isinstance(result, list):
                for addr in result:
                    if isinstance(addr, dict) and addr.get('address', '').startswith('u1'):
                        return addr.get('address')
            
            # Fallback: read from file
            address_file = Path(self.data_dir) / "faucet-address.txt"
            if address_file.exists():
                return address_file.read_text().strip()
            
            return None
            
        except Exception as e:
            print(f"Error getting address: {e}")
            return None
    
    def send_to_address(self, to_address, amount, memo=""):
        """Send ZEC to address - returns real TXID from blockchain"""
        try:
            # Convert ZEC to zatoshis
            zatoshis = int(amount * 100_000_000)
            
            # Build send command
            if memo:
                command = f'send {to_address} {zatoshis} "{memo}"'
            else:
                command = f'send {to_address} {zatoshis}'
            
            result = self._run_zingo_cmd(command)
            
            # Extract TXID from result
            if isinstance(result, dict):
                txid = result.get('txid')
                if txid:
                    # Record transaction
                    self._record_transaction(to_address, amount, txid, memo)
                    return txid
            
            raise Exception("No TXID returned from send command")
            
        except Exception as e:
            raise Exception(f"Failed to send transaction: {str(e)}")
    
    def sync_wallet(self):
        """Sync wallet with blockchain"""
        try:
            # Run sync via docker exec with proper stdin
            cmd = [
                "docker", "exec", "-i", "zeckit-zingo-wallet",
                "zingo-cli",
                "--data-dir", self.data_dir,
                "--server", self.lightwalletd_uri
            ]
            
            result = subprocess.run(
                cmd,
                input="sync run\nquit\n",
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return True
            
        except Exception as e:
            print(f"Sync warning: {e}")
            return False
    
    def _record_transaction(self, to_address, amount, txid, memo=""):
        """Record transaction to history file"""
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
            print(f"Warning: Failed to record transaction: {e}")
    
    def get_transaction_history(self, limit=100):
        """Get transaction history"""
        try:
            if not self.history_file.exists():
                return []
            
            history = json.loads(self.history_file.read_text())
            return history[-limit:]
            
        except Exception as e:
            print(f"Error reading history: {e}")
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
            print(f"Error getting stats: {e}")
            return {
                "balance": 0.0,
                "address": None,
                "transactions_count": 0,
                "recent_transactions": []
            }

# Singleton wallet instance
_wallet = None

def get_wallet():
    """Get wallet singleton"""
    global _wallet
    if _wallet is None:
        _wallet = ZingoWallet()
    return _wallet
