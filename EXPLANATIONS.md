# Cheapest Energy Windows NG - Parameter Explanations

This document explains all configuration parameters, how they interact, and provides examples for different use cases.

## Table of Contents

- [Core Concepts](#core-concepts)
- [Charging Parameters](#charging-parameters)
- [Discharge Parameters](#discharge-parameters)
- [Spread and Threshold Parameters](#spread-and-threshold-parameters)
- [Calculation Window](#calculation-window)
- [Override Parameters](#override-parameters)
- [Example Profiles](#example-profiles)

---

## Core Concepts

### How Window Selection Works

The integration selects charging and discharging windows through a multi-step process:

```
1. Filter by Percentile    → Creates candidate pool
2. Filter by Spread        → Validates profitability
3. Filter by Price Diff    → Safety check for flat prices
4. Select N Windows        → Picks the best candidates
```

### Price Spread Calculation

The spread percentage determines if charging/discharging is economically worthwhile:

```
spread_pct = ((avg_expensive - avg_cheap) / avg_cheap) × 100
```

Example:
- Avg cheap price: 0.25 EUR/kWh
- Avg expensive price: 0.32 EUR/kWh
- Spread: (0.32 - 0.25) / 0.25 × 100 = **28%**

---

## Charging Parameters

### CEW Charging Windows

**What it does:** Maximum number of 15-minute windows to select for charging.

**How to calculate:**
```
windows_needed = battery_capacity / (charge_power × 0.25)
```

**Example (20.48 kWh battery, 7500W charger):**
```
windows_needed = 20480 / (7500 × 0.25) = 10.9 → 11 windows minimum
```

| Battery Size | Charge Power | Windows Needed | Recommended Setting |
|--------------|--------------|----------------|---------------------|
| 10 kWh | 3000W | 14 | 16-18 |
| 10 kWh | 5000W | 8 | 10-12 |
| 20 kWh | 5000W | 16 | 18-20 |
| 20 kWh | 7500W | 11 | 13-15 |

**Recommendation:** Set 20-30% higher than minimum to account for:
- Battery not being empty at start
- Round-trip efficiency losses
- Some windows potentially being filtered out

---

### CEW Cheap Percentile

**What it does:** Filters which windows can be candidates for charging. Only windows with prices in the bottom N% are considered.

**How it works:**
```
With 96 windows per day:
- 20% percentile = ~19 candidate windows
- 25% percentile = ~24 candidate windows
- 35% percentile = ~34 candidate windows
```

**Trade-off:**

| Setting | Effect |
|---------|--------|
| Lower (15-20%) | Stricter - only absolute cheapest, may not have enough candidates on flat days |
| Higher (30-40%) | Flexible - more candidates, works better on flat price days |

**Example:**
```
Prices: [0.24, 0.25, 0.26, 0.27, 0.28, 0.29, 0.30, 0.31, 0.32, 0.33]

20% percentile threshold = 0.25
→ Only windows ≤ 0.25 are candidates (2 windows)

35% percentile threshold = 0.27
→ Windows ≤ 0.27 are candidates (4 windows)
```

**Recommendation:**
- Conservative: 20-25%
- Aggressive (fuller battery): 30-40%

---

### CEW Charge Power

**What it does:** Your battery's charging power in Watts. Used for:
- Calculating how many windows needed for full charge
- Cost calculations and estimates

**Set this to:** Your actual inverter/battery charge rate limit.

---

## Discharge Parameters

### CEW Expensive Windows

**What it does:** Maximum number of 15-minute windows to select for discharging.

**For self-consumption (no grid export):**
- More windows = more hours powered by battery during expensive times
- Each window is 15 minutes, so 12 windows = 3 hours of coverage

**For grid export:**
- Balance between revenue and battery wear
- Typically fewer windows at higher prices is better

| Use Case | Recommended |
|----------|-------------|
| Self-consumption only | 8-16 windows (2-4 hours) |
| Grid export | 4-8 windows (1-2 hours peak) |

---

### CEW Expensive Percentile

**What it does:** Filters which windows can be candidates for discharging. Only windows with prices in the top N% are considered.

**How it works:**
```
25% expensive percentile = top 25% of prices
→ With 96 windows: ~24 candidate windows
```

**For self-consumption:** Can be more aggressive (30-40%) since all discharge saves money.

**For grid export:** More conservative (20-25%) to only discharge during true peaks.

---

### CEW Discharge Power

**What it does:** Your battery's discharge power in Watts.

**For self-consumption:** Set to your typical house load or inverter limit.
- If house uses 1500W average, battery discharging at 7500W is wasteful
- Excess would be exported (if allowed) or curtailed

---

## Spread and Threshold Parameters

### CEW Min Spread (Charging)

**What it does:** Minimum percentage difference between cheap and expensive prices required before ANY charging windows are selected.

**Why it matters:**
```
Battery round-trip efficiency (RTE) = ~90%
You lose 10% of energy in charge/discharge cycle

If spread < 10%, you lose money even ignoring other costs
```

**Calculation:**
```
spread = ((expensive_avg - cheap_avg) / cheap_avg) × 100

Example:
- Cheap avg: 0.25 EUR/kWh
- Expensive avg: 0.30 EUR/kWh
- Spread: (0.30 - 0.25) / 0.25 × 100 = 20%
```

**Recommendations:**

| Goal | Min Spread |
|------|------------|
| Conservative (guaranteed profit) | 20-25% |
| Balanced | 10-15% |
| Aggressive (maximize charging) | 5-10% |

---

### CEW Min Spread Discharge

**What it does:** Minimum spread required before discharge windows are selected.

**For self-consumption:**
- Can be lower since ALL discharge during expensive hours saves money
- You're avoiding buying expensive grid power
- Recommended: 10-20%

**For grid export:**
- Should be higher to ensure profitable export
- Must cover RTE losses + feed-in costs
- Recommended: 25-35%

---

### CEW Min Price Difference

**What it does:** Minimum absolute price difference (EUR/kWh) between cheap and expensive averages.

**Why it matters:** Prevents action when spread percentage is high but absolute savings are tiny.

**Example:**
```
Scenario A:
- Cheap: 0.05 EUR/kWh, Expensive: 0.08 EUR/kWh
- Spread: 60% (looks great!)
- Actual diff: 0.03 EUR/kWh (tiny savings)

Scenario B:
- Cheap: 0.25 EUR/kWh, Expensive: 0.32 EUR/kWh
- Spread: 28%
- Actual diff: 0.07 EUR/kWh (meaningful savings)
```

**Recommendation:** 0.02-0.05 EUR/kWh

---

### CEW Aggressive Discharge Spread

**What it does:** Higher spread threshold for "aggressive discharge" mode. When prices are exceptionally high, the battery discharges more aggressively (potentially to lower SOC).

**Use case:** Peak pricing events, demand response, extreme price spikes.

**Recommendation:** 40-60% (only triggers during significant price events)

---

## Calculation Window

### CEW Calculation Window Enabled

**What it does:** When enabled, only considers prices within a specific time range for calculations.

### CEW Calculation Window Start / End

**What it does:** Defines the time range for price consideration.

**Common use case:** Rolling 24-hour window that resets when new prices arrive.

**Example configuration:**
```
Start: 13:00 (1 PM)
End: 12:59 (12:59 PM next day)

This creates a 24-hour window that resets at 1 PM when
tomorrow's prices typically become available.
```

**Overnight window example:**
```
Start: 22:00
End: 08:00

Only considers overnight prices for charging decisions.
```

---

## Override Parameters

### Time Override

**CEW Time Override Enabled:** When ON, forces a specific mode during a time range.

**CEW Time Override Mode:** The mode to force (charge, discharge, idle, off).

**CEW Time Override Start/End:** The time range for the override.

**Use case:** Guarantee charging during specific hours regardless of price calculations.

```
Example: Force charging 01:00-05:00
- Start: 01:00
- End: 05:00
- Mode: charge
```

### Price Override

**CEW Price Override Enabled:** When ON, forces charging when price drops below threshold.

**CEW Price Override Threshold:** Price threshold in EUR/kWh.

**Use case:** Always charge when electricity is extremely cheap (negative prices, etc.)

```
Example: Charge whenever price < 0.10 EUR/kWh
- Enabled: ON
- Threshold: 0.10
```

---

## Example Profiles

### Profile 1: Self-Consumption (No Grid Export)

**Setup:**
- Battery: 20.48 kWh
- Charge/Discharge Power: 7500W
- Goal: Maximize self-consumption, minimize grid purchases

**Recommended Settings:**

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Charging Windows | 15 | 11 needed + 36% buffer |
| Cheap Percentile | 35% | Flexible, works on flat days |
| Min Spread | 5% | Low barrier, charge often |
| Min Price Difference | 0.02 | Minimal safety check |
| Expensive Windows | 12 | 3 hours of self-consumption |
| Expensive Percentile | 30% | Capture morning + evening peaks |
| Min Spread Discharge | 15% | All self-consumption saves money |

**Expected behavior:**
- Charges overnight (00:00-06:00) when prices are lowest
- Discharges during morning peak (07:00-10:00)
- Discharges during evening peak (17:00-20:00)
- Battery powers house instead of buying expensive grid power

---

### Profile 2: Grid Export (Feed-in Tariff)

**Setup:**
- Battery: 10 kWh
- Charge Power: 5000W
- Discharge Power: 5000W
- Goal: Maximize profit from price arbitrage

**Recommended Settings:**

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Charging Windows | 12 | 8 needed + 50% buffer |
| Cheap Percentile | 25% | Only true cheap windows |
| Min Spread | 20% | Must cover RTE + export costs |
| Min Price Difference | 0.05 | Ensure meaningful profit |
| Expensive Windows | 6 | Focus on peak hours only |
| Expensive Percentile | 20% | Only highest prices |
| Min Spread Discharge | 30% | Conservative for profitability |

**Expected behavior:**
- Only charges when prices are in bottom 25%
- Only exports during top 20% price windows
- Higher thresholds ensure each cycle is profitable

---

### Profile 3: Conservative / Battery Longevity

**Setup:**
- Any battery size
- Goal: Minimize cycles, only act on significant price differences

**Recommended Settings:**

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Charging Windows | (calculate for your battery) | Just enough for full charge |
| Cheap Percentile | 15% | Very selective |
| Min Spread | 25% | Only significant spreads |
| Min Price Difference | 0.08 | Meaningful savings required |
| Expensive Windows | 4 | Minimal discharge cycles |
| Expensive Percentile | 15% | Only true peaks |
| Min Spread Discharge | 35% | Conservative |

**Expected behavior:**
- Fewer charge/discharge cycles
- Only acts on days with significant price variation
- Extends battery lifespan

---

## Typical European Price Patterns

### Pattern 1: Dual Peak (Most Common)

```
Price
  ▲
  │    ┌───┐              ┌───┐
  │    │MOR│              │EVE│
  │    │   │    ┌───┐     │   │
  │    │   │    │MID│     │   │
  │    │   │    │   │     │   │     ┌─────┐
  │────┴───┴────┴───┴─────┴───┴─────┤NIGHT│
  └──────────────────────────────────┴─────┴──▶
     06   09   12   15   18   21   00   06
```

- **Morning peak:** 07:00-10:00 (people waking, no solar yet)
- **Midday dip:** 11:00-15:00 (solar production)
- **Evening peak:** 17:00-21:00 (solar gone, people home)
- **Night valley:** 00:00-06:00 (low demand)

### Pattern 2: Single Peak

```
Price
  ▲
  │              ┌───────┐
  │              │       │
  │         ┌───┤       ├───┐
  │    ┌───┤   │       │   ├───┐
  │────┴───┴───┴───────┴───┴───┴────
  └─────────────────────────────────▶
     06   09   12   15   18   21   00
```

Common on weekends or low-solar days.

### Pattern 3: Negative Prices (Renewable Surplus)

```
Price
  ▲
  │
  │    ┌───┐              ┌───┐
  ├────┴───┴──────────────┴───┴────  0
  │              ┌───┐
  │              │NEG│
  └──────────────┴───┴─────────────▶
     06   09   12   15   18   21   00
```

Use **Price Override** to capture negative price opportunities.

---

## Troubleshooting

### Battery Not Charging

**Check in order:**

1. **Min Spread too high?**
   - Calculate actual spread from current prices
   - Lower Min Spread if needed

2. **Cheap Percentile too low?**
   - Not enough candidate windows
   - Increase to 30-40%

3. **Min Price Difference too high?**
   - Check absolute price difference
   - Lower to 0.02-0.03

4. **Calculation Window filtering out cheap hours?**
   - Verify start/end times include overnight

### Battery Always Idle

Usually means spread requirements aren't met. On flat price days:
- Lower Min Spread to 5%
- Lower Min Price Difference to 0.02
- Increase Cheap Percentile to 35-40%

### Too Many Discharge Windows

If battery empties too fast:
- Reduce Expensive Windows
- Increase Min Spread Discharge
- Lower Expensive Percentile

---

## Quick Reference

| Parameter | Conservative | Balanced | Aggressive |
|-----------|--------------|----------|------------|
| Cheap Percentile | 20% | 25% | 35% |
| Min Spread | 20% | 10% | 5% |
| Min Price Diff | 0.05 | 0.03 | 0.02 |
| Expensive Percentile | 20% | 25% | 30% |
| Min Spread Discharge | 30% | 20% | 15% |
