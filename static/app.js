// DebtFund Frontend — Vanilla JS
(function () {
  "use strict";

  // --- State ---
  let currentJobId = null;
  let pollTimer = null;
  let pollInterval = 2000;
  let resultData = null;
  let sortCol = null;
  let sortAsc = true;

  // --- DOM refs ---
  const $ = (sel) => document.querySelector(sel);
  const keyInput = $("#api-key-input");
  const keyStatus = $("#key-status");
  const dropZone = $("#drop-zone");
  const fileInput = $("#file-input");
  const uploadStatus = $("#upload-status");
  const progressSection = $("#progress-section");
  const progressFill = $("#progress-fill");
  const progressText = $("#progress-text");
  const errorSection = $("#error-section");
  const errorMessage = $("#error-message");
  const resultsSection = $("#results-section");

  // --- API helpers ---
  function apiKey() {
    return keyInput.value || localStorage.getItem("df_api_key") || "";
  }

  async function apiFetch(path, opts = {}) {
    const key = apiKey();
    if (!key) throw new Error("API key is required");
    const headers = { Authorization: "Bearer " + key, ...(opts.headers || {}) };
    const res = await fetch(path, { ...opts, headers });
    if (res.status === 401) throw new Error("Invalid API key (401)");
    if (res.status === 413) throw new Error("File too large");
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Request failed (" + res.status + ")");
    }
    return res;
  }

  // --- Upload ---
  async function uploadFile(file) {
    if (!file) return;
    if (!file.name.match(/\.xlsx?$/i)) {
      uploadStatus.textContent = "Only .xlsx and .xls files are accepted.";
      return;
    }
    hide(errorSection);
    hide(resultsSection);
    show(progressSection);
    progressFill.style.width = "5%";
    progressText.textContent = "Uploading " + file.name + "...";
    uploadStatus.textContent = "";

    try {
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch("/api/v1/files/upload", { method: "POST", body: form });
      const data = await res.json();

      if (data.status === "duplicate") {
        progressText.textContent = "Duplicate file detected. Fetching existing results...";
        currentJobId = data.job_id;
      } else {
        currentJobId = data.job_id;
        progressText.textContent = "Extraction started...";
      }
      progressFill.style.width = "15%";
      startPolling();
    } catch (err) {
      showError(err.message);
    }
  }

  // --- Polling ---
  function startPolling() {
    pollInterval = 2000;
    poll();
  }

  async function poll() {
    if (!currentJobId) return;
    try {
      const res = await apiFetch("/api/v1/jobs/" + currentJobId);
      const job = await res.json();

      if (job.status === "completed") {
        progressFill.style.width = "100%";
        progressText.textContent = "Extraction complete!";
        await loadResults();
        return;
      }
      if (job.status === "failed") {
        showError(job.error || "Extraction failed");
        return;
      }

      // Still processing
      const pct = job.progress_percent || 20;
      progressFill.style.width = Math.min(pct, 95) + "%";
      progressText.textContent = (job.current_stage || "processing") + "...";

      // Backoff: 2s -> 4s -> 8s, max 15s
      pollInterval = Math.min(pollInterval * 1.5, 15000);
      pollTimer = setTimeout(poll, pollInterval);
    } catch (err) {
      showError(err.message);
    }
  }

  // --- Load results ---
  async function loadResults() {
    try {
      const res = await apiFetch("/api/v1/jobs/" + currentJobId + "/export?format=json");
      resultData = await res.json();
      renderResults(resultData);
      hide(progressSection);
      show(resultsSection);
    } catch (err) {
      showError(err.message);
    }
  }

  // --- Render ---
  function renderResults(data) {
    // Summary
    const items = data.line_items || [];
    const validation = data.validation || {};
    const conf = validation.overall_confidence;

    $("#stat-sheets").textContent = (data.sheets || []).length;
    $("#stat-items").textContent = items.length;
    $("#stat-confidence").textContent = conf != null ? (conf * 100).toFixed(0) + "%" : "N/A";
    $("#stat-tokens").textContent = (data.tokens_used || 0).toLocaleString();
    $("#stat-cost").textContent = "$" + (data.cost_usd || 0).toFixed(3);

    renderLineItems(items);
    renderTriage(data.triage || []);
    renderValidation(validation);
  }

  function renderLineItems(items) {
    const tbody = $("#line-items-table tbody");
    tbody.innerHTML = "";
    items.forEach((item) => {
      const tr = document.createElement("tr");
      const conf = item.confidence || 0;
      const badgeClass = conf >= 0.8 ? "badge-high" : conf >= 0.5 ? "badge-mid" : "badge-low";
      const vals = item.values || {};
      const valStr = Object.entries(vals)
        .map(([k, v]) => k + ": " + formatNum(v))
        .join(", ");

      tr.innerHTML =
        "<td>" + esc(item.sheet || "") + "</td>" +
        "<td>" + esc(item.original_label || "") + "</td>" +
        "<td><code>" + esc(item.canonical_name || "") + "</code></td>" +
        '<td><span class="badge ' + badgeClass + '">' + (conf * 100).toFixed(0) + "%</span></td>" +
        '<td class="values-cell">' + esc(valStr || "-") + "</td>";
      tbody.appendChild(tr);
    });
  }

  function renderTriage(triage) {
    const tbody = $("#triage-table tbody");
    tbody.innerHTML = "";
    triage.forEach((t) => {
      const tr = document.createElement("tr");
      const tierClass = "tier-" + (t.tier || 4);
      tr.innerHTML =
        "<td>" + esc(t.sheet_name || "") + "</td>" +
        '<td><span class="badge ' + tierClass + '">Tier ' + (t.tier || "?") + "</span></td>" +
        "<td>" + esc(t.decision || "") + "</td>" +
        "<td>" + esc(t.rationale || "") + "</td>";
      tbody.appendChild(tr);
    });
  }

  function renderValidation(val) {
    const el = $("#validation-content");
    if (!val || !val.overall_confidence) {
      el.innerHTML = '<p class="val-overall">No validation data available.</p>';
      return;
    }
    const conf = val.overall_confidence;
    const badgeClass = conf >= 0.8 ? "badge-high" : conf >= 0.5 ? "badge-mid" : "badge-low";
    let html = '<p class="val-overall">Overall Confidence: <span class="badge ' + badgeClass + '">' +
      (conf * 100).toFixed(0) + "%</span></p>";

    const flags = val.flags || [];
    if (flags.length) {
      html += "<h4>Flags (" + flags.length + ")</h4>";
      flags.forEach((f) => {
        html += '<div class="val-flag">' + esc(f.message || f.rule || JSON.stringify(f)) + "</div>";
      });
    } else {
      html += "<p>No validation flags raised.</p>";
    }
    el.innerHTML = html;
  }

  // --- Sorting ---
  function setupSorting() {
    document.querySelectorAll("#line-items-table th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const col = th.dataset.sort;
        if (sortCol === col) { sortAsc = !sortAsc; } else { sortCol = col; sortAsc = true; }
        if (!resultData) return;
        const items = [...(resultData.line_items || [])];
        items.sort((a, b) => {
          let va = a[col] || "", vb = b[col] || "";
          if (typeof va === "number" && typeof vb === "number") return sortAsc ? va - vb : vb - va;
          va = String(va).toLowerCase();
          vb = String(vb).toLowerCase();
          return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        });
        renderLineItems(items);
      });
    });
  }

  // --- Export ---
  function setupExport() {
    $("#export-json").addEventListener("click", async () => {
      if (!currentJobId) return;
      try {
        const res = await apiFetch("/api/v1/jobs/" + currentJobId + "/export?format=json");
        const blob = await res.blob();
        download(blob, "extraction_" + currentJobId.slice(0, 8) + ".json");
      } catch (err) { alert(err.message); }
    });

    $("#export-csv").addEventListener("click", async () => {
      if (!currentJobId) return;
      try {
        const res = await apiFetch("/api/v1/jobs/" + currentJobId + "/export?format=csv");
        const blob = await res.blob();
        download(blob, "extraction_" + currentJobId.slice(0, 8) + ".csv");
      } catch (err) { alert(err.message); }
    });
  }

  function download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  // --- Tabs ---
  function setupTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
        tab.classList.add("active");
        $("#tab-" + tab.dataset.tab).classList.add("active");
      });
    });
  }

  // --- Drag & Drop ---
  function setupDragDrop() {
    dropZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) uploadFile(fileInput.files[0]);
    });

    dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("dragover"); });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
      if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
    });
  }

  // --- API Key ---
  function setupAuth() {
    const saved = localStorage.getItem("df_api_key");
    if (saved) {
      keyInput.value = saved;
      keyStatus.textContent = "Key loaded from storage.";
    }
    $("#save-key-btn").addEventListener("click", () => {
      const val = keyInput.value.trim();
      if (val) {
        localStorage.setItem("df_api_key", val);
        keyStatus.textContent = "Key saved.";
      }
    });
  }

  // --- Helpers ---
  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }
  function showError(msg) {
    hide(progressSection);
    errorMessage.textContent = msg;
    show(errorSection);
    if (pollTimer) clearTimeout(pollTimer);
  }
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
  function formatNum(v) {
    if (v == null) return "-";
    if (typeof v === "number") return v.toLocaleString();
    return String(v);
  }

  // --- Init ---
  setupAuth();
  setupDragDrop();
  setupTabs();
  setupSorting();
  setupExport();
})();
