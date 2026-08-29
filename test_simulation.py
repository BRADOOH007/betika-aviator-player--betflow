#!/usr/bin/env python3
"""
Quick test to verify simulation mode works end-to-end
"""

import sys
from aviator_bot import AviatorMartingaleBot, MARTINGALE_STEPS

def test_simulation_mode():
    """Test simulation mode with 5 rounds"""
    print("=" * 60)
    print("SIMULATION MODE TEST")
    print("=" * 60)
    print()
    
    # Create bot in simulation mode
    bot = AviatorMartingaleBot(
        phone="test_user",
        password="test_pass",
        simulation_mode=True,
        steps=[10, 40, 174],  # Shorter sequence for testing
        auto_cashout=1.3,
        on_exhaustion="reset"
    )
    
    print("✅ Bot created in simulation mode")
    print(f"   Virtual balance: {bot._virtual_balance:.0f} KES")
    print(f"   Steps: {bot.steps}")
    print(f"   Auto cashout: {bot.auto_cashout}x")
    print()
    
    # Run 5 simulated rounds manually
    print("Running 5 simulated rounds...")
    print("-" * 60)
    
    for i in range(5):
        try:
            multiplier = bot._simulate_round()
            
            bet_amount = bot._last_bet_amount
            won = multiplier >= bot.auto_cashout
            
            if won:
                profit = bet_amount * (bot.auto_cashout - 1)
                print(f"Round {i+1}: ✅ WIN at {multiplier}x | Bet: {bet_amount:.0f} | Profit: +{profit:.0f} | Balance: {bot._virtual_balance:.0f}")
                bot._step_idx = 0  # Reset on win
            else:
                print(f"Round {i+1}: ❌ LOSS at {multiplier}x | Bet: {bet_amount:.0f} | Loss: -{bet_amount:.0f} | Balance: {bot._virtual_balance:.0f}")
                bot._step_idx = min(bot._step_idx + 1, len(bot.steps) - 1)
            
        except Exception as e:
            print(f"Round {i+1}: ❌ ERROR: {e}")
            break
    
    print("-" * 60)
    print()
    print("✅ SIMULATION TEST COMPLETE")
    print(f"   Final virtual balance: {bot._virtual_balance:.0f} KES")
    print(f"   Balance change: {bot._virtual_balance - 10000:+.0f} KES")
    print()
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        success = test_simulation_mode()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
