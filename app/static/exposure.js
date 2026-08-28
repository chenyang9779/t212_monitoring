(() => {
  const panel = document.getElementById("exposurePanel");
  if (!panel) return;

  const coverageEl = document.getElementById("exposureCoverage");
  const investedEl = document.getElementById("exposureInvested");
  const currenciesEl = document.getElementById("exposureCurrencies");
  const typesEl = document.getElementById("exposureTypes");
  const noteEl = document.getElementById("exposureNote");
  const refreshButton = document.getElementById("exposureRefresh");

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[ch]));
  }

  function pct(value) {
    return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
  }

  function money(value, currency) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: currency || "GBP",
        maximumFractionDigits: 2
      }).format(value);
    } catch (_) {
      return `${value.toFixed(2)} ${currency || ""}`.trim();
    }
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function renderGroups(container, groups, accountCurrency, emptyMessage) {
    if (!Array.isArray(groups) || !groups.length) {
      container.innerHTML = `<div class="empty">${escapeHtml(emptyMessage)}</div>`;
      return;
    }
    container.innerHTML = groups.map((group) => `
      <div class="exposure-row">
        <div class="exposure-label"><strong>${escapeHtml(group.name || "UNKNOWN")}</strong></div>
        <div class="exposure-bar-wrap" aria-hidden="true"><div class="exposure-bar" style="width:${Math.max(0, Math.min(100, Number(group.weight_pct) || 0))}%"></div></div>
        <div class="exposure-value"><strong>${pct(group.weight_pct)}</strong><small>${money(group.account_value, accountCurrency)}</small></div>
      </div>
    `).join("");
  }

  function render(payload) {
    const accountCurrency = payload.account_currency || "";
    coverageEl.textContent = pct(payload.metadata_coverage_pct);
    investedEl.textContent = money(payload.invested_value, accountCurrency);
    renderGroups(currenciesEl, payload.currency_exposure, accountCurrency, "No currency exposure available.");
    renderGroups(typesEl, payload.type_exposure, accountCurrency, "No instrument-type exposure available.");

    const notes = [];
    if (payload.metadata_stale) notes.push("Using cached metadata because the latest metadata refresh failed.");
    if (payload.metadata_error) notes.push(`Metadata: ${payload.metadata_error}`);
    notes.push("Currency exposure is based on instrument quote currency, not issuer domicile or revenue exposure.");
    notes.push("Sector/country exposure is intentionally omitted until a provider supplies those classifications.");
    if (payload.metadata_refreshed_at) {
      notes.push(`Metadata refreshed ${new Date(payload.metadata_refreshed_at).toLocaleString()}.`);
    }
    noteEl.textContent = notes.join(" ");
  }

  async function refresh(force = false) {
    refreshButton.disabled = true;
    try {
      const payload = await getJSON(`/api/exposure${force ? "?refresh_metadata=true" : ""}`);
      render(payload);
    } catch (error) {
      currenciesEl.innerHTML = `<div class="empty">Exposure unavailable.</div>`;
      typesEl.innerHTML = `<div class="empty">Exposure unavailable.</div>`;
      noteEl.textContent = `Exposure error: ${error.message}`;
    } finally {
      refreshButton.disabled = false;
    }
  }

  refreshButton.addEventListener("click", () => refresh(true));
  refresh();
  setInterval(() => refresh(false), 300000);
})();
