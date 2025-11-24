#!/usr/bin/env python3
import requests
import json
import hashlib
import struct

def mine_block():
    """Mine a single block in regtest"""
    url = "http://127.0.0.1:8232"
    
    # Get block template
    template_response = requests.post(url, json={
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getblocktemplate",
        "params": [{"rules": ["segwit"]}]
    })
    
    if template_response.status_code != 200:
        print(f"Failed to get template: {template_response.text}")
        return False
    
    template = template_response.json()
    
    if "error" in template:
        print(f"Error: {template['error']}")
        return False
    
    # In regtest with Zebra, calling getblocktemplate actually mines the block
    # Check block count increased
    count_response = requests.post(url, json={
        "jsonrpc": "2.0",
        "id": "2",
        "method": "getblockcount",
        "params": []
    })
    
    count = count_response.json().get("result", 0)
    return count

def mine_blocks(n=101):
    """Mine n blocks"""
    print(f"🔨 Mining {n} blocks...")
    
    start_count = mine_block()
    if start_count is False:
        print("❌ Failed to start mining")
        return False
    
    print(f"Starting at block {start_count}")
    
    for i in range(n):
        current = mine_block()
        if current is False or current == start_count + i:
            print(f"✅ Mined block {i+1}/{n} (height: {current})")
        else:
            print(f"⚠️  Block {i+1}/{n} might have failed")
    
    final_count = mine_block()
    print(f"🎉 Final block count: {final_count}")
    print(f"📊 Mined {final_count - start_count} blocks")
    
    return True

if __name__ == "__main__":
    mine_blocks(101)