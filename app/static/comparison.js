(() => {
  const panel = document.getElementById("comparisonPanel");
  if (!panel) return;

  const tickersEl = document.getElementById("comparisonTickers");
  const rangeEl = document.getElementById("comparisonRange");
  const chart = document.getElementById("comparisonChart");
  const legendEl = document.getElementById("comparisonLegend");
  const noteEl = document.getElementById("comparisonNote");
  const selectAllBtn = document.getElementById("comparisonSelectAll");
  const clearBtn = document.getElementById("comparisonClear");

  let positions = [];
  let selectedTickers = new Set();
  let requestId = 0;

  const palette = [
    "#78a9ff",
    "#55c98a",
    "#ef6a6a",
    "#e9b949",
    "#b18cff",
    "#4fd1c5",
    "#f59e0b",
    "#60a5fa",
    "#f472b6",
    "#a3e635",
  ];

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    }[ch]));
  }

  function pct(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  }

  function renderTickerSelector() {
    const sorted = positions
      .slice()
      .sort((a, b) => String(a.ticker).localeCompare(String(b.ticker)));

    const available = new Set(sorted.map((p) => p.ticker));
    selectedTickers = new Set([...selectedTickers].filter((ticker) => available.has(ticker)));

    if (!selectedTickers.size && sorted.length) {
      for (const position of sorted.slice(0, Math.min(4, sorted.length))) {
        selectedTickers.add(position.ticker);
      }
    }

    tickersEl.innerHTML = sorted.map((position) => `
      <label class="comparison-chip">
        <input type="checkbox" value="${escapeHtml(position.ticker)}" ${selectedTickers.has(position.ticker) ? "checked" : ""}>
        <span>${escapeHtml(position.ticker)}</span>
      </label>
    `).join("");

    tickersEl.querySelectorAll("input[type=checkbox]").forEach((input) => {
      input.addEventListener("change", () => {
        if (input.checked) selectedTickers.add(input.value);
        else selectedTickers.delete(input.value);
        refreshChart().catch(renderError);
      });
    });
  }

  function normalizeHistory(items) {
    const points = items
      .map((item) => ({ ts: item.ts, value: Number(item.current_price) }))
      .filter((point) => Number.isFinite(point.value) && point.value > 0);

    if (points.length < 2) return [];
    const base = points[0].value;
    return points.map((point) => ({
      ts: point.ts,
      value: (point.value / base - 1) * 100,
    }));
  }

  function downsample(points, maxPoints = 900) {
    if (points.length <= maxPoints) return points;
    const step = (points.length - 1) / (maxPoints - 1);
    const result = [];
    for (let i = 0; i < maxPoints; i += 1) {
      result.push(points[Math.round(i * step)]);
    }
    return result;
  }

  async function refreshPositions() {
    const latest = await getJSON("/api/latest");
    positions = Array.isArray(latest.positions) ? latest.positions : [];
    renderTickerSelector();
  }

  async function refreshChart() {
    const tickers = [...selectedTickers];
    const hours = Number(rangeEl.value) || 24;
    const currentRequest = ++requestId;

    if (!tickers.length) {
      drawSeries([]);
      legendEl.innerHTML = "";
      noteEl.textContent = "Select at least one position.";
      return;
    }

    noteEl.textContent = "Loading comparison history…";
    const payloads = await Promise.all(
      tickers.map(async (ticker) => {
        const data = await getJSON(`/api/position-history?ticker=${encodeURIComponent(ticker)}&hours=${hours}`);
        return {
          ticker,
          points: downsample(normalizeHistory(data.items || [])),
        };
      })
    );

    if (currentRequest !== requestId) return;

    const series = payloads.filter((seriesItem) => seriesItem.points.length >= 2);
    drawSeries(series);
    renderLegend(series);

    const unavailable = payloads.filter((seriesItem) => seriesItem.points.length < 2).map((seriesItem) => seriesItem.ticker);
    noteEl.textContent = unavailable.length
      ? `Rebased to 0% at each series start. Not enough history yet: ${unavailable.join(", ")}.`
      : "Rebased to 0% at each series start using sampled Trading 212 current-price snapshots.";
  }

  function renderLegend(series) {
    legendEl.innerHTML = series.map((item, index) => {
      const last = item.points[item.points.length - 1]?.value;
      return `
        <span class="comparison-legend-item">
          <span class="comparison-swatch" style="background:${palette[index % palette.length]}"></span>
          <strong>${escapeHtml(item.ticker)}</strong>
          <span>${pct(last)}</span>
        </span>
      `;
    }).join("");
  }

  function drawSeries(series) {
    const ctx = chart.getContext("2d");
    const cssWidth = chart.clientWidth || 900;
    const cssHeight = 260;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    chart.width = Math.round(cssWidth * dpr);
    chart.height = Math.round(cssHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);

    const styles = getComputedStyle(document.documentElement);
    const border = styles.getPropertyValue("--border").trim();
    const muted = styles.getPropertyValue("--muted").trim();

    if (!series.length) {
      ctx.fillStyle = muted;
      ctx.font = "14px system-ui";
      ctx.fillText("No comparable position history yet.", 16, 30);
      return;
    }

    const allPoints = series.flatMap((item) => item.points);
    const minTs = Math.min(...allPoints.map((point) => new Date(point.ts).getTime()));
    const maxTs = Math.max(...allPoints.map((point) => new Date(point.ts).getTime()));
    let minY = Math.min(...allPoints.map((point) => point.value));
    let maxY = Math.max(...allPoints.map((point) => point.value));

    if (minY === maxY) {
      minY -= 1;
      maxY += 1;
    }
    const padY = Math.max((maxY - minY) * 0.08, 0.25);
    minY -= padY;
    maxY += padY;

    const pad = { l: 68, r: 16, t: 18, b: 30 };
    const width = cssWidth - pad.l - pad.r;
    const height = cssHeight - pad.t - pad.b;

    ctx.font = "11px system-ui";
    ctx.fillStyle = muted;
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i += 1) {
      const y = pad.t + height * i / 4;
      const value = maxY - (maxY - minY) * i / 4;
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(cssWidth - pad.r, y);
      ctx.stroke();
      ctx.fillText(`${value.toFixed(2)}%`, 4, y + 4);
    }

    if (minY < 0 && maxY > 0) {
      const zeroY = pad.t + height - ((0 - minY) / (maxY - minY)) * height;
      ctx.save();
      ctx.strokeStyle = muted;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(pad.l, zeroY);
      ctx.lineTo(cssWidth - pad.r, zeroY);
      ctx.stroke();
      ctx.restore();
    }

    function xFor(ts) {
      if (maxTs === minTs) return pad.l;
      return pad.l + (new Date(ts).getTime() - minTs) / (maxTs - minTs) * width;
    }

    function yFor(value) {
      return pad.t + height - (value - minY) / (maxY - minY) * height;
    }

    series.forEach((item, index) => {
      ctx.strokeStyle = palette[index % palette.length];
      ctx.lineWidth = 2;
      ctx.beginPath();
      item.points.forEach((point, pointIndex) => {
        const x = xFor(point.ts);
        const y = yFor(point.value);
        if (pointIndex === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });

    const firstLabel = new Date(minTs).toLocaleString();
    const lastLabel = new Date(maxTs).toLocaleString();
    ctx.fillStyle = muted;
    ctx.fillText(firstLabel, pad.l, cssHeight - 8);
    const lastWidth = ctx.measureText(lastLabel).width;
    ctx.fillText(lastLabel, cssWidth - pad.r - lastWidth, cssHeight - 8);
  }

  function renderError(error) {
    noteEl.textContent = `Comparison data error: ${error.message}`;
  }

  rangeEl.addEventListener("change", () => refreshChart().catch(renderError));
  selectAllBtn.addEventListener("click", () => {
    selectedTickers = new Set(positions.map((position) => position.ticker));
    renderTickerSelector();
    refreshChart().catch(renderError);
  });
  clearBtn.addEventListener("click", () => {
    selectedTickers.clear();
    renderTickerSelector();
    selectedTickers.clear();
    tickersEl.querySelectorAll("input[type=checkbox]").forEach((input) => { input.checked = false; });
    refreshChart().catch(renderError);
  });
  window.addEventListener("resize", () => refreshChart().catch(() => {}));

  async function refreshAll() {
    try {
      await refreshPositions();
      await refreshChart();
    } catch (error) {
      renderError(error);
    }
  }

  refreshAll();
  setInterval(() => refreshPositions().catch(() => {}), 6000);
  setInterval(() => refreshChart().catch(() => {}), 30000);
})();
