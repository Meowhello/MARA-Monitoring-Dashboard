const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const compactNumber = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 2,
});

const numberFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });

let mnavChart;
let factorChart;
let contributionChart;

async function loadData() {
  const response = await fetch("/api/data");
  const payload = await response.json();
  renderDashboard(payload);
}

function renderDashboard(payload) {
  renderHeader(payload);
  renderMetrics(payload.latest || {});
  renderSummary(payload.quick_summary || []);
  renderMethodology(payload.methodology || {});
  renderTransactions(payload.transactions || []);
  renderCharts(payload.series || []);
}

function renderHeader(payload) {
  const pill = document.getElementById("last-updated-pill");
  if (!payload.generated_at) {
    pill.textContent = "尚未建立資料檔";
    return;
  }
  const local = new Date(payload.generated_at).toLocaleString("zh-TW", {
    hour12: false,
  });
  pill.textContent = `最後更新：${local}`;
}

function renderMetrics(latest) {
  const entries = [
    {
      label: "最新 mNAV",
      value: latest.realized_mnav == null ? "—" : numberFmt.format(latest.realized_mnav),
      sub: `7D ${formatPct(latest.mnav_change_7d_pct)} · 30D ${formatPct(latest.mnav_change_30d_pct)}`,
    },
    {
      label: "MARA 股價",
      value: latest.stock_price == null ? "—" : money.format(latest.stock_price),
      sub: "資料源：Alpha Vantage / Yahoo Finance 備援",
    },
    {
      label: "BTC 價格",
      value: latest.btc_price == null ? "—" : money.format(latest.btc_price),
      sub: "資料源：CoinGecko",
    },
    {
      label: "BTC 持幣量",
      value: latest.btc_holdings == null ? "—" : `${compactNumber.format(latest.btc_holdings)} BTC`,
      sub: latest.total_asset_value == null ? "—" : `資產價值 ${money.format(latest.total_asset_value)}`,
    },
    {
      label: "股數 / 稀釋",
      value: latest.shares_outstanding == null ? "—" : compactNumber.format(latest.shares_outstanding),
      sub: latest.btc_per_share == null ? "—" : `BTC / Share ${latest.btc_per_share}`,
    },
  ];

  const root = document.getElementById("metrics");
  root.innerHTML = entries
    .map(
      (item) => `
        <article class="metric">
          <div class="metric-label">${item.label}</div>
          <div class="metric-value">${item.value}</div>
          <div class="metric-sub">${item.sub}</div>
        </article>
      `,
    )
    .join("");
}

function renderSummary(items) {
  const root = document.getElementById("summaryList");
  root.innerHTML = items.map((item) => `<li>${item}</li>`).join("");
}

function formatPctTick(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${Number(value).toFixed(2)}%`;
}

function renderMethodology(methodology) {
  document.getElementById("formula").textContent = methodology.formula || "—";
  const root = document.getElementById("methodologyNotes");
  const notes = methodology.notes || [];
  root.innerHTML = notes.map((item) => `<li>${item}</li>`).join("");
}

function renderTransactions(rows) {
  const root = document.getElementById("transactionsBody");
  if (!rows.length) {
    root.innerHTML = `<tr><td colspan="6">目前沒有交易資料。</td></tr>`;
    return;
  }

  root.innerHTML = rows
    .map((row) => {
      const source = row.source_url
        ? `<a href="${row.source_url}" target="_blank" rel="noreferrer">連結</a>`
        : "—";
      return `
        <tr>
          <td>${row.date || "—"}</td>
          <td>${row.type || "—"}</td>
          <td class="${row.holding_net_change >= 0 ? "positive" : "negative"}">${formatSignedNumber(row.holding_net_change)}</td>
          <td>${formatMaybeNumber(row.holding_balance)}</td>
          <td>${row.transaction_value_usd == null || row.transaction_value_usd <= 0 ? "—" : money.format(row.transaction_value_usd)}</td>
          <td>${source}</td>
        </tr>
      `;
    })
    .join("");
}

function renderCharts(series) {
  if (!series.length) {
    return;
  }

  const labels = series.map((row) => row.date);
  const mnav = series.map((row) => row.realized_mnav);
  const stock = normalizeSeries(series.map((row) => row.stock_price));
  const shares = normalizeSeries(series.map((row) => row.shares_outstanding));
  const btcPrice = normalizeSeries(series.map((row) => row.btc_price));
  const btcHoldings = normalizeSeries(series.map((row) => row.btc_holdings));

  if (mnavChart) mnavChart.destroy();
  if (factorChart) factorChart.destroy();
  if (contributionChart) contributionChart.destroy();

  mnavChart = new Chart(document.getElementById("mnavChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Realized mNAV",
          data: mnav,
          borderColor: "#8bb4ff",
          backgroundColor: "rgba(139, 180, 255, 0.12)",
          borderWidth: 2.5,
          fill: true,
          pointRadius: 0,
          tension: 0.25,
        },
      ],
    },
    options: lineOptions("mNAV"),
  });

  factorChart = new Chart(document.getElementById("factorChart"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "股價 (起點=100)",
          data: stock,
          borderColor: "#7c9cff",
          pointRadius: 0,
          tension: 0.2,
          borderWidth: 2,
        },
        {
          label: "股數 / 稀釋 (起點=100)",
          data: shares,
          borderColor: "#f7c76b",
          pointRadius: 0,
          tension: 0.2,
          borderWidth: 2,
        },
        {
          label: "BTC 價格 (起點=100)",
          data: btcPrice,
          borderColor: "#20c997",
          pointRadius: 0,
          tension: 0.2,
          borderWidth: 2,
        },
        {
          label: "BTC 持幣量 (起點=100)",
          data: btcHoldings,
          borderColor: "#ff7b9c",
          pointRadius: 0,
          tension: 0.2,
          borderWidth: 2,
        },
      ],
    },
    options: lineOptions("標準化指數"),
  });

  const contributionRows = series.filter((row) =>
    [row.contrib_stock_price, row.contrib_shares, row.contrib_btc_price, row.contrib_btc_holdings].some(
      (v) => v != null && Number.isFinite(v),
    ),
  );
  const contributionWindow = contributionRows.slice(-7);
  const avgContribution = (key) => {
    const values = contributionWindow
      .map((row) => row[key])
      .filter((v) => v != null && Number.isFinite(v));
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  };

  contributionChart = new Chart(document.getElementById("contributionChart"), {
    type: "bar",
    data: {
      labels: ["股價", "股數/稀釋", "BTC 價格", "BTC 持幣量"],
      datasets: [
        {
          label: "近 7 天平均近似貢獻(%)",
          data: [
            avgContribution("contrib_stock_price"),
            avgContribution("contrib_shares"),
            avgContribution("contrib_btc_price"),
            avgContribution("contrib_btc_holdings"),
          ],
          backgroundColor: ["#7c9cff", "#f7c76b", "#20c997", "#ff7b9c"],
          borderRadius: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: {
          ticks: { color: "#cdd6f5" },
          grid: { display: false },
        },
        y: {
          ticks: {
            color: "#cdd6f5",
            callback: (v) => formatPctTick(v),
          },
          grid: { color: "rgba(255,255,255,0.08)" },
        },
      },
    },
  });
}

function lineOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        labels: { color: "#e8edff", boxWidth: 14 },
      },
    },
    scales: {
      x: {
        ticks: {
          color: "#cdd6f5",
          maxTicksLimit: 8,
        },
        grid: {
          color: "rgba(255,255,255,0.05)",
        },
      },
      y: {
        ticks: {
          color: "#cdd6f5",
        },
        title: {
          display: true,
          text: yLabel,
          color: "#cdd6f5",
        },
        grid: {
          color: "rgba(255,255,255,0.08)",
        },
      },
    },
  };
}

function normalizeSeries(values) {
  const first = values.find((value) => value != null && Number.isFinite(value));
  if (!first) return values;
  return values.map((value) => (value == null ? null : (value / first) * 100));
}

function formatPct(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  const cls = value >= 0 ? "positive" : "negative";
  return `<span class="${cls}">${value >= 0 ? "+" : ""}${value.toFixed(2)}%</span>`;
}

function formatSignedNumber(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${numberFmt.format(value)}`;
}

function formatMaybeNumber(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  return numberFmt.format(value);
}

loadData().catch((error) => {
  console.error(error);
  const root = document.getElementById("summaryList");
  root.innerHTML = `<li>讀取資料失敗：${error.message}</li>`;
});
