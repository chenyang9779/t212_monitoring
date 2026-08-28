(() => {
  const root = document.getElementById("allocationPanel");
  if (!root) return;

  const totalEl = document.getElementById("allocationTotal");
  const top1El = document.getElementById("allocationTop1");
  const top3El = document.getElementById("allocationTop3");
  const bodyEl = document.getElementById("allocationBody");
  const noteEl = document.getElementById("allocationNote");

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
    return `${value.toFixed(2)}%`;
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

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function renderUnavailable(message) {
    totalEl.textContent = "—";
    top1El.textContent = "—";
    top3El.textContent = "—";
    bodyEl.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
    noteEl.textContent = "Weights require Trading 212 walletImpact.currentValue in the account currency; instrument-currency values are never mixed.";
  }

  function render(latest) {
    const account = latest.account;
    const positions = Array.isArray(latest.positions) ? latest.positions : [];
    if (!account) {
      renderUnavailable("Waiting for account data…");
      return;
    }

    const currency = account.currency || "";
    const valid = positions
      .filter((position) =>
        typeof position.wallet_current_value === "number"
        && Number.isFinite(position.wallet_current_value)
        && position.wallet_current_value >= 0
        && (!position.wallet_currency || !currency || position.wallet_currency === currency)
      )
      .map((position) => ({
        ticker: position.ticker,
        name: position.name,
        value: position.wallet_current_value,
      }));

    if (!valid.length) {
      renderUnavailable("Account-currency position values are not available yet.");
      return;
    }

    const brokerInvested = account.investments_current_value;
    const summed = valid.reduce((sum, position) => sum + position.value, 0);
    const denominator = typeof brokerInvested === "number" && Number.isFinite(brokerInvested) && brokerInvested > 0
      ? brokerInvested
      : summed;

    if (!(denominator > 0)) {
      renderUnavailable("No invested position value to allocate.");
      return;
    }

    const rows = valid
      .map((position) => ({ ...position, weight: position.value / denominator * 100 }))
      .sort((a, b) => b.weight - a.weight);

    const top1 = rows[0]?.weight ?? 0;
    const top3 = rows.slice(0, 3).reduce((sum, position) => sum + position.weight, 0);

    totalEl.textContent = money(denominator, currency);
    top1El.textContent = pct(top1);
    top3El.textContent = pct(top3);

    bodyEl.innerHTML = rows.map((position) => `
      <div class="allocation-row">
        <div class="allocation-label">
          <strong>${escapeHtml(position.ticker)}</strong>
          <small>${escapeHtml(position.name)}</small>
        </div>
        <div class="allocation-bar-wrap" aria-hidden="true">
          <div class="allocation-bar" style="width:${Math.min(Math.max(position.weight, 0), 100).toFixed(3)}%"></div>
        </div>
        <div class="allocation-value">
          <strong>${pct(position.weight)}</strong>
          <small>${money(position.value, currency)}</small>
        </div>
      </div>
    `).join("");

    const difference = typeof brokerInvested === "number" && Number.isFinite(brokerInvested)
      ? Math.abs(summed - brokerInvested)
      : 0;
    const tolerance = denominator * 0.01;
    noteEl.textContent = difference > tolerance
      ? `Trading 212 account invested value and summed wallet-impact values differ by ${money(difference, currency)}; weights use the broker account invested value.`
      : `Values and weights are in ${currency || "the account currency"} using Trading 212 wallet impact data.`;
  }

  async function refresh() {
    try {
      render(await getJSON("/api/latest"));
    } catch (error) {
      renderUnavailable(`Allocation data error: ${error.message}`);
    }
  }

  refresh();
  setInterval(refresh, 6000);
})();
