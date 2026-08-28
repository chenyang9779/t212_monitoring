(() => {
  const panel = document.getElementById("brokerActivityPanel");
  if (!panel) return;

  const head = document.getElementById("brokerHead");
  const body = document.getElementById("brokerBody");
  const note = document.getElementById("brokerNote");
  const refreshButton = document.getElementById("brokerRefresh");
  const loadMoreButton = document.getElementById("brokerLoadMore");
  const tabs = Array.from(panel.querySelectorAll(".broker-tab"));

  let currentView = "pending";
  let nextPagePath = null;
  let currentItems = [];
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

  function finite(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  function pick(obj, paths) {
    for (const path of paths) {
      let current = obj;
      let ok = true;
      for (const key of path.split(".")) {
        if (current == null || typeof current !== "object" || !(key in current)) {
          ok = false;
          break;
        }
        current = current[key];
      }
      if (ok && current !== null && current !== undefined && current !== "") return current;
    }
    return null;
  }

  function formatNumber(value, digits = 6) {
    const numeric = finite(value);
    if (numeric === null) return value == null ? "—" : escapeHtml(value);
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(numeric);
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? escapeHtml(value) : escapeHtml(date.toLocaleString());
  }

  function formatMoney(value, currency) {
    const numeric = finite(value);
    if (numeric === null) return value == null ? "—" : escapeHtml(value);
    if (currency) {
      try {
        return new Intl.NumberFormat(undefined, {
          style: "currency",
          currency,
          maximumFractionDigits: 2,
        }).format(numeric);
      } catch (_) {}
    }
    return formatNumber(numeric, 2);
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function setLoading(message = "Loading broker activity…") {
    head.innerHTML = "";
    body.innerHTML = `<tr><td class="empty">${escapeHtml(message)}</td></tr>`;
    note.textContent = "This panel only performs GET requests.";
    loadMoreButton.classList.add("hidden");
  }

  function setUnavailable(payload) {
    head.innerHTML = "";
    const status = payload?.status_code ? `HTTP ${payload.status_code}` : "Unavailable";
    body.innerHTML = `<tr><td class="empty">${escapeHtml(status)} — ${escapeHtml(payload?.error || "Trading 212 did not return this data.")}</td></tr>`;
    note.textContent = "Check that this API key has the corresponding read-only Orders/History/Transactions permission. Monitoring continues even if this view is unavailable.";
    loadMoreButton.classList.add("hidden");
  }

  function tickerOf(item) {
    return pick(item, ["ticker", "instrument.ticker", "order.ticker", "order.instrument.ticker"]) || "—";
  }

  function sideOf(item) {
    const side = pick(item, ["side", "order.side"]);
    if (side) return String(side).toUpperCase();
    const quantity = pick(item, ["quantity", "order.quantity"]);
    return typeof quantity === "number" ? (quantity >= 0 ? "BUY" : "SELL") : "—";
  }

  function renderPending(items) {
    head.innerHTML = `<tr>
      <th>Created</th><th>Instrument</th><th>Side</th><th>Type</th><th>Status</th>
      <th class="num">Qty</th><th class="num">Limit</th><th class="num">Stop</th>
    </tr>`;

    if (!items.length) {
      body.innerHTML = `<tr><td colspan="8" class="empty">No pending orders.</td></tr>`;
      note.textContent = "No currently pending Trading 212 orders were returned.";
      return;
    }

    body.innerHTML = items.map((item) => {
      const currency = pick(item, ["currency", "instrument.currency"]);
      return `<tr>
        <td>${formatDate(pick(item, ["createdAt", "createdDate", "dateCreated", "created"]))}</td>
        <td><strong>${escapeHtml(tickerOf(item))}</strong></td>
        <td>${escapeHtml(sideOf(item))}</td>
        <td>${escapeHtml(pick(item, ["type", "orderType"]) || "—")}</td>
        <td>${escapeHtml(pick(item, ["status"]) || "—")}</td>
        <td class="num">${formatNumber(pick(item, ["quantity"]))}</td>
        <td class="num">${formatMoney(pick(item, ["limitPrice", "limit"]), currency)}</td>
        <td class="num">${formatMoney(pick(item, ["stopPrice", "stop"]), currency)}</td>
      </tr>`;
    }).join("");
    note.textContent = `${items.length} pending order${items.length === 1 ? "" : "s"}. Read-only view.`;
  }

  function renderHistory(items) {
    head.innerHTML = `<tr>
      <th>Time</th><th>Instrument</th><th>Side</th><th>Type</th><th>Status</th>
      <th class="num">Ordered</th><th class="num">Filled</th><th class="num">Avg fill</th>
    </tr>`;

    if (!items.length) {
      body.innerHTML = `<tr><td colspan="8" class="empty">No historical orders returned.</td></tr>`;
      note.textContent = "Trading 212 returned no historical orders for this page.";
      return;
    }

    body.innerHTML = items.map((item) => {
      const currency = pick(item, ["currency", "instrument.currency", "order.currency", "order.instrument.currency"]);
      return `<tr>
        <td>${formatDate(pick(item, ["dateCreated", "createdAt", "createdDate", "filledAt", "dateExecuted", "order.dateCreated"]))}</td>
        <td><strong>${escapeHtml(tickerOf(item))}</strong></td>
        <td>${escapeHtml(sideOf(item))}</td>
        <td>${escapeHtml(pick(item, ["type", "orderType", "order.type", "order.orderType"]) || "—")}</td>
        <td>${escapeHtml(pick(item, ["status", "order.status"]) || "—")}</td>
        <td class="num">${formatNumber(pick(item, ["quantity", "orderedQuantity", "order.quantity"]))}</td>
        <td class="num">${formatNumber(pick(item, ["filledQuantity", "executedQuantity", "order.filledQuantity"]))}</td>
        <td class="num">${formatMoney(pick(item, ["fillPrice", "averagePrice", "filledPrice", "order.fillPrice"]), currency)}</td>
      </tr>`;
    }).join("");
    note.textContent = `${items.length} historical order${items.length === 1 ? "" : "s"} loaded.`;
  }

  function renderTransactions(items) {
    head.innerHTML = `<tr>
      <th>Time</th><th>Type</th><th>Reference</th><th>Instrument</th>
      <th class="num">Quantity</th><th class="num">Amount</th><th class="num">Fee</th>
    </tr>`;

    if (!items.length) {
      body.innerHTML = `<tr><td colspan="7" class="empty">No transactions returned.</td></tr>`;
      note.textContent = "Trading 212 returned no transactions for this page.";
      return;
    }

    body.innerHTML = items.map((item) => {
      const currency = pick(item, ["currency", "instrument.currency"]);
      return `<tr>
        <td>${formatDate(pick(item, ["dateTime", "date", "createdAt", "timestamp"]))}</td>
        <td>${escapeHtml(pick(item, ["type", "transactionType"]) || "—")}</td>
        <td>${escapeHtml(pick(item, ["reference", "referenceId", "id"]) || "—")}</td>
        <td><strong>${escapeHtml(tickerOf(item))}</strong></td>
        <td class="num">${formatNumber(pick(item, ["quantity"]))}</td>
        <td class="num">${formatMoney(pick(item, ["amount", "value", "total"]), currency)}</td>
        <td class="num">${formatMoney(pick(item, ["fee", "fees", "commission"]), currency)}</td>
      </tr>`;
    }).join("");
    note.textContent = `${items.length} transaction${items.length === 1 ? "" : "s"} loaded.`;
  }

  function renderCurrent() {
    if (currentView === "pending") renderPending(currentItems);
    else if (currentView === "history") renderHistory(currentItems);
    else renderTransactions(currentItems);

    if (nextPagePath && currentView !== "pending") loadMoreButton.classList.remove("hidden");
    else loadMoreButton.classList.add("hidden");
  }

  function endpoint(loadMore = false) {
    if (currentView === "pending") return "/api/orders/pending";
    const base = currentView === "history" ? "/api/orders/history?limit=50" : "/api/transactions?limit=50";
    if (!loadMore || !nextPagePath) return base;
    return `${base}&next_page_path=${encodeURIComponent(nextPagePath)}`;
  }

  async function refresh(loadMore = false) {
    const id = ++requestId;
    if (!loadMore) {
      currentItems = [];
      nextPagePath = null;
      setLoading();
    } else {
      loadMoreButton.disabled = true;
      loadMoreButton.textContent = "Loading…";
    }

    try {
      const payload = await getJSON(endpoint(loadMore));
      if (id !== requestId) return;
      if (!payload.available) {
        setUnavailable(payload);
        return;
      }
      const items = Array.isArray(payload.items) ? payload.items : [];
      currentItems = loadMore ? currentItems.concat(items) : items;
      nextPagePath = payload.next_page_path || null;
      renderCurrent();
    } catch (error) {
      if (id !== requestId) return;
      head.innerHTML = "";
      body.innerHTML = `<tr><td class="empty">Broker activity error: ${escapeHtml(error.message)}</td></tr>`;
      note.textContent = "The rest of the portfolio monitor is unaffected.";
      loadMoreButton.classList.add("hidden");
    } finally {
      loadMoreButton.disabled = false;
      loadMoreButton.textContent = "Load more";
    }
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const nextView = tab.dataset.view;
      if (!nextView || nextView === currentView) return;
      currentView = nextView;
      tabs.forEach((candidate) => candidate.classList.toggle("active", candidate === tab));
      refresh(false);
    });
  });

  refreshButton.addEventListener("click", () => refresh(false));
  loadMoreButton.addEventListener("click", () => refresh(true));

  refresh(false);
})();
