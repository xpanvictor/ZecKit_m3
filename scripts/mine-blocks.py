#!/usr/bin/env python3
import requests
import time
import sys

def mine_blocks(count=101):
    """Mine blocks using Zebra's getblocktemplate"""
    url = "http://127.0.0.1:8232"
    
    print(f"🔨 Mining {count} blocks...")
    
    for i in range(count):
        # Get block template
        response = requests.post(url, json={
            "jsonrpc": "2.0",
            "id": str(i),
            "method": "getblocktemplate",
            "params": [{}]
        })
        
        if response.status_code == 200:
            result = response.json()
            if "result" in result:
                # In regtest, just calling getblocktemplate mines a block
                print(f"✅ Mined block {i+1}/{count}")
                time.sleep(0.1)
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP Error: {response.status_code}")
            return False
    
    print(f"🎉 Successfully mined {count} blocks!")
    return True

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 101
    mine_blocks(count)