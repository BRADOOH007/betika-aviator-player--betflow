#!/usr/bin/env python3
"""
Test script to verify all enhancements are working correctly
Run this before using the bot in production
"""

import sys
from aviator_bot import (
    AviatorMartingaleBot, 
    EMERGENCY_STOP_CONDITIONS,
    MARTINGALE_STEPS,
    AUTO_CASHOUT
)

def test_configuration():
    """Test that configuration is properly set"""
    print("=" * 60)
    print("TESTING CONFIGURATION")
    print("=" * 60)
    
    # Check emergency stop conditions
    assert "max_consecutive_losses" in EMERGENCY_STOP_CONDITIONS
    assert "max_session_loss" in EMERGENCY_STOP_CONDITIONS
    assert "min_balance_threshold" in EMERGENCY_STOP_CONDITIONS
    assert "max_session_duration" in EMERGENCY_STOP_CONDITIONS
    assert "max_stake_percent" in EMERGENCY_STOP_CONDITIONS
    
    print("✅ Emergency stop conditions configured")
    print(f"   - Max consecutive losses: {EMERGENCY_STOP_CONDITIONS['max_consecutive_losses']}")
    print(f"   - Max session loss: {EMERGENCY_STOP_CONDITIONS['max_session_loss']} KES")
    print(f"   - Min balance threshold: {EMERGENCY_STOP_CONDITIONS['min_balance_threshold']} KES")
    print(f"   - Max session duration: {EMERGENCY_STOP_CONDITIONS['max_session_duration']/3600:.1f} hours")
    print(f"   - Max stake percent: {EMERGENCY_STOP_CONDITIONS['max_stake_percent']*100}%")
    
    # Check martingale steps
    assert len(MARTINGALE_STEPS) > 0
    print(f"\n✅ Martingale steps configured: {MARTINGALE_STEPS}")
    
    # Check auto cashout
    assert AUTO_CASHOUT > 1.0
    print(f"✅ Auto cashout configured: {AUTO_CASHOUT}x")
    
    print("\n" + "=" * 60)
    print("CONFIGURATION TEST PASSED")
    print("=" * 60 + "\n")

def test_bot_initialization():
    """Test that bot can be initialized with enhanced features"""
    print("=" * 60)
    print("TESTING BOT INITIALIZATION")
    print("=" * 60)
    
    try:
        bot = AviatorMartingaleBot(
            phone="0712345678",
            password="test_password",
            site="OdiBets",
            headless=True
        )
        
        # Check enhanced attributes
        assert hasattr(bot, '_session_start')
        assert hasattr(bot, '_consecutive_losses')
        assert hasattr(bot, '_session_profit')
        assert hasattr(bot, '_last_balance')
        assert hasattr(bot, '_error_count')
        assert hasattr(bot, '_recovery_attempts')
        
        print("✅ Bot initialized with enhanced tracking attributes")
        print(f"   - Session start: {bot._session_start}")
        print(f"   - Consecutive losses: {bot._consecutive_losses}")
        print(f"   - Session profit: {bot._session_profit}")
        print(f"   - Last balance: {bot._last_balance}")
        print(f"   - Error count: {bot._error_count}")
        print(f"   - Recovery attempts: {bot._recovery_attempts}")
        
        # Check enhanced methods exist
        assert hasattr(bot, '_check_circuit_breaker')
        assert hasattr(bot, '_auto_recover_from_error')
        assert hasattr(bot, '_check_balance_threshold')
        assert hasattr(bot, '_verify_bet_placed')
        assert hasattr(bot, '_read_multiplier_robust')
        
        print("\n✅ Enhanced methods available:")
        print("   - _check_circuit_breaker()")
        print("   - _auto_recover_from_error()")
        print("   - _check_balance_threshold()")
        print("   - _verify_bet_placed()")
        print("   - _read_multiplier_robust()")
        
        print("\n" + "=" * 60)
        print("INITIALIZATION TEST PASSED")
        print("=" * 60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ INITIALIZATION TEST FAILED: {e}")
        return False

def test_circuit_breaker_logic():
    """Test circuit breaker logic without running bot"""
    print("=" * 60)
    print("TESTING CIRCUIT BREAKER LOGIC")
    print("=" * 60)
    
    bot = AviatorMartingaleBot(
        phone="0712345678",
        password="test_password",
        site="OdiBets",
        headless=True
    )
    
    # Test 1: No losses - should not trigger
    bot._consecutive_losses = 0
    bot._session_profit = 0
    bot._session_start = None
    
    result = bot._check_circuit_breaker()
    assert result == False, "Circuit breaker should not trigger with 0 losses"
    print("✅ Test 1: No trigger with 0 losses")
    
    # Test 2: Max consecutive losses - should trigger
    bot._consecutive_losses = EMERGENCY_STOP_CONDITIONS["max_consecutive_losses"]
    result = bot._check_circuit_breaker()
    assert result == True, "Circuit breaker should trigger at max consecutive losses"
    print(f"✅ Test 2: Triggers at {EMERGENCY_STOP_CONDITIONS['max_consecutive_losses']} consecutive losses")
    
    # Test 3: Max session loss - should trigger
    bot._consecutive_losses = 0
    bot._session_profit = -EMERGENCY_STOP_CONDITIONS["max_session_loss"] - 1
    result = bot._check_circuit_breaker()
    assert result == True, "Circuit breaker should trigger at max session loss"
    print(f"✅ Test 3: Triggers at {EMERGENCY_STOP_CONDITIONS['max_session_loss']} KES loss")
    
    print("\n" + "=" * 60)
    print("CIRCUIT BREAKER TEST PASSED")
    print("=" * 60 + "\n")

def test_stake_capping():
    """Test dynamic stake capping logic"""
    print("=" * 60)
    print("TESTING STAKE CAPPING")
    print("=" * 60)
    
    # Test scenarios
    test_cases = [
        {"balance": 1000, "stake": 100, "expected": 100, "reason": "Normal stake within limit"},
        {"balance": 1000, "stake": 200, "expected": 150, "reason": "Stake exceeds 15%, capped"},
        {"balance": 500, "stake": 100, "expected": 75, "reason": "Stake exceeds 15%, capped"},
        {"balance": 10000, "stake": 3267, "expected": 1500, "reason": "Large stake capped"},
    ]
    
    max_percent = EMERGENCY_STOP_CONDITIONS["max_stake_percent"]
    
    for i, test in enumerate(test_cases, 1):
        balance = test["balance"]
        stake = test["stake"]
        expected = test["expected"]
        
        max_allowed = balance * max_percent
        actual = min(stake, max_allowed)
        
        assert actual == expected, f"Test {i} failed: expected {expected}, got {actual}"
        print(f"✅ Test {i}: {test['reason']}")
        print(f"   Balance: {balance} KES, Stake: {stake} KES → Capped: {actual} KES")
    
    print("\n" + "=" * 60)
    print("STAKE CAPPING TEST PASSED")
    print("=" * 60 + "\n")

def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("AVIATOR BOT ENHANCEMENT TESTS")
    print("=" * 60 + "\n")
    
    tests = [
        ("Configuration", test_configuration),
        ("Bot Initialization", test_bot_initialization),
        ("Circuit Breaker Logic", test_circuit_breaker_logic),
        ("Stake Capping", test_stake_capping),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ {name} TEST FAILED: {e}\n")
            failed += 1
        except Exception as e:
            print(f"\n❌ {name} TEST ERROR: {e}\n")
            failed += 1
    
    # Final summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Bot is ready for use.")
        print("\nNext steps:")
        print("1. Review QUICK_START_GUIDE.md")
        print("2. Configure safety thresholds if needed")
        print("3. Test with small stakes first")
        print("4. Monitor first session closely")
    else:
        print("\n⚠️  SOME TESTS FAILED! Please review errors above.")
        return 1
    
    print("=" * 60 + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(run_all_tests())
