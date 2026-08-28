(() => {
  const root = document.getElementById("drawdownPanel");
  if (!root) return;

  const tickerEl = document.getElementById("drawdownTicker");
  const rangeEl = document.getElementById("drawdownRange");
  const subtitleEl = document.getElementById("drawdownSubtitle");
  const currentEl = document.getElementById("drawdownCurrent");
  const maxEl = document.getElementById("drawdownMax");
  const peakEl = document.getElementById("drawdownPeak");
  const returnEl = document.getElementById("drawdownReturn");
  const noteEl = document.getElementById("drawdownNote");

  const OVERALL = "__ALL__";
  let selectedTicker = OVERALL;
  let requestId = 0;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "'": "&#39;",
      '"': "&quot;",
    }[ch]));
  }

  function pct(value, signed = true) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`;
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function applyTone(element, value) {
    element.classList.remove("good-text", "bad-text");
    if (typeof value !== "number" || !Number.isFinite(value)) return;
    if (value < 0) element.classList.add("bad-text");
    else if (value > 0) element.classList.add("good-text");
  }

  async function syncTickers() {
    const latest = await getJSON("/api/latest");
    const positions = Array.isArray(latest.positions) ? latest.positions : [];
    const sorted = positions
      .slice()
      .sort((a, b) => String(a.ticker).localeCompare(String(b.ticker)));

    const available = new Set([OVERALL, ...sorted.map((position) => position.ticker)]);
    if (!available.has(selectedTicker)) selectedTicker = OVERALL;

    const nextValues = [OVERALL, ...sorted.map((position) => position.ticker)];
    const currentValues = Array.from(tickerEl.options).map((option) => option.value);
    const changed = currentValues.length !== nextValues.length
      || currentValues.some((value, index) => value !== nextValues[index]);

    if (changed) {
      tickerEl.innerHTML = [
        `<option value="${OVERALL}">Overall positions</option>`,
        ...sorted.map((position) =>
          `<option value="${escapeHtml(position.ticker)}">${escapeHtml(position.ticker)} — ${escapeHtml(position.name)}</option>`
        ),
      ].join("");
    }

    tickerEl.value = selectedTicker;
  }

  function render(data) {
    currentEl.textContent = pct(data.current_drawdown_pct, false);
    maxEl.textContent = pct(data.max_drawdown_pct, false);
    peakEl.textContent = pct(data.peak_return_pct);
    returnEl.textContent = pct(data.current_return_pct);

    applyTone(currentEl, data.current_drawdown_pct);
    applyTone(maxEl, data.max_drawdown_pct);
    applyTone(peakEl, data.peak_return_pct);
    applyTone(returnEl, data.current_return_pct);

    const label = data.scope === "overall" ? "Overall positions" : data.ticker;
    subtitleEl.textContent = `${label} · ${data.hours}h flow-aware return drawdown`;

    if (!data.observations) {
      noteEl.textContent = "Not enough stored snapshots yet to calculate drawdown.";
      return;
    }

    const segmentText = data.segments > 1
      ? `${data.segments} performance segments after observed quantity changes.`
      : "No observed quantity change inside this window.";
    noteEl.textContent = `${segmentText} Drawdown uses unrealized-return snapshots rather than raw position value, so adds/reductions do not appear as market losses.`;
  }

  function renderError(error) {
    currentEl.textContent = "—";
    maxEl.textContent = "—";
    peakEl.textContent = "—";
    returnEl.textContent = "—";
    noteEl.textContent = `Drawdown data error: ${error.message}`;
  }

  async function refresh() {
    const localRequestId = ++requestId;
    try {
      await syncTickers();
      const hours = Number(rangeEl.value) || 24;
      const url = selectedTicker === OVERALL
        ? `/api/drawdown?hours=${hours}`
        : `/api/drawdown?hours=${hours}&ticker=${encodeURIComponent(selectedTicker)}`;
      const data = await getJSON(url);
      if (localRequestId !== requestId) return;
      render(data);
    } catch (error) {
      if (localRequestId !== requestId) return;
      renderError(error);
    }
  }

  tickerEl.addEventListener("change", () => {
    selectedTicker = tickerEl.value;
    refresh();
  });
  rangeEl.addEventListener("change", refresh);

  refresh();
  setInterval(refresh, 30000);
})();
