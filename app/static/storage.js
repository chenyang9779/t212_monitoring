(() => {
  const panel = document.getElementById("storagePanel");
  if (!panel) return;

  const totalEl = document.getElementById("storageTotal");
  const dbEl = document.getElementById("storageDb");
  const reclaimableEl = document.getElementById("storageReclaimable");
  const retentionEl = document.getElementById("storageRetention");
  const bodyEl = document.getElementById("storageBody");
  const noteEl = document.getElementById("storageNote");
  const refreshButton = document.getElementById("storageRefresh");

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'\"]/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '\"': "&quot;"
    }[ch]));
  }

  function bytes(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let amount = value;
    let index = 0;
    while (amount >= 1024 && index < units.length - 1) {
      amount /= 1024;
      index += 1;
    }
    return `${amount.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
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

  function render(payload) {
    totalEl.textContent = bytes(payload.total_files_bytes);
    dbEl.textContent = bytes(payload.db_bytes);
    reclaimableEl.textContent = bytes(payload.reclaimable_bytes);
    retentionEl.textContent = payload.retention_enabled ? `${payload.retention_days}d` : "Disabled";

    const tables = Array.isArray(payload.tables) ? payload.tables : [];
    if (!tables.length) {
      bodyEl.innerHTML = `<tr><td colspan="5" class="empty">No storage tables found.</td></tr>`;
    } else {
      bodyEl.innerHTML = tables.map((table) => `
        <tr>
          <td><strong>${escapeHtml(table.table)}</strong></td>
          <td class="num">${Number(table.rows || 0).toLocaleString()}</td>
          <td>${date(table.oldest_ts)}</td>
          <td>${date(table.newest_ts)}</td>
          <td>${table.retention_managed ? (payload.retention_enabled ? `${payload.retention_days}d raw` : "Managed / disabled") : "Preserved"}</td>
        </tr>
      `).join("");
    }

    const parts = [
      `WAL ${bytes(payload.wal_bytes)}`,
      `SHM ${bytes(payload.shm_bytes)}`,
      `${payload.freelist_pages || 0} free pages`
    ];
    if (payload.last_maintenance) {
      parts.push(`last cleanup ${date(payload.last_maintenance)}`);
      parts.push(`${payload.maintenance_deleted_total || 0} rows deleted`);
    }
    if (payload.maintenance_error) parts.push(`maintenance error: ${payload.maintenance_error}`);
    if (!payload.retention_enabled) parts.push("set T212_RAW_RETENTION_DAYS to enable automatic cleanup");
    noteEl.textContent = parts.join(" · ");
  }

  async function refresh() {
    refreshButton.disabled = true;
    try {
      render(await getJSON("/api/storage"));
    } catch (error) {
      bodyEl.innerHTML = `<tr><td colspan="5" class="empty">Storage diagnostics error: ${escapeHtml(error.message)}</td></tr>`;
      noteEl.textContent = "Storage diagnostics could not be loaded.";
    } finally {
      refreshButton.disabled = false;
    }
  }

  refreshButton.addEventListener("click", refresh);
  refresh();
  setInterval(refresh, 60000);
})();
