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
        self.lightwalletd_uri = lightwalletd_uri or os.getenv('LIGHTWALLETD_URI', 'http://zaino:9067')
        self.history_file = Path(self.data_dir) / "faucet-history.json"
        
        print(f"🔧 ZingoWallet initialized:")
        print(f"  Data dir: {self.data_dir}")
        print(f"  Backend URI: {self.lightwalletd_uri}")
        
    def _run_zingo_cmd(self, command, timeout=30, nosync=False):  # Changed default to False
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
            result = self._run_zingo_cmd("balance", nosync=False)  # No nosync
            
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
            result = self._run_zingo_cmd("addresses", nosync=True)  # This one can stay nosync
            
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
        
        """Send from Orchard pool - stop background sync first"""
        try:
            amount_sats = int(amount * 100_000_000)
            wallet_container = os.getenv('WALLET_CONTAINER', 'zeckit-zingo-wallet')
            
            print(f"📤 Sending {amount} ZEC ({amount_sats} sats) to {to_address[:16]}...")
            
            # STOP background sync first!
            print("🛑 Stopping background sync...")
            stop_cmd = f"""docker exec -i {wallet_container} bash -c "echo -e 'sync stop\\nquit' | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest --nosync" """
            
            subprocess.run(
                stop_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            time.sleep(2)  # Let it stop
            
            # Now check balance with --nosync (sync is stopped, data is fresh)
            print("💰 Checking spendable Orchard balance...")
            balance_cmd = f"""docker exec -i {wallet_container} bash -c "echo -e 'spendable_balance\\nquit' | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest --nosync" """
            
            balance_result = subprocess.run(
                balance_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            print(f"💰 Balance output: {balance_result.stdout[:400]}")
            
            # Extract spendable balance
            spendable_match = re.search(r'"spendable_balance":\s*(\d+)', balance_result.stdout)
            spendable_sats = int(spendable_match.group(1)) if spendable_match else 0
            
            print(f"💰 Spendable Orchard: {spendable_sats / 100_000_000} ZEC (raw: {spendable_sats} sats)")
            
            # Check if we have enough
            required_sats = amount_sats + 20000
            if spendable_sats >= required_sats:
                print(f"✅ Sufficient funds (need {required_sats / 100_000_000} ZEC, have {spendable_sats / 100_000_000} ZEC)")
            else:
                error_msg = f"Insufficient Orchard balance: need {required_sats / 100_000_000} ZEC, have {spendable_sats / 100_000_000} ZEC"
                print(f"❌ {error_msg}")
                raise Exception(error_msg)
            
            # Send with --nosync (sync already stopped)
            print(f"💸 Sending transaction...")
            
            if memo and not (to_address.startswith('tm') or to_address.startswith('t1') or to_address.startswith('t3')):
                send_cmd = f"""docker exec -i {wallet_container} bash -c "echo -e 'send {to_address} {amount_sats} \\"{memo}\\"\\nconfirm\\nquit' | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest --nosync" """
            else:
                send_cmd = f"""docker exec -i {wallet_container} bash -c "echo -e 'send {to_address} {amount_sats}\\nconfirm\\nquit' | zingo-cli --data-dir {self.data_dir} --server {self.lightwalletd_uri} --chain regtest --nosync" """
            
            send_result = subprocess.run(
                send_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=90
            )
            
            print(f"📋 Send output: {send_result.stdout[:600]}")
            
            # Extract TXID
            txid_match = re.search(r'"txids":\s*\[\s*"([0-9a-f]{64})"', send_result.stdout)
            if txid_match:
                txid = txid_match.group(1)
                timestamp = datetime.utcnow().isoformat() + "Z"
                self._record_transaction(to_address, amount, txid, memo)
                print(f"✅ Success! TXID: {txid}")
                return {
                    "success": True,
                    "txid": txid,
                    "timestamp": timestamp
                }
            
            # Check for errors
            if "error" in send_result.stdout.lower() or "insufficient" in send_result.stdout.lower():
                raise Exception(f"Send failed: {send_result.stdout[:500]}")
            
            raise Exception(f"No TXID in response: {send_result.stdout[:500]}")
            
        except subprocess.TimeoutExpired:
            print(f"❌ Operation timed out")
            return {"success": False, "error": "Transaction timed out"}
        except Exception as e:
            print(f"❌ Send failed: {e}")
            return {"success": False, "error": str(e)}
                
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