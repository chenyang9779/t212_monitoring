(() => {
  const bodyEl = document.getElementById("attributionBody");
  if (!bodyEl) return;

  const accountEl = document.getElementById("attributionAccount");
  const sumEl = document.getElementById("attributionSum");
  const gainsEl = document.getElementById("attributionGains");
  const lossesEl = document.getElementById("attributionLosses");
  const noteEl = document.getElementById("attributionNote");

  function money(value, currency) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: currency || "GBP",
        maximumFractionDigits: 2,
      }).format(value);
    } catch (_) {
      return `${value.toFixed(2)} ${currency || ""}`.trim();
    }
  }

  function pct(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
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

  function toneClass(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "";
    return value >= 0 ? "good-text" : "bad-text";
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function renderUnavailable(data, message) {
    accountEl.textContent = money(data?.account_unrealized_pl, data?.currency);
    sumEl.textContent = "—";
    gainsEl.textContent = "—";
    lossesEl.textContent = "—";
    bodyEl.innerHTML = `<tr><td colspan="5" class="empty">${escapeHtml(message)}</td></tr>`;
    noteEl.textContent = "Attribution requires Trading 212 per-position walletImpact.unrealizedProfitLoss in the account currency; instrument-currency P/L is not mixed in.";
  }

  function render(data) {
    if (!data.available) {
      renderUnavailable(data, data.reason || "P/L attribution is unavailable.");
      return;
    }

    const currency = data.currency || "";
    accountEl.textContent = money(data.account_unrealized_pl, currency);
    sumEl.textContent = money(data.sum_position_unrealized_pl, currency);
    gainsEl.textContent = money(data.gross_gains, currency);
    lossesEl.textContent = money(data.gross_losses, currency);

    accountEl.className = toneClass(data.account_unrealized_pl);
    sumEl.className = toneClass(data.sum_position_unrealized_pl);
    gainsEl.className = toneClass(data.gross_gains);
    lossesEl.className = toneClass(data.gross_losses);

    const rows = Array.isArray(data.rows) ? data.rows : [];
    if (!rows.length) {
      bodyEl.innerHTML = `<tr><td colspan="5" class="empty">No attributable open positions.</td></tr>`;
    } else {
      bodyEl.innerHTML = rows.map((row) => `
        <tr>
          <td class="instrument"><strong>${escapeHtml(row.ticker)}</strong><small>${escapeHtml(row.name)}</small></td>
          <td class="num ${toneClass(row.pnl)}">${money(row.pnl, currency)}</td>
          <td class="num ${toneClass(row.net_contribution_pct)}">${pct(row.net_contribution_pct)}</td>
          <td class="num">${pct(row.gross_share_pct)}</td>
          <td class="num ${toneClass(row.fx_impact)}">${money(row.fx_impact, currency)}</td>
        </tr>
      `).join("");
    }

    const difference = data.reconciliation_difference;
    const coverage = `${data.accounted_positions}/${data.total_positions} open positions attributed`;
    if (typeof difference === "number" && Number.isFinite(difference)) {
      const tolerance = Math.max(0.01, Math.abs(data.account_unrealized_pl || 0) * 0.01);
      noteEl.textContent = Math.abs(difference) > tolerance
        ? `${coverage}. Position P/L does not fully reconcile to the account total; residual: ${money(difference, currency)}.`
        : `${coverage}. Position-level P/L reconciles to the account unrealized P/L within 1%.`;
    } else {
      noteEl.textContent = coverage;
    }
  }

  async function refresh() {
    try {
      render(await getJSON("/api/pnl-attribution"));
    } catch (error) {
      renderUnavailable({}, `P/L attribution error: ${error.message}`);
    }
  }

  refresh();
  setInterval(refresh, 6000);
})();
