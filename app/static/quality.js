(() => {
  const panel = document.getElementById("qualityPanel");
  if (!panel) return;

  const statusEl = document.getElementById("qualityStatus");
  const warningsEl = document.getElementById("qualityWarnings");
  const gapsEl = document.getElementById("qualityGaps");
  const continuityEl = document.getElementById("qualityContinuity");
  const issuesEl = document.getElementById("qualityIssues");
  const noteEl = document.getElementById("qualityNote");
  const rangeEl = document.getElementById("qualityRange");
  const refreshButton = document.getElementById("qualityRefresh");

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[ch]));
  }

  function pct(value) {
    return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
  }

  function seconds(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    if (value < 60) return `${Math.round(value)}s`;
    if (value < 3600) return `${(value / 60).toFixed(1)}m`;
    return `${(value / 3600).toFixed(1)}h`;
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function render(payload) {
    const state = String(payload.status || "unknown");
    statusEl.textContent = state.toUpperCase();
    statusEl.className = `quality-state quality-${state}`;
    warningsEl.textContent = `${payload.critical || 0} critical / ${payload.warnings || 0} warning`;
    gapsEl.textContent = String(payload.snapshot_gap_count ?? "—");
    continuityEl.textContent = pct(payload.snapshot_continuity_pct);

    const issues = Array.isArray(payload.issues) ? payload.issues : [];
    if (!issues.length) {
      issuesEl.innerHTML = `<div class="quality-issue quality-healthy"><strong>Healthy</strong><span>No integrity issues detected in the selected window.</span></div>`;
    } else {
      issuesEl.innerHTML = issues.map((issue) => `
        <div class="quality-issue quality-${escapeHtml(issue.severity)}">
          <strong>${escapeHtml(issue.severity)}</strong>
          <span>${escapeHtml(issue.message)}</span>
        </div>
      `).join("");
    }

    const parts = [
      `${payload.account_snapshots || 0} account snapshots`,
      `last sync age ${seconds(payload.sync_age_seconds)}`,
      `last snapshot age ${seconds(payload.snapshot_age_seconds)}`,
      `${payload.positions_with_wallet_values || 0}/${payload.open_positions || 0} positions with account-currency wallet values`
    ];
    if (typeof payload.valuation_difference_pct === "number") {
      parts.push(`valuation difference ${payload.valuation_difference_pct.toFixed(2)}%`);
    }
    noteEl.textContent = parts.join(" · ");
  }

  async function refresh() {
    refreshButton.disabled = true;
    issuesEl.innerHTML = `<div class="empty">Checking data quality…</div>`;
    try {
      const hours = Number(rangeEl.value) || 24;
      const payload = await getJSON(`/api/data-quality?hours=${hours}`);
      render(payload);
    } catch (error) {
      statusEl.textContent = "ERROR";
      statusEl.className = "quality-state quality-critical";
      issuesEl.innerHTML = `<div class="quality-issue quality-critical"><strong>error</strong><span>${escapeHtml(error.message)}</span></div>`;
      noteEl.textContent = "Data-quality diagnostics could not be loaded.";
    } finally {
      refreshButton.disabled = false;
    }
  }

  rangeEl.addEventListener("change", refresh);
  refreshButton.addEventListener("click", refresh);
  refresh();
  setInterval(refresh, 30000);
})();
