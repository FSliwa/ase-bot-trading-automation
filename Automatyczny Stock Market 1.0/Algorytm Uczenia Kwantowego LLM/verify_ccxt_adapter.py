import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

try:
    from bot.http.ccxt_adapter import CCXTAdapter
    print("Successfully imported CCXTAdapter")
    
    print("Attributes of CCXTAdapter class:")
    for attr in dir(CCXTAdapter):
        print(f" - {attr}")
        
    if hasattr(CCXTAdapter, 'get_positions'):
        print("\n✅ get_positions exists")
    else:
        print("\n❌ get_positions DOES NOT exist")
        
except Exception as e:
    print(f"Error importing: {e}")
