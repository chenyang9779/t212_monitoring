(() => {
  const panel = document.getElementById("lifecyclePanel");
  if (!panel) return;

  const body = document.getElementById("lifecycleBody");
  const note = document.getElementById("lifecycleNote");
  const refreshButton = document.getElementById("lifecycleRefresh");
  const openEl = document.getElementById("lifecycleOpen");
  const closedEl = document.getElementById("lifecycleClosed");
  const incompleteEl = document.getElementById("lifecycleIncomplete");
  const totalEl = document.getElementById("lifecycleTotal");

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[ch]));
  }

  function number(value, digits = 6) {
    return typeof value === "number" && Number.isFinite(value)
      ? new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value)
      : "—";
  }

  function date(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? escapeHtml(value) : escapeHtml(parsed.toLocaleString());
  }

  function duration(seconds) {
    if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "—";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
    return `${(seconds / 86400).toFixed(1)}d`;
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function render(payload) {
    openEl.textContent = String(payload.open ?? 0);
    closedEl.textContent = String(payload.closed ?? 0);
    incompleteEl.textContent = String(payload.incomplete ?? 0);
    totalEl.textContent = String(payload.total ?? 0);

    const items = Array.isArray(payload.items) ? payload.items : [];
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="10" class="empty">No lifecycle data yet.</td></tr>`;
      note.textContent = "Lifecycle records appear after position changes are observed, while current holdings are shown as incomplete if they predate the monitor.";
      return;
    }

    body.innerHTML = items.map((item) => {
      const status = item.status === "closed" ? "closed" : "open";
      const coverage = item.complete ? "complete" : "incomplete";
      const statusClass = status === "open" ? "lifecycle-open" : "lifecycle-closed";
      const coverageClass = item.complete ? "lifecycle-complete" : "lifecycle-incomplete";
      return `<tr>
        <td class="instrument"><strong>${escapeHtml(item.ticker)}</strong><small>${escapeHtml(item.name)}</small></td>
        <td><span class="lifecycle-badge ${statusClass}">${escapeHtml(status)}</span></td>
        <td>${date(item.opened_at)}</td>
        <td>${date(item.closed_at)}</td>
        <td class="num">${number(item.current_quantity)}</td>
        <td class="num">${number(item.peak_quantity)}</td>
        <td class="num good-text">${number(item.total_added_quantity)}</td>
        <td class="num bad-text">${number(item.total_reduced_quantity)}</td>
        <td class="num">${duration(item.holding_seconds)}</td>
        <td><span class="lifecycle-badge ${coverageClass}">${escapeHtml(coverage)}</span></td>
      </tr>`;
    }).join("");

    const sourceEvents = Number(payload.source_events);
    const sourceText = Number.isFinite(sourceEvents) ? ` Reconstructed from ${sourceEvents} local event(s).` : "";
    note.textContent = payload.incomplete
      ? `${payload.incomplete} lifecycle(s) are incomplete because monitoring began after the position was already open. Realized P/L is intentionally not inferred yet.${sourceText}`
      : `Observed lifecycle coverage is complete for the records shown. Realized P/L is intentionally not inferred yet.${sourceText}`;
  }

  async function refresh() {
    refreshButton.disabled = true;
    refreshButton.textContent = "Loading…";
    try {
      render(await getJSON("/api/position-lifecycles"));
    } catch (error) {
      body.innerHTML = `<tr><td colspan="10" class="empty">Lifecycle error: ${escapeHtml(error.message)}</td></tr>`;
      note.textContent = "The rest of the portfolio monitor is unaffected.";
    } finally {
      refreshButton.disabled = false;
      refreshButton.textContent = "Refresh";
    }
  }

  refreshButton.addEventListener("click", refresh);
  refresh();
  setInterval(refresh, 15000);
})();
