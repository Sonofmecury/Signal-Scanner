import sys
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QTableWidget, 
                             QTableWidgetItem, QGroupBox, QCheckBox, QDoubleSpinBox, 
                             QTextEdit, QMessageBox, QHeaderView, QScrollArea, 
                             QSplitter, QGridLayout, QMenu)
from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QColor, QFont, QAction

# ==========================================
# 1️⃣ CONFIGURATION
# ==========================================
class PropGuardConfig:
    ASSETS = {
        # Add your crosses here inside the brackets!
        "FOREX": [
            "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "NZDUSD", "USDCHF",
            "GBPJPY", "EURJPY", "EURAUD", "GBPAUD", "EURGBP", "AUDJPY"  # <--- Added these
        ],
        "INDICES": ["US30", "NAS100", "GER40", "SPX500"],
        "METALS": ["XAUUSD", "XAGUSD"],
        "ENERGY": ["USOIL", "UKOIL"],
        "CRYPTO": ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
    }
    ATR_PERIOD = 14
    ATR_MULTIPLIER = 1.5
    LOOKBACK = 20
    EMA_PERIOD = 200
    RSI_PERIOD = 14
    ADX_PERIOD = 14

# ==========================================
# 2️⃣ QUANT ENGINE
# ==========================================
class ScannerWorker(QThread):
    log_signal = pyqtSignal(str, str)
    stats_signal = pyqtSignal(dict)
    scanner_signal = pyqtSignal(list, str) 
    
    def __init__(self):
        super().__init__()
        self.is_running = False
        self.active_symbols = []
        self.risk_per_trade = 0.5
        self.rr_ratio = 1.5
        self.timeframe = mt5.TIMEFRAME_H1
        self.initial_equity = 0.0

    def set_config(self, symbols, risk, rr):
        self.active_symbols = symbols
        self.risk_per_trade = risk
        self.rr_ratio = rr
        self.log_signal.emit(f"🧮 Quant Engine Loaded: {len(symbols)} Pairs | Risk: {risk}%", "cyan")

    def run(self):
        if not mt5.initialize():
            self.log_signal.emit("❌ MT5 Init Failed", "red")
            return
        
        self.initial_equity = mt5.account_info().equity
        self.is_running = True
        self.log_signal.emit("✅ Scanner Started. Analyzing...", "lime")

        while self.is_running:
            acct = mt5.account_info()
            if acct:
                stats = {
                    "balance": acct.balance,
                    "equity": acct.equity,
                    "daily_pl": acct.equity - self.initial_equity
                }
                self.stats_signal.emit(stats)
            
            opportunities = []
            for symbol in self.active_symbols:
                data = self.analyze_symbol(symbol)
                if data: opportunities.append(data)
            
            opportunities.sort(key=lambda x: x['score'], reverse=True)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.scanner_signal.emit(opportunities, timestamp)
            
            time.sleep(1) 

        mt5.shutdown()
        self.log_signal.emit("⛔ Scanner Stopped", "orange")

    def analyze_symbol(self, symbol):
        try:
            bars = 250
            rates = mt5.copy_rates_from_pos(symbol, self.timeframe, 0, bars)
            if rates is None or len(rates) < bars: return None
            
            df = pd.DataFrame(rates)
            df['ema'] = df.ta.ema(length=PropGuardConfig.EMA_PERIOD)
            df['atr'] = df.ta.atr(length=PropGuardConfig.ATR_PERIOD)
            df['rsi'] = df.ta.rsi(length=PropGuardConfig.RSI_PERIOD)
            adx_obj = df.ta.adx(length=PropGuardConfig.ADX_PERIOD)
            df['adx'] = adx_obj[f"ADX_{PropGuardConfig.ADX_PERIOD}"]
            donchian = df.ta.donchian(lower_length=PropGuardConfig.LOOKBACK, upper_length=PropGuardConfig.LOOKBACK)
            df = pd.concat([df, donchian], axis=1)
            
            curr = df.iloc[-1]
            tick = mt5.symbol_info_tick(symbol)
            if not tick: return None

            bias = "NEUTRAL"
            if curr['close'] > curr['ema']: bias = "BULLISH"
            elif curr['close'] < curr['ema']: bias = "BEARISH"

            # SCORING
            ema_dist = abs(curr['close'] - curr['ema'])
            trend_str = min(ema_dist / (curr['atr'] * 2.0), 1.0)
            adx_norm = min(max((curr['adx'] - 20) / 25, 0), 1)
            score_trend = (0.6 * trend_str) + (0.4 * adx_norm)

            score_mom = 0.0
            if bias == "BULLISH": score_mom = max(min((curr['rsi'] - 50) / 25, 1), 0)
            elif bias == "BEARISH": score_mom = max(min((50 - curr['rsi']) / 25, 1), 0)

            atr_pct = curr['atr'] / curr['close']
            score_vol = min(max((atr_pct - 0.0005) / 0.002, 0), 1)

            dcu = curr[f"DCU_{PropGuardConfig.LOOKBACK}_{PropGuardConfig.LOOKBACK}"]
            dcl = curr[f"DCL_{PropGuardConfig.LOOKBACK}_{PropGuardConfig.LOOKBACK}"]
            dist_to_break = abs(dcu - tick.ask) if bias == "BULLISH" else abs(tick.bid - dcl)
            score_struct = 1.0 - min(dist_to_break / (curr['atr'] * 1.5), 1.0)

            sym_info = mt5.symbol_info(symbol)
            spread_points = (tick.ask - tick.bid) / sym_info.point
            atr_points = curr['atr'] / sym_info.point
            score_liq = max(1.0 - (spread_points / (atr_points * 0.2)), 0.0)

            final_score = 100 * ((0.30 * score_trend) + (0.20 * score_mom) + (0.15 * score_vol) + (0.25 * score_struct) + (0.10 * score_liq))
            final_score = round(final_score, 1)

            if bias == "BULLISH":
                entry = tick.ask
                sl = entry - (curr['atr'] * PropGuardConfig.ATR_MULTIPLIER)
                tp = entry + ((entry - sl) * self.rr_ratio)
            else:
                entry = tick.bid
                sl = entry + (curr['atr'] * PropGuardConfig.ATR_MULTIPLIER)
                tp = entry - ((sl - entry) * self.rr_ratio)

            sl_points = abs(entry - sl) / sym_info.point
            lot_size = self.calculate_lot(symbol, sl_points)

            return {
                "symbol": symbol, "score": final_score, "bias": bias, "price": entry, "sl": sl, "tp": tp, 
                "lots": lot_size, "adx": curr['adx'], "rsi": curr['rsi'], "atr": curr['atr'], 
                "spread": spread_points, "ema_dist": trend_str
            }
        except Exception:
            return None

    def calculate_lot(self, symbol, sl_points):
        balance = mt5.account_info().balance
        risk_money = balance * (self.risk_per_trade / 100.0)
        sym_info = mt5.symbol_info(symbol)
        if not sym_info: return 0.0
        tick_value = sym_info.trade_tick_value
        if tick_value == 0 or sl_points == 0: return 0.0
        raw_lot = risk_money / (sl_points * tick_value)
        step = sym_info.volume_step
        lot = round(raw_lot / step) * step
        return max(lot, sym_info.volume_min) if lot <= sym_info.volume_max else sym_info.volume_max

# ==========================================
# 3️⃣ GUI
# ==========================================
class ScannerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛡️ PROP-FIRM QUANT SCANNER v6.2 (AI Bridge)")
        self.setGeometry(100, 100, 1450, 950)
        self.setStyleSheet(self.get_style())
        
        self.worker = ScannerWorker()
        self.worker.log_signal.connect(self.log)
        self.worker.stats_signal.connect(self.update_stats)
        self.worker.scanner_signal.connect(self.update_table)
        
        self.selected_symbols = set()
        self.previous_scores = {} 
        self.latest_data_map = {} # Store full data for AI prompt
        
        w = QWidget()
        self.setCentralWidget(w)
        lay = QVBoxLayout(w)
        
        self.create_top_bar(lay)
        self.create_main_area(lay)
        self.create_legend(lay) 
        self.create_log_area(lay)
        
    def get_style(self):
        return """
            QMainWindow { background-color: #121212; color: #e0e0e0; }
            QTableWidget { background-color: #1a1a1a; gridline-color: #333; font-size: 14px; selection-background-color: #333; }
            QHeaderView::section { background-color: #252525; padding: 6px; border: 1px solid #333; font-weight: bold; }
            QGroupBox { border: 1px solid #444; margin-top: 10px; font-weight: bold; color: #00e5ff; padding-top: 15px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; background: #121212; }
            QPushButton { background-color: #222; border: 1px solid #444; color: white; padding: 10px; border-radius: 4px; }
            QPushButton:hover { background-color: #333; border-color: #00e5ff; }
            QLabel { color: #ccc; }
        """

    def create_top_bar(self, parent):
        h = QHBoxLayout()
        self.lbl_bal = QLabel("Bal: $0.00")
        self.lbl_bal.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        h.addWidget(self.lbl_bal)
        h.addStretch()
        self.lbl_update = QLabel("Last Scan: --:--:--")
        self.lbl_update.setStyleSheet("color: #555; font-family: Consolas;")
        h.addWidget(self.lbl_update)
        self.spin_risk = QDoubleSpinBox(); self.spin_risk.setValue(0.5); self.spin_risk.setSuffix("% Risk")
        self.spin_rr = QDoubleSpinBox(); self.spin_rr.setValue(2.0); self.spin_rr.setPrefix("1:")
        h.addWidget(self.spin_risk)
        h.addWidget(self.spin_rr)
        self.btn_scan = QPushButton("▶ START SCANNER")
        self.btn_scan.setStyleSheet("background-color: #006400; font-weight: bold; min-width: 150px;")
        self.btn_scan.clicked.connect(self.toggle_scan)
        h.addWidget(self.btn_scan)
        parent.addLayout(h)

    def create_main_area(self, parent):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(400)
        left_widget = QWidget(); left_layout = QVBoxLayout(left_widget)
        
        self.checks = {}
        for cat, syms in PropGuardConfig.ASSETS.items():
            gb = QGroupBox(cat)
            gl = QGridLayout(gb)
            r, c = 0, 0
            for s in syms:
                chk = QCheckBox(s)
                chk.stateChanged.connect(self.on_check)
                self.checks[s] = chk
                gl.addWidget(chk, r, c)
                c += 1
                if c > 1: c=0; r+=1
            left_layout.addWidget(gb)
        left_layout.addStretch()
        scroll.setWidget(left_widget)
        splitter.addWidget(scroll)
        
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["Symbol", "Score", "Trend", "Signal", "Entry", "SL", "TP", "Lot Size"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # Enable Right Click Context Menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)
        
        splitter.addWidget(self.table)
        splitter.setSizes([350, 1050])
        parent.addWidget(splitter, 1)

    def create_legend(self, parent):
        grp = QGroupBox("📋 Quant Score Guide")
        grp.setMaximumHeight(80)
        layout = QHBoxLayout(grp)
        l1 = QLabel("🟩 85-100: INSTITUTIONAL"); l1.setStyleSheet("color: #0f0; font-weight: bold;")
        l2 = QLabel("🟨 70-84: VALID SETUP"); l2.setStyleSheet("color: #ff0; font-weight: bold;")
        l3 = QLabel("🟥 <70: WEAK"); l3.setStyleSheet("color: #f44; font-weight: bold;")
        layout.addWidget(l1); layout.addWidget(l2); layout.addWidget(l3); layout.addStretch()
        parent.addWidget(grp)

    def create_log_area(self, parent):
        self.txt_log = QTextEdit()
        self.txt_log.setMaximumHeight(100)
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background: #000; color: #0f0; font-family: Consolas;")
        parent.addWidget(self.txt_log)

    def on_check(self):
        self.selected_symbols = {s for s, chk in self.checks.items() if chk.isChecked()}

    def toggle_scan(self):
        if not self.worker.is_running:
            if not self.selected_symbols:
                QMessageBox.warning(self, "Error", "Select symbols first.")
                return
            self.worker.set_config(list(self.selected_symbols), self.spin_risk.value(), self.spin_rr.value())
            self.worker.start()
            self.btn_scan.setText("⛔ STOP SCANNER")
            self.btn_scan.setStyleSheet("background-color: #8b0000;")
        else:
            self.worker.is_running = False
            self.btn_scan.setText("▶ START SCANNER")
            self.btn_scan.setStyleSheet("background-color: #006400;")

    # 🆕 AI BRIDGE FUNCTIONALITY
    def open_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row == -1: return
        
        sym_item = self.table.item(row, 0)
        if not sym_item: return
        symbol = sym_item.text()
        
        menu = QMenu()
        copy_ai_action = QAction(f"📋 Copy '{symbol}' AI Prompt", self)
        copy_ai_action.triggered.connect(lambda: self.copy_for_ai(symbol))
        menu.addAction(copy_ai_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def copy_for_ai(self, symbol):
        data = self.latest_data_map.get(symbol)
        if not data: return
        
        prompt = (
            f"Gemini, analyze this live potential setup for {symbol}:\n"
            f"- Quant Score: {data['score']}/100\n"
            f"- Bias: {data['bias']}\n"
            f"- ADX Strength: {data['adx']:.1f}\n"
            f"- RSI Momentum: {data['rsi']:.1f}\n"
            f"- Trend Strength (0-1): {data.get('ema_dist', 0):.2f}\n"
            f"- Spread: {data.get('spread', 0):.1f} points\n"
            f"Based on this data, is this a high-probability entry for a scalper?"
        )
        QApplication.clipboard().setText(prompt)
        self.log(f"📋 AI Prompt for {symbol} copied to clipboard!", "cyan")

    @pyqtSlot(list, str)
    def update_table(self, opportunities, timestamp):
        self.lbl_update.setText(f"Last Scan: {timestamp} ●")
        self.lbl_update.setStyleSheet("color: #00ff00; font-family: Consolas; font-weight: bold;")
        self.table.setRowCount(0)
        
        for row, data in enumerate(opportunities):
            self.table.insertRow(row)
            sym = data['symbol']
            self.latest_data_map[sym] = data # Store for AI Prompt
            
            score = data['score']
            prev_score = self.previous_scores.get(sym, score)
            arrow = " ▲" if score > prev_score else " ▼" if score < prev_score else ""
            self.previous_scores[sym] = score 
            
            self.table.setItem(row, 0, QTableWidgetItem(sym))
            
            score_item = QTableWidgetItem(f"{score}{arrow}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bg = "#00ff00" if score >= 85 else "#555500" if score >= 70 else "#330000"
            fg = "#000000" if score >= 85 else "#e0e0e0"
            score_item.setBackground(QColor(bg)); score_item.setForeground(QColor(fg))
            self.table.setItem(row, 1, score_item)
            
            self.table.setItem(row, 2, QTableWidgetItem(f"{data['bias']} (ADX:{data['adx']:.0f})"))
            
            sig = "🔥 TRADE" if score >= 85 else "👀 WATCH" if score >= 70 else "WAIT"
            self.table.setItem(row, 3, QTableWidgetItem(sig))
            
            self.table.setItem(row, 4, QTableWidgetItem(f"{data['price']:.5f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{data['sl']:.5f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{data['tp']:.5f}"))
            
            lot_item = QTableWidgetItem(str(data['lots']))
            lot_item.setForeground(QColor("#00ffff")); lot_item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            self.table.setItem(row, 7, lot_item)

    @pyqtSlot(str, str)
    def log(self, msg, col):
        t = datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f'<span style="color:{col}">[{t}] {msg}</span>')

    @pyqtSlot(dict)
    def update_stats(self, stats):
        self.lbl_bal.setText(f"Bal: ${stats['balance']:.2f}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ScannerGUI()
    w.show()
    sys.exit(app.exec())
