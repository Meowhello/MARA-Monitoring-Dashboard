# MARA Realized mNAV 四因子監測平台

這是一個可自動更新的 Flask 網站，主題是 **MARA Holdings 的 realized mNAV**。

網站會自動抓取並整合四個核心因子：

1. **MARA 股價**
2. **股數 / 稀釋（Shares Outstanding）**
3. **BTC 價格**
4. **MARA 的 BTC 持幣量**

然後用下面的公式重建 realized mNAV：

```text
mNAV = (shares_outstanding × stock_price) / (btc_holdings × btc_price)
```

---

## 功能

- 顯示 MARA realized mNAV 每日折線圖
- 顯示四因子標準化走勢圖
- 顯示最近一天的因子貢獻分解
- 顯示最近交易紀錄
- 支援 `refresh_data.py` 手動更新
- 支援 `/api/refresh` 觸發更新
- 附 GitHub Actions 每日排程範例

---

## 資料來源設計

- **CoinGecko Public Treasury**
  - MARA BTC holdings 歷史資料
  - MARA transaction history
  - BTC/USD 市價
- **Alpha Vantage**
  - MARA 日股價（主要來源）
- **Yahoo Finance chart**
  - MARA 日股價（當 Alpha Vantage 免費額度用完時自動備援）
- **SEC CompanyFacts**
  - Shares Outstanding

> 注意：Shares Outstanding 不是每天都會有新值，因此網站會將 SEC 申報值做前向填補，讓每日 mNAV 可以持續計算。

---

## 本機執行方式

### 1. 安裝套件

```bash
pip install -r requirements.txt
```

### 2. 建立環境變數

把 `.env.example` 複製成 `.env`

```bash
cp .env.example .env
```

然後填入：

- `COINGECKO_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `SEC_USER_AGENT`
- `REFRESH_TOKEN`

### 3. 先抓一次資料

```bash
python refresh_data.py
```

成功後會在 `data/mara_dashboard.json` 看到最新整合結果。

### 4. 啟動網站

```bash
python app.py
```

開啟：

```text
http://127.0.0.1:5000
```

---

## API 更新方式

### 手動刷新

```bash
python refresh_data.py --days 365
```

### 透過網站 API 刷新

```bash
curl -X POST "http://127.0.0.1:5000/api/refresh?token=你的REFRESH_TOKEN"
```

---

## 部署建議

### Render

這個專案最適合直接部署到 Render：

- Build Command

```bash
pip install -r requirements.txt
```

- Start Command

```bash
gunicorn app:app
```

### GitHub Actions 自動更新

你可以把這個專案推到 GitHub，然後設定 repository secrets：

- `COINGECKO_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `SEC_USER_AGENT`
- `REFRESH_TOKEN`

排程 workflow 會每天更新 `data/mara_dashboard.json`。

---

## 專題報告可寫的重點

### Selected Indicator

- 選擇指標：MARA 的 realized mNAV
- 原因：可以直接反映公司市場估值相對於其 BTC 資產價值的變化

### 四因子拆解

- 股價上升 → mNAV 上升
- 股數上升 / 稀釋增加 → mNAV 上升
- BTC 價格上升 → mNAV 下降（分母變大）
- BTC 持幣量上升 → mNAV 下降（分母變大）

### 與 BTC 的關係

- BTC 價格會直接影響公司的 crypto treasury value
- 若 MARA 股價漲幅大於 BTC 資產價值漲幅，mNAV 會擴大
- 若 BTC 大漲但 MARA 股價沒有跟上，mNAV 可能收斂

---

## 重要限制

1. CoinGecko Demo plan 的 treasury / historical access 可能有天數限制。
2. Alpha Vantage 免費方案有 25 requests/day 的限制，若超額會自動改用 Yahoo Finance 備援。
3. Shares Outstanding 為 filing-based 資料，因此不是逐日原生資料。
4. 這個版本屬於 **教育用途 / 作業用途** 的 dashboard，不是交易系統。

---

## 後續可加分方向

- 加入 OpenAI / Gemini 摘要
- 增加時間區間切換（30D / 90D / 1Y）
- 增加 Premium / Discount to NAV 比較
- 改成多家公司比較（MARA / MSTR / Metaplanet）
