(() => {
  const panel = document.getElementById("reconciliationPanel");
  if (!panel) return;

  const matchedEl = document.getElementById("reconciliationMatched");
  const unmatchedEl = document.getElementById("reconciliationUnmatched");
  const rateEl = document.getElementById("reconciliationRate");
  const body = document.getElementById("reconciliationBody");
  const note = document.getElementById("reconciliationNote");
  const refreshButton = document.getElementById("reconciliationRefresh");

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[ch]));
  }

  function finite(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  function number(value, digits = 6) {
    const numeric = finite(value);
    if (numeric === null) return "—";
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(numeric);
  }

  function pct(value) {
    const numeric = finite(value);
    return numeric === null ? "—" : `${numeric.toFixed(1)}%`;
  }

  function date(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? escapeHtml(value) : escapeHtml(parsed.toLocaleString());
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  async function refresh() {
    refreshButton.disabled = true;
    matchedEl.textContent = "—";
    unmatchedEl.textContent = "—";
    rateEl.textContent = "—";
    body.innerHTML = `<tr><td colspan="8" class="empty">Reconciling position events with broker history…</td></tr>`;
    note.textContent = "Matching uses ticker, signed quantity and a 180-second timestamp window.";

    try {
      const data = await getJSON("/api/reconciliation?event_limit=50&tolerance_seconds=180");
      if (!data.available) {
        body.innerHTML = `<tr><td colspan="8" class="empty">${escapeHtml(data.error || "Historical orders unavailable.")}</td></tr>`;
        note.textContent = "Historical-orders read permission is required for reconciliation.";
        return;
      }

      matchedEl.textContent = String(data.matched ?? 0);
      unmatchedEl.textContent = String(data.unmatched ?? 0);
      rateEl.textContent = pct(data.match_rate_pct);

      const items = Array.isArray(data.items) ? data.items : [];
      if (!items.length) {
        body.innerHTML = `<tr><td colspan="8" class="empty">No observed position events to reconcile yet.</td></tr>`;
        note.textContent = "Position events are only recorded after the monitor establishes its startup baseline.";
        return;
      }

      body.innerHTML = items.map((item) => {
        const status = item.status === "matched" ? "matched" : "unmatched";
        const statusClass = status === "matched" ? "good-text" : "bad-text";
        const lag = finite(item.lag_seconds);
        return `<tr>
          <td>${date(item.event_ts)}</td>
          <td class="instrument"><strong>${escapeHtml(item.ticker)}</strong><small>${escapeHtml(item.name || "")}</small></td>
          <td>${escapeHtml(item.event_type || "—")}</td>
          <td class="${statusClass}">${escapeHtml(status)}</td>
          <td class="num">${number(item.observed_quantity)}</td>
          <td class="num">${number(item.broker_quantity)}</td>
          <td class="num">${number(item.broker_price, 4)}</td>
          <td class="num">${lag === null ? "—" : `${number(lag, 1)}s`}</td>
        </tr>`;
      }).join("");

      note.textContent = `${data.broker_orders_used ?? 0} broker order${data.broker_orders_used === 1 ? "" : "s"} matched across ${data.events_considered ?? 0} observed position event${data.events_considered === 1 ? "" : "s"}.`;
    } catch (error) {
      body.innerHTML = `<tr><td colspan="8" class="empty">Reconciliation error: ${escapeHtml(error.message)}</td></tr>`;
      note.textContent = "The rest of the monitor is unaffected.";
    } finally {
      refreshButton.disabled = false;
    }
  }

  refreshButton.addEventListener("click", refresh);
  refresh();
})();
