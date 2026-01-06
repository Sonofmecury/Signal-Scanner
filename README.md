# 🛡️ PropGuard Quant Scanner (v6.1)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![MetaTrader5](https://img.shields.io/badge/Platform-MetaTrader5-green)
![License](https://img.shields.io/badge/License-MIT-orange)

A professional-grade **Quantitative Signal Scanner** and **Risk Management Terminal** built for MetaTrader 5. Designed specifically for funded traders (FTMO, The 5%ers) to enforce discipline, calculate position sizing instantly, and identify high-probability setups using a normalized scoring model.

---

## 🚀 Key Features

### 🧠 1. Quantitative Scoring Engine (0-100)
The system does not use basic indicators. It uses a **Normalized Weighted Probability Model** to rank every pair in real-time:
* **Trend Strength (30%):** Distance from 200 EMA + ADX Power.
* **Momentum Alignment (20%):** RSI Curves (penalizes exhaustion).
* **Structure Proximity (25%):** Distance to Donchian Breakout levels.
* **Volatility Quality (15%):** Healthy ATR % range.
* **Liquidity Quality (10%):** **CRITICAL.** Punishes high spreads (News/Rollover).

### 🛡️ Institutional Risk Governor
* **Portfolio Protection:** Blocks new trades if total open risk > Max %.
* **Spread Filter:** Automatically ignores assets with poor liquidity.
* **Jitter-Free Math:** Calculates lot sizes based on **Tick Value** (Accurate for JPY, Indices, & Metals).

### 🎮 The "Pilot's Cockpit" UI
* **Live Scoreboard:** Color-coded table (Green/Yellow/Red) for instant decision making.
* **Active Alerts:** Visual arrows (▲/▼) show real-time score momentum.
* **One-Click Config:** Adjust Risk % (0.5%, 1.0%) and R:R Ratio (1:2, 1:3) on the fly.

---

## 🛠️ Installation

### Prerequisites
1.  **MetaTrader 5 (MT5)** installed and logged into your broker.
2.  **"Algo Trading"** enabled in the MT5 toolbar.
3.  **Python 3.10+** installed.

### Setup
1.  Clone the repository:
    ```bash
    git clone [https://github.com/YourUsername/PropGuard-Quant-Scanner.git](https://github.com/YourUsername/PropGuard-Quant-Scanner.git)
    cd PropGuard-Quant-Scanner
    ```

2.  Install dependencies:
    ```bash
    pip install PyQt6 MetaTrader5 pandas pandas_ta
    ```

3.  Run the terminal:
    ```bash
    python scanner.py
    ```

---

## 📖 How to Use

### 1. The Dashboard
* **Select Markets:** Check the boxes on the left (Forex, Indices, Crypto).
* **Set Risk:** Choose your risk per trade (e.g., **0.50%**) and Target R:R (e.g., **1:2**).
* **Start Scan:** Click **"▶ START SCANNER"**.

### 2. Interpreting Scores
The scanner normalizes all data into a 0-100 score.

| Score | Rating | Action |
| :--- | :--- | :--- |
| **85 - 100** | 🟩 **INSTITUTIONAL** | **TRADE NOW.** High trend, perfect momentum, breakout imminent. |
| **70 - 84** | 🟨 **VALID SETUP** | **WATCH.** Good conditions, wait for price action trigger. |
| **0 - 69** | 🟥 **WEAK / NOISE** | **STAY AWAY.** Low quality or high spread. |

### 3. Execution
The table provides the exact **Lot Size**, **Stop Loss**, and **Take Profit** based on your account balance and risk settings. Simply enter these figures into MT5.

---

## ⚙️ Configuration (Optional)
You can modify `PropGuardConfig` in the code to adjust sensitivity:

```python
class PropGuardConfig:
    ATR_MULTIPLIER = 1.5   # Tightness of Stop Loss
    EMA_PERIOD = 200       # Trend Baseline
    LOOKBACK = 20          # Breakout Sensitivity

⚠️ Disclaimer

This software is a decision-support tool, not a financial advisor. Algo trading involves risk. Always test on a Demo account before using real funds.

Author: sonofmecury Built for: Prop Firm Compliance (FTMO / 5ers Rules)
