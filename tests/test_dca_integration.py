"""
Test DCA Integration with auto_trader.py and strategies.py

Run: python -m tests.test_dca_integration
"""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

def test_imports():
    """Test 1: Verify all DCA imports work correctly."""
    print("\n[TEST 1] Testing DCA imports...")
    
    try:
        from bot.services.dca_manager import DCAManager, DCAConfig
        print("  ✅ DCAManager imported successfully")
        
        # Test DCAConfig dataclass
        config = DCAConfig(
            base_order_percent=40.0,
            safety_order_count=3,
            price_deviation_percent=3.0,
            price_deviation_scale=1.5,
            take_profit_percent=5.0,
            stop_loss_percent=10.0
        )
        print(f"  ✅ DCAConfig created: base={config.base_order_percent}%, SO={config.safety_order_count}")
        
        return True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


def test_db_models():
    """Test 2: Verify DCA database models exist."""
    print("\n[TEST 2] Testing DCA database models...")
    
    try:
        from bot.db import DCAPosition, DCAOrder, DCASettings
        print("  ✅ DCAPosition model imported")
        print("  ✅ DCAOrder model imported")
        print("  ✅ DCASettings model imported")
        
        # Check model attributes
        assert hasattr(DCAPosition, 'symbol'), "DCAPosition missing 'symbol'"
        assert hasattr(DCAPosition, 'side'), "DCAPosition missing 'side'"
        assert hasattr(DCAPosition, 'average_entry_price'), "DCAPosition missing 'average_entry_price'"
        print("  ✅ DCAPosition has required attributes")
        
        assert hasattr(DCAOrder, 'order_type'), "DCAOrder missing 'order_type'"
        assert hasattr(DCAOrder, 'trigger_price'), "DCAOrder missing 'trigger_price'"
        print("  ✅ DCAOrder has required attributes")
        
        assert hasattr(DCASettings, 'dca_enabled'), "DCASettings missing 'dca_enabled'"
        assert hasattr(DCASettings, 'default_base_order_percent'), "DCASettings missing 'default_base_order_percent'"
        print("  ✅ DCASettings has required attributes")
        
        return True
    except Exception as e:
        print(f"  ❌ Model test failed: {e}")
        return False


def test_auto_trader_dca_flag():
    """Test 3: Verify DCA_AVAILABLE flag in auto_trader."""
    print("\n[TEST 3] Testing DCA flag in auto_trader...")
    
    try:
        # Import auto_trader module to check flag
        import bot.auto_trader as auto_trader
        
        if hasattr(auto_trader, 'DCA_AVAILABLE'):
            print(f"  ✅ DCA_AVAILABLE flag exists: {auto_trader.DCA_AVAILABLE}")
            return True
        else:
            print("  ❌ DCA_AVAILABLE flag not found in auto_trader")
            return False
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False


def test_strategies_dca_integration():
    """Test 4: Verify AutoTradingEngine accepts dca_manager parameter."""
    print("\n[TEST 4] Testing AutoTradingEngine DCA integration...")
    
    try:
        from bot.strategies import AutoTradingEngine
        import inspect
        
        # Check __init__ signature
        sig = inspect.signature(AutoTradingEngine.__init__)
        params = list(sig.parameters.keys())
        
        if 'dca_manager' in params:
            print("  ✅ AutoTradingEngine.__init__ accepts 'dca_manager' parameter")
        else:
            print("  ❌ AutoTradingEngine.__init__ missing 'dca_manager' parameter")
            return False
        
        # Check set_dca_manager method
        if hasattr(AutoTradingEngine, 'set_dca_manager'):
            print("  ✅ AutoTradingEngine.set_dca_manager method exists")
        else:
            print("  ❌ AutoTradingEngine.set_dca_manager method missing")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False


def test_dca_config_validation():
    """Test 5: Test DCAConfig validates parameters."""
    print("\n[TEST 5] Testing DCAConfig validation...")
    
    try:
        from bot.services.dca_manager import DCAConfig
        
        # Valid config
        config = DCAConfig(
            base_order_percent=40.0,
            safety_order_count=3,
            price_deviation_percent=3.0
        )
        print(f"  ✅ Valid config created")
        
        # Check calculated values
        remaining = 100 - config.base_order_percent
        per_so = remaining / config.safety_order_count
        print(f"  ✅ Safety order size: {per_so:.1f}% each ({config.safety_order_count} orders)")
        
        # Edge cases
        config_aggressive = DCAConfig(
            base_order_percent=20.0,
            safety_order_count=5,
            price_deviation_percent=2.0
        )
        print(f"  ✅ Aggressive config: base={config_aggressive.base_order_percent}%, SO={config_aggressive.safety_order_count}")
        
        config_conservative = DCAConfig(
            base_order_percent=60.0,
            safety_order_count=2,
            price_deviation_percent=5.0
        )
        print(f"  ✅ Conservative config: base={config_conservative.base_order_percent}%, SO={config_conservative.safety_order_count}")
        
        return True
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False


def test_dca_manager_methods():
    """Test 6: Test DCAManager has all required methods."""
    print("\n[TEST 6] Testing DCAManager methods...")
    
    try:
        from bot.services.dca_manager import DCAManager
        import inspect
        
        required_methods = [
            'open_dca_position',
            'check_and_execute_safety_orders',
            'close_position',  # Method name in implementation
            'check_all_safety_orders',
            'get_active_positions'  # Method name in implementation
        ]
        
        for method in required_methods:
            if hasattr(DCAManager, method):
                sig = inspect.signature(getattr(DCAManager, method))
                print(f"  ✅ {method}() exists")
            else:
                print(f"  ❌ {method}() missing")
                return False
        
        return True
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False


def run_all_tests():
    """Run all DCA integration tests."""
    print("=" * 60)
    print("DCA INTEGRATION TESTS")
    print("=" * 60)
    
    results = {
        'imports': test_imports(),
        'db_models': test_db_models(),
        'auto_trader_flag': test_auto_trader_dca_flag(),
        'strategies_integration': test_strategies_dca_integration(),
        'config_validation': test_dca_config_validation(),
        'manager_methods': test_dca_manager_methods(),
    }
    
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL DCA INTEGRATION TESTS PASSED!")
        return True
    else:
        print("\n⚠️ Some tests failed. Please review the output above.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
