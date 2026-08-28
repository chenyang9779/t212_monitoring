(() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    envBadge: $("envBadge"), statusDot: $("statusDot"), statusText: $("statusText"), errorBox: $("errorBox"),
    totalValue: $("totalValue"), invested: $("invested"), cash: $("cash"), unrealized: $("unrealized"),
    unrealizedPct: $("unrealizedPct"), realized: $("realized"), positionCount: $("positionCount"), lastSync: $("lastSync"),
    positionsBody: $("positionsBody"), filter: $("filter"), historyRange: $("historyRange"), historyChart: $("historyChart"), alerts: $("alerts"),
    historyTicker: $("historyTicker"), historyMetric: $("historyMetric"), historySubtitle: $("historySubtitle")
  };

  let latestPositions = [];
  let accountCurrency = "";
  let selectedHistoryTicker = "";
  let historyRequestId = 0;

  function money(value, currency) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "GBP", maximumFractionDigits: 2 }).format(value);
    } catch (_) {
      return `${value.toFixed(2)} ${currency || ""}`.trim();
    }
  }

  function number(value, digits = 4) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
  }

  function pct(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  }

  function tone(el, value) {
    el.classList.remove("good-text", "bad-text");
    if (typeof value !== "number") return;
    el.classList.add(value >= 0 ? "good-text" : "bad-text");
  }

  async function getJSON(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  function renderPositions() {
    const query = els.filter.value.trim().toLowerCase();
    const rows = latestPositions.filter((p) => `${p.ticker} ${p.name}`.toLowerCase().includes(query));
    if (!rows.length) {
      els.positionsBody.innerHTML = `<tr><td colspan="7" class="empty">No matching positions.</td></tr>`;
      return;
    }
    els.positionsBody.innerHTML = rows.map((p) => {
      const pnlClass = typeof p.pnl_local === "number" ? (p.pnl_local >= 0 ? "good-text" : "bad-text") : "";
      return `<tr>
        <td class="instrument"><strong>${escapeHtml(p.ticker)}</strong><small>${escapeHtml(p.name)}</small></td>
        <td class="num">${number(p.quantity, 6)}</td>
        <td class="num">${money(p.average_price, p.currency)}</td>
        <td class="num">${money(p.current_price, p.currency)}</td>
        <td class="num">${money(p.market_value_local, p.currency)}</td>
        <td class="num ${pnlClass}">${money(p.pnl_local, p.currency)}</td>
        <td class="num ${pnlClass}">${pct(p.pnl_pct)}</td>
      </tr>`;
    }).join("");
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[ch]));
  }

  function syncHistoryTickerOptions() {
    if (!latestPositions.length) {
      els.historyTicker.innerHTML = `<option value="">No positions</option>`;
      els.historyTicker.disabled = true;
      selectedHistoryTicker = "";
      return false;
    }

    const sortedPositions = latestPositions
      .slice()
      .sort((a, b) => String(a.ticker).localeCompare(String(b.ticker)));
    const availableTickers = new Set(sortedPositions.map((p) => p.ticker));
    const previous = availableTickers.has(selectedHistoryTicker)
      ? selectedHistoryTicker
      : (availableTickers.has(els.historyTicker.value) ? els.historyTicker.value : "");

    const currentTickers = Array.from(els.historyTicker.options).map((option) => option.value);
    const nextTickers = sortedPositions.map((p) => p.ticker);
    const optionsChanged = currentTickers.length !== nextTickers.length
      || currentTickers.some((ticker, index) => ticker !== nextTickers[index]);

    if (optionsChanged) {
      els.historyTicker.innerHTML = sortedPositions
        .map((p) => `<option value="${escapeHtml(p.ticker)}">${escapeHtml(p.ticker)} — ${escapeHtml(p.name)}</option>`)
        .join("");
    }

    els.historyTicker.disabled = false;
    const nextSelection = previous || sortedPositions[0].ticker;
    const selectionChanged = selectedHistoryTicker !== nextSelection;
    selectedHistoryTicker = nextSelection;
    els.historyTicker.value = selectedHistoryTicker;
    return selectionChanged;
  }

  async function refreshLatest() {
    const [status, latest] = await Promise.all([getJSON("/api/status"), getJSON("/api/latest")]);
    els.envBadge.textContent = status.environment;
    const connected = Boolean(status.connected);
    els.statusDot.className = `dot ${connected ? "good" : (status.last_error ? "bad" : "")}`;
    els.statusText.textContent = connected ? `Connected · ${status.poll_seconds}s` : "Not connected";

    if (status.last_error) {
      els.errorBox.textContent = status.last_error;
      els.errorBox.classList.remove("hidden");
    } else {
      els.errorBox.classList.add("hidden");
    }

    const a = latest.account;
    if (!a) return;
    accountCurrency = a.currency || "";
    els.totalValue.textContent = money(a.total_value, accountCurrency);
    els.invested.textContent = money(a.investments_current_value, accountCurrency);
    els.cash.textContent = money(a.available_to_trade, accountCurrency);
    els.unrealized.textContent = money(a.unrealized_pl, accountCurrency);
    els.unrealizedPct.textContent = pct(a.unrealized_pl_pct);
    els.realized.textContent = money(a.realized_pl, accountCurrency);
    tone(els.unrealized, a.unrealized_pl);
    tone(els.unrealizedPct, a.unrealized_pl_pct);
    tone(els.realized, a.realized_pl);

    latestPositions = Array.isArray(latest.positions) ? latest.positions : [];
    els.positionCount.textContent = String(latestPositions.length);
    els.lastSync.textContent = `Last sync: ${latest.last_sync ? new Date(latest.last_sync).toLocaleString() : "—"}`;
    renderPositions();

    const selectionChanged = syncHistoryTickerOptions();
    if (selectionChanged) {
      await refreshHistory();
    }
  }

  async function refreshAlerts() {
    const data = await getJSON("/api/alerts?limit=30");
    if (!data.items.length) {
      els.alerts.innerHTML = `<div class="empty">No alerts.</div>`;
      return;
    }
    els.alerts.innerHTML = data.items.map((a) => `<div class="alert">
      <span class="alert-severity">${escapeHtml(a.severity)}</span>
      <span>${escapeHtml(a.message)}</span>
      <time>${new Date(a.ts).toLocaleString()}</time>
    </div>`).join("");
  }

  async function refreshHistory() {
    const ticker = selectedHistoryTicker || els.historyTicker.value;
    if (!ticker) {
      drawHistory([], { metric: els.historyMetric.value, ticker: "", name: "", currency: accountCurrency });
      return;
    }

    const requestId = ++historyRequestId;
    const hours = Number(els.historyRange.value) || 24;
    const metric = els.historyMetric.value;
    const data = await getJSON(`/api/position-history?ticker=${encodeURIComponent(ticker)}&hours=${hours}`);

    // Ignore stale responses if the user switches positions while a request is in flight.
    if (requestId !== historyRequestId || ticker !== selectedHistoryTicker) return;

    const items = data.items || [];
    const latestPosition = latestPositions.find((p) => p.ticker === ticker);
    const name = items[items.length - 1]?.name || latestPosition?.name || "";
    const currency = items[items.length - 1]?.currency || latestPosition?.currency || accountCurrency;
    drawHistory(items, { metric, ticker, name, currency });
  }

  function formatMetricValue(value, metric, currency) {
    if (metric === "pnl_pct") return pct(value);
    if (metric === "quantity") return number(value, 6);
    return money(value, currency);
  }

  function formatAxisValue(value, metric, currency) {
    if (!Number.isFinite(value)) return "—";
    if (metric === "pnl_pct") return `${value.toFixed(2)}%`;
    if (metric === "quantity") return number(value, 4);
    return money(value, currency);
  }

  function historyMetricLabel(metric) {
    return {
      market_value_local: "Market value",
      pnl_local: "P/L",
      pnl_pct: "P/L %",
      current_price: "Current price",
      quantity: "Quantity"
    }[metric] || metric;
  }

  function drawHistory(items, meta) {
    const canvas = els.historyChart;
    const ctx = canvas.getContext("2d");
    const cssWidth = canvas.clientWidth || 900;
    const cssHeight = 230;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(cssWidth * dpr);
    canvas.height = Math.round(cssHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);

    const metric = meta.metric || "market_value_local";
    const values = items.map((x) => Number(x[metric])).filter(Number.isFinite);
    const label = historyMetricLabel(metric);
    const title = meta.ticker ? `${meta.ticker}${meta.name ? ` — ${meta.name}` : ""}` : "No position selected";
    els.historySubtitle.textContent = meta.ticker
      ? `${title} · ${label}`
      : "Historical snapshots for the selected holding stored locally in SQLite";

    const border = getComputedStyle(document.documentElement).getPropertyValue("--border");
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent");
    const muted = getComputedStyle(document.documentElement).getPropertyValue("--muted");

    if (values.length < 2) {
      ctx.fillStyle = muted;
      ctx.font = "14px system-ui";
      const message = meta.ticker ? "Not enough snapshots yet for this holding." : "No position selected.";
      ctx.fillText(message, 16, 30);
      return;
    }

    const pad = { l: 92, r: 14, t: 18, b: 28 };
    const w = cssWidth - pad.l - pad.r;
    const h = cssHeight - pad.t - pad.b;
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) { min -= 1; max += 1; }

    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.fillStyle = muted;
    ctx.font = "11px system-ui";
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (h * i / 4);
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(cssWidth - pad.r, y);
      ctx.stroke();
      const value = max - ((max - min) * i / 4);
      const text = formatAxisValue(value, metric, meta.currency);
      ctx.fillText(text, 4, y + 4);
    }

    if (metric === "pnl_local" || metric === "pnl_pct") {
      const zeroInRange = min < 0 && max > 0;
      if (zeroInRange) {
        const yZero = pad.t + h - ((0 - min) / (max - min)) * h;
        ctx.strokeStyle = muted;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(pad.l, yZero);
        ctx.lineTo(cssWidth - pad.r, yZero);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    values.forEach((value, i) => {
      const x = pad.l + (w * i / (values.length - 1));
      const y = pad.t + h - ((value - min) / (max - min)) * h;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const lastValue = items.length ? Number(items[items.length - 1][metric]) : NaN;
    const summary = `${label}: ${formatMetricValue(lastValue, metric, meta.currency)}`;
    ctx.fillStyle = muted;
    ctx.fillText(summary, pad.l, 12);

    const firstTs = new Date(items[0].ts).toLocaleString();
    const lastTs = new Date(items[items.length - 1].ts).toLocaleString();
    ctx.fillText(firstTs, pad.l, cssHeight - 8);
    const width = ctx.measureText(lastTs).width;
    ctx.fillText(lastTs, cssWidth - pad.r - width, cssHeight - 8);
  }

  els.filter.addEventListener("input", renderPositions);
  els.historyRange.addEventListener("change", () => refreshHistory().catch(() => {}));
  els.historyTicker.addEventListener("change", () => {
    selectedHistoryTicker = els.historyTicker.value;
    refreshHistory().catch((err) => {
      els.errorBox.textContent = `Position history error: ${err.message}`;
      els.errorBox.classList.remove("hidden");
    });
  });
  els.historyMetric.addEventListener("change", () => refreshHistory().catch(() => {}));
  window.addEventListener("resize", () => refreshHistory().catch(() => {}));

  async function cycle() {
    try {
      await refreshLatest();
    } catch (err) {
      els.errorBox.textContent = `Dashboard error: ${err.message}`;
      els.errorBox.classList.remove("hidden");
    }
  }

  cycle();
  refreshHistory().catch(() => {});
  refreshAlerts().catch(() => {});
  setInterval(cycle, 6000);
  setInterval(() => refreshHistory().catch(() => {}), 30000);
  setInterval(() => refreshAlerts().catch(() => {}), 15000);
})();
