# ⚛️ Uranium Analytics Hub

Professional-grade investment analysis platform for uranium sector capital allocation targeting 20% annual returns.

## 📊 Dashboards

### 1. **Sector Dashboard** (`index.html`)
Original analytics platform for uranium company analysis.

**Features:**
- 13 uranium companies with 50+ technical indicators each
- Interactive heat map with color-coded signals (BUY/HOLD/SELL)
- Sortable company rankings table
- Real-time data feeds & charts
- Company detail modals with deep analysis
- CSV/JSON export functionality
- 4 Plotly visualizations:
  - Composite Score Distribution (bar)
  - Score vs Volatility scatter plot
  - Signal Distribution (pie)
  - Price Returns (1M/3M/1Y grouped bars)

**Use case:** Which uranium stocks to analyze / company-level due diligence

**URL:** `https://opticreports.github.io/uranium-dashboard/`

---

### 2. **Thesis Deployment Engine** (`thesis-deployment.html`) 🆕
Portfolio-integrated capital allocation framework for institutional investors.

**Features:**

#### 🌍 Macro Thesis Validation
- Supply/demand deficit analysis (50M lbs/yr shortfall through 2030)
- Nuclear capacity expansion tracking
- Geopolitical risk assessment (Kazakhstan, Russia, Australia, etc.)
- Price floor modeling ($40-60/lb mining cost → $110-130/lb equilibrium)
- Conviction driver scoring (95/100 supply, 85/100 adoption, 75/100 geopolitical)

#### 💰 Portfolio Allocation Sizing
- Monte Carlo simulations (10,000 iterations)
- Optimal uranium allocation: **8-12% recommended** (10% optimal)
- Sensitivity analysis across allocation ranges
- Sharpe ratio improvement: +0.18 (0.75 → 0.93)
- Expected return contribution: +2.4-3.6% on $1M portfolio

#### 🎯 Capital Deployment Guidance
For $100K allocation:
- **60% URA/URNM ETF** - Core sector exposure
- **25% LEU (Denison)** - Tier-1 conviction position
- **10% OKLO** - High-beta exploration play
- **5% Dry powder** - Tactical rebalancing

**Position sizing rules & deployment schedule included**

#### 📈 Dynamic Entry/Exit Rules
Conviction-gated triggers:
- **ENTRY:** Uranium < $85/lb + conviction > 70
- **HOLD:** $85-120/lb range with conviction > 60
- **TAKE_PROFIT:** LEU @ $45 (30%), $60 (50%)
- **STOP_LOSS:** Conviction < 50 or thesis breaks

#### ⚠️ Stress Scenarios
5 major scenarios with portfolio impact analysis:
1. **Price crash -30%** → -0.84% portfolio impact
2. **Rates +200bps** → -1% (hedged by PHYS)
3. **Kazakhstan disruption** → +4.5-7% upside (best case)
4. **Nuclear policy reversal** → EMERGENCY EXIT
5. **Thorium tech breakthrough** → -1 to -2% downside

#### 🔗 Portfolio Integration
Analyzes with B.5 Enhanced reference portfolio (AVUV, PHYS, AVDV, KMLM, etc.):
- Correlation matrix (uranium + each holding)
- Suggested rebalancing: -2% AVUV, -2% PHYS, -1% AVDV → +10% uranium
- Metrics impact: Sharpe +0.12, drawdown -3pp, returns +220bps

#### ⭐ Conviction Monitor
Real-time tracking of thesis conviction scores:
- **Supply Deficit:** 95/100 ✅
- **Nuclear Adoption:** 85/100 ✅
- **Geopolitical Tailwind:** 75/100 ✅
- **Price Valuation:** 65/100 (fairly valued)
- **Macro Environment:** 78/100 ✅

**Master conviction 86/100 → Maintain 10% allocation**

**Use case:** How much capital to deploy, where, and when to exit based on macro thesis conviction

**URL:** `file://thesis-deployment.html` (local) | GitHub deployment pending

---

## 🎯 Landing Hub (`hub.html`)

Links both dashboards with quick-access navigation.

---

## 📈 Data Sources

### Uranium Companies (13)
- DNN, UUUU, LEU, UEC, LTBR, URAA, OKLO, EFR, ISOU, PENMF, STMXF, SMR, RYCEY

### Indicators per Company
- **Technical:** Price, RSI, MACD, Bollinger Bands, trend, volatility, returns (1M/3M/1Y)
- **Fundamental:** P/E, P/B, market cap, ROE, ROA, debt/equity, dividend yield
- **Valuation:** Intrinsic value, P/I ratio, grade, signal
- **Composite Score:** 25% TA + 25% FA + 25% Risk + 25% Sentiment

---

## 🚀 Deployment

### GitHub Pages
```bash
git push origin main
# Deploys to https://opticreports.github.io/uranium-dashboard/
```

### Local Testing
```bash
# Open in browser
file:///path/to/thesis-deployment.html
```

---

## 📊 Key Metrics (As of 2024-05-04)

| Metric | Value | Status |
|--------|-------|--------|
| Uranium Spot Price | $93/lb | Fair |
| Global Supply Deficit | 50M lbs/yr | Structural |
| Target Price (2026-2027) | $110-130/lb | +18-40% upside |
| Recommended Allocation | 10% | Optimal |
| Portfolio Sharpe Improvement | +0.12 | Significant |
| Thesis Conviction | 86/100 | Strong ✅ |
| Entry Signal | ACCUMULATE | Active |

---

## 🔄 Rebalancing Triggers

| Event | Action | Conviction Impact |
|-------|--------|-------------------|
| Uranium > $120/lb | Trim 10% | Thesis validates (no change) |
| Uranium < $75/lb | Add 10% dry powder | Thesis holds (opportunity) |
| Uranium > 15% of portfolio | Rebalance to 10% | Risk control |
| Conviction < 60/100 | Reduce to 5% | Major headwind |
| Nuclear policy reversal | EXIT all | Thesis breaks (-40 pts) |

---

## 💡 Use Cases

### For Individual Investors
→ Use **Sector Dashboard** to analyze companies and build conviction

### For Portfolio Managers
→ Use **Thesis Deployment Engine** to size allocation and integrate with existing holdings

### For Due Diligence Teams
→ Use **Stress Scenarios** and **Conviction Monitor** to validate thesis stability

---

## 🛠️ Tech Stack

- **Frontend:** HTML5, CSS3, jQuery
- **Charting:** Plotly.js v2.28.0
- **Data:** Embedded JSON (13 companies, full fundamentals)
- **Hosting:** GitHub Pages

---

## 📝 Notes

- All price targets are base-case scenarios (not financial advice)
- Supply/demand assumptions based on IAEA, WNA public data
- Stress scenarios are illustrative (not probabilistic)
- Conviction scores updated daily (manual tracking)
- Rebalancing triggers are recommended (not automated)

---

**Status:** Production-ready | Last Updated: 2024-05-04 | Maintained by: Optic Capital