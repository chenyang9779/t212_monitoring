(() => {
  if (!("EventSource" in window)) return;

  const $ = (id) => document.getElementById(id);
  const source = new EventSource("/api/stream");
  let connected = false;

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[ch]));
  }

  function number(value, digits = 4) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
  }

  function pct(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  }

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

  function tone(el, value) {
    if (!el) return;
    el.classList.remove("good-text", "bad-text");
    if (typeof value === "number" && Number.isFinite(value)) {
      el.classList.add(value >= 0 ? "good-text" : "bad-text");
    }
  }

  function renderPortfolio(payload) {
    const account = payload?.account;
    const positions = Array.isArray(payload?.positions) ? payload.positions : [];
    if (!account) return;

    const currency = account.currency || "";
    const totalValue = $("totalValue");
    const invested = $("invested");
    const cash = $("cash");
    const unrealized = $("unrealized");
    const unrealizedPct = $("unrealizedPct");
    const realized = $("realized");
    const positionCount = $("positionCount");
    const lastSync = $("lastSync");
    const positionsBody = $("positionsBody");

    if (totalValue) totalValue.textContent = money(account.total_value, currency);
    if (invested) invested.textContent = money(account.investments_current_value, currency);
    if (cash) cash.textContent = money(account.available_to_trade, currency);
    if (unrealized) unrealized.textContent = money(account.unrealized_pl, currency);
    if (unrealizedPct) unrealizedPct.textContent = pct(account.unrealized_pl_pct);
    if (realized) realized.textContent = money(account.realized_pl, currency);
    if (positionCount) positionCount.textContent = String(positions.length);
    if (lastSync) {
      lastSync.textContent = `Last sync: ${payload.last_sync ? new Date(payload.last_sync).toLocaleString() : "—"}`;
    }
    tone(unrealized, account.unrealized_pl);
    tone(unrealizedPct, account.unrealized_pl_pct);
    tone(realized, account.realized_pl);

    if (positionsBody) {
      const filter = $("filter")?.value?.trim().toLowerCase() || "";
      const rows = positions.filter((position) => `${position.ticker} ${position.name}`.toLowerCase().includes(filter));
      positionsBody.innerHTML = rows.length ? rows.map((position) => {
        const pnlClass = typeof position.pnl_local === "number"
          ? (position.pnl_local >= 0 ? "good-text" : "bad-text")
          : "";
        return `<tr>
          <td class="instrument"><strong>${escapeHtml(position.ticker)}</strong><small>${escapeHtml(position.name)}</small></td>
          <td class="num">${number(position.quantity, 6)}</td>
          <td class="num">${money(position.average_price, position.currency)}</td>
          <td class="num">${money(position.current_price, position.currency)}</td>
          <td class="num">${money(position.market_value_local, position.currency)}</td>
          <td class="num ${pnlClass}">${money(position.pnl_local, position.currency)}</td>
          <td class="num ${pnlClass}">${pct(position.pnl_pct)}</td>
        </tr>`;
      }).join("") : `<tr><td colspan="7" class="empty">No matching positions.</td></tr>`;
    }

    window.dispatchEvent(new CustomEvent("t212:portfolio", { detail: payload }));
  }

  function renderReady(payload) {
    const status = payload?.status || {};
    const latest = payload?.latest || {};
    const envBadge = $("envBadge");
    const statusDot = $("statusDot");
    const statusText = $("statusText");
    const errorBox = $("errorBox");

    if (envBadge && status.environment) envBadge.textContent = status.environment;
    if (statusDot) statusDot.className = `dot ${status.connected ? "good" : (status.last_error ? "bad" : "")}`;
    if (statusText) {
      statusText.textContent = status.connected
        ? `Connected · SSE · ${status.poll_seconds}s`
        : "Connecting live stream…";
    }
    if (errorBox && status.last_error) {
      errorBox.textContent = status.last_error;
      errorBox.classList.remove("hidden");
    }
    if (latest.account) renderPortfolio(latest);
  }

  function refreshPositionEvents() {
    fetch("/api/position-events?limit=50", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(String(response.status))))
      .then((payload) => {
        const body = $("positionEventsBody");
        if (!body) return;
        const items = Array.isArray(payload.items) ? payload.items : [];
        if (!items.length) {
          body.innerHTML = `<tr><td colspan="7" class="empty">No position activity recorded yet.</td></tr>`;
          return;
        }
        body.innerHTML = items.map((event) => {
          const deltaClass = event.delta_quantity > 0 ? "good-text" : "bad-text";
          const deltaText = `${event.delta_quantity > 0 ? "+" : ""}${number(event.delta_quantity, 6)}`;
          return `<tr>
            <td>${new Date(event.ts).toLocaleString()}</td>
            <td class="instrument"><strong>${escapeHtml(event.ticker)}</strong><small>${escapeHtml(event.name)}</small></td>
            <td><span class="event-badge event-${escapeHtml(String(event.event_type).toLowerCase())}">${escapeHtml(event.event_type)}</span></td>
            <td class="num">${number(event.quantity_before, 6)}</td>
            <td class="num">${number(event.quantity_after, 6)}</td>
            <td class="num ${deltaClass}">${deltaText}</td>
            <td class="num">${money(event.current_price, event.currency)}</td>
          </tr>`;
        }).join("");
      })
      .catch(() => {});
  }

  function refreshAlerts() {
    fetch("/api/alerts?limit=30", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(String(response.status))))
      .then((payload) => {
        const alerts = $("alerts");
        if (!alerts) return;
        const items = Array.isArray(payload.items) ? payload.items : [];
        alerts.innerHTML = items.length ? items.map((alert) => `<div class="alert">
          <span class="alert-severity">${escapeHtml(alert.severity)}</span>
          <span>${escapeHtml(alert.message)}</span>
          <time>${new Date(alert.ts).toLocaleString()}</time>
        </div>`).join("") : `<div class="empty">No alerts.</div>`;
      })
      .catch(() => {});
  }

  source.addEventListener("open", () => {
    connected = true;
    document.documentElement.dataset.liveStream = "connected";
  });

  source.addEventListener("ready", (event) => {
    try { renderReady(JSON.parse(event.data)); } catch (_) {}
  });

  source.addEventListener("portfolio", (event) => {
    try { renderPortfolio(JSON.parse(event.data)); } catch (_) {}
  });

  source.addEventListener("snapshot", (event) => {
    let detail = null;
    try { detail = JSON.parse(event.data); } catch (_) {}
    window.dispatchEvent(new CustomEvent("t212:snapshot", { detail }));
  });

  source.addEventListener("position_event", (event) => {
    refreshPositionEvents();
    let detail = null;
    try { detail = JSON.parse(event.data); } catch (_) {}
    window.dispatchEvent(new CustomEvent("t212:position-event", { detail }));
  });

  source.addEventListener("alert", (event) => {
    refreshAlerts();
    let detail = null;
    try { detail = JSON.parse(event.data); } catch (_) {}
    window.dispatchEvent(new CustomEvent("t212:alert", { detail }));
  });

  source.addEventListener("monitor_error", (event) => {
    const errorBox = $("errorBox");
    let payload = {};
    try { payload = JSON.parse(event.data); } catch (_) {}
    if (errorBox && payload.error) {
      errorBox.textContent = payload.error;
      errorBox.classList.remove("hidden");
    }
  });

  source.addEventListener("error", () => {
    connected = false;
    document.documentElement.dataset.liveStream = "reconnecting";
    const statusText = $("statusText");
    if (statusText) statusText.textContent = "SSE reconnecting · polling fallback active";
  });

  window.addEventListener("beforeunload", () => source.close(), { once: true });
  window.t212LiveStreamConnected = () => connected;
})();
