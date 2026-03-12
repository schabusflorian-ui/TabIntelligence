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
  let pendingCorrections = {};
  let activeDropdown = null;

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
    pendingCorrections = {};
    updatePendingBanner();
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

      if (job.status === "completed" || job.status === "needs_review") {
        progressFill.style.width = "100%";
        progressText.textContent = job.status === "needs_review"
          ? "Extraction complete (needs review)"
          : "Extraction complete!";
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

      // Display friendly stage names with stage count
      var stageDisplayNames = {
        parsing: "Parsing Excel",
        triage: "Classifying Sheets",
        mapping: "Mapping Labels",
        validation: "Validating Data",
        enhanced_mapping: "Refining Mappings",
      };
      var stageName = stageDisplayNames[job.current_stage] || job.current_stage || "Processing";
      var stagesCompleted = job.stages_completed;
      var totalStages = job.total_stages || 5;
      if (stagesCompleted != null) {
        progressText.textContent = "Stage " + stagesCompleted + " of " + totalStages + ": " + stageName;
      } else {
        progressText.textContent = stageName + "...";
      }

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

  async function reviewJob(decision) {
    if (!currentJobId) return;
    var reason = decision === "reject" ? prompt("Rejection reason (optional):") : null;
    try {
      await apiFetch("/api/v1/jobs/" + currentJobId + "/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: decision, reason: reason }),
      });
      var reviewEl = document.getElementById("review-actions");
      if (reviewEl) reviewEl.innerHTML = "<em>" + decision + "d</em>";
    } catch (err) {
      alert("Review failed: " + err.message);
    }
  }

  // --- Render ---
  function renderResults(data) {
    // Summary
    const items = data.line_items || [];
    const validation = data.validation || {};
    const conf = validation.overall_confidence;

    // Quality score badge
    const quality = data.quality || {};
    const qualityEl = $("#stat-quality");
    if (quality.letter_grade) {
      var grade = quality.letter_grade;
      var gradeColors = { A: "badge-high", B: "badge-high", C: "badge-mid", D: "badge-low", F: "badge-low" };
      qualityEl.textContent = grade + " (" + (quality.numeric_score * 100).toFixed(0) + "%)";
      qualityEl.className = "quality-badge badge " + (gradeColors[grade] || "badge-mid");
      // Build tooltip with label and model type
      var tooltip = quality.label || "";
      if (quality.model_type) {
        tooltip += " | Model: " + quality.model_type;
      }
      qualityEl.title = tooltip;
      // Quality gate warning + review buttons
      if (quality.quality_gate && !quality.quality_gate.passed) {
        qualityEl.textContent += " \u26A0";
        qualityEl.className += " quality-gate-failed";

        var reviewContainer = document.getElementById("review-actions");
        if (!reviewContainer) {
          reviewContainer = document.createElement("span");
          reviewContainer.id = "review-actions";
          reviewContainer.style.marginLeft = "12px";
          qualityEl.parentNode.appendChild(reviewContainer);
        }
        reviewContainer.innerHTML = "";
        var approveBtn = document.createElement("button");
        approveBtn.className = "btn btn-sm";
        approveBtn.style.cssText = "background:#28a745;color:#fff;margin-right:4px;padding:2px 8px;border:none;border-radius:3px;cursor:pointer";
        approveBtn.textContent = "Approve";
        approveBtn.onclick = function () { reviewJob("approve"); };
        var rejectBtn = document.createElement("button");
        rejectBtn.className = "btn btn-sm";
        rejectBtn.style.cssText = "background:#dc3545;color:#fff;padding:2px 8px;border:none;border-radius:3px;cursor:pointer";
        rejectBtn.textContent = "Reject";
        rejectBtn.onclick = function () { reviewJob("reject"); };
        reviewContainer.appendChild(approveBtn);
        reviewContainer.appendChild(rejectBtn);
      }
    } else {
      qualityEl.textContent = "N/A";
    }

    $("#stat-sheets").textContent = (data.sheets || []).length;
    $("#stat-items").textContent = items.length;
    $("#stat-confidence").textContent = conf != null ? (conf * 100).toFixed(0) + "%" : "N/A";
    $("#stat-tokens").textContent = (data.tokens_used || 0).toLocaleString();
    $("#stat-cost").textContent = "$" + (data.cost_usd || 0).toFixed(3);

    // Validation delta (post-Stage-5 re-validation improvement)
    var deltaEl = document.getElementById("stat-validation-delta");
    var delta = data.validation_delta;
    if (deltaEl && delta && delta.delta !== undefined && delta.delta !== 0) {
      var pct = (delta.delta * 100).toFixed(1);
      var prefix = delta.delta > 0 ? "+" : "";
      deltaEl.textContent = prefix + pct + "% after remapping";
      deltaEl.className = "badge " + (delta.delta > 0 ? "badge-high" : "badge-low");
      deltaEl.title = "Pre: " + (delta.pre_stage5_rate * 100).toFixed(1)
        + "% \u2192 Post: " + (delta.post_stage5_rate * 100).toFixed(1) + "%";
    } else if (deltaEl) {
      deltaEl.textContent = "";
    }

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

      const key = (item.sheet || "") + "|" + (item.original_label || "");
      const pending = pendingCorrections[key];
      const displayName = pending ? pending.new_canonical_name : (item.canonical_name || "");
      const correctedClass = pending ? " corrected" : "";

      tr.innerHTML =
        "<td>" + esc(item.sheet || "") + "</td>" +
        "<td>" + esc(item.original_label || "") + "</td>" +
        '<td class="canonical-cell' + correctedClass + '"><code>' + esc(displayName) + "</code></td>" +
        '<td><span class="badge ' + badgeClass + '">' + (conf * 100).toFixed(0) + "%</span></td>" +
        '<td class="values-cell">' + esc(valStr || "-") + "</td>";
      if (pending) tr.classList.add("row-corrected");
      tr.dataset.sheet = item.sheet || "";
      tr.dataset.label = item.original_label || "";
      tr.dataset.canonical = item.canonical_name || "";
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll(".canonical-cell").forEach(function (td) {
      td.addEventListener("click", function (e) {
        e.stopPropagation();
        openTaxonomyDropdown(td);
      });
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
        if (tab.dataset.tab === "corrections") loadCorrectionHistory();
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

  // --- Corrections ---
  function updatePendingBanner() {
    var banner = $("#pending-banner");
    var count = Object.keys(pendingCorrections).length;
    if (count > 0) {
      banner.classList.remove("hidden");
      $("#pending-count").textContent = count;
    } else {
      banner.classList.add("hidden");
    }
  }

  function closeDropdown() {
    if (activeDropdown) {
      activeDropdown.remove();
      activeDropdown = null;
    }
    document.removeEventListener("click", closeDropdownOutside);
  }

  function closeDropdownOutside(e) {
    if (activeDropdown && !activeDropdown.contains(e.target)) closeDropdown();
  }

  function openTaxonomyDropdown(td) {
    closeDropdown();
    var tr = td.closest("tr");
    var sheet = tr.dataset.sheet;
    var label = tr.dataset.label;
    var currentCanonical = tr.dataset.canonical;

    var dropdown = document.createElement("div");
    dropdown.className = "tax-dropdown";
    var input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Search taxonomy...";
    dropdown.appendChild(input);
    var list = document.createElement("div");
    dropdown.appendChild(list);

    td.appendChild(dropdown);
    activeDropdown = dropdown;
    input.focus();

    var timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        searchTaxonomy(input.value.trim(), list, sheet, label, currentCanonical);
      }, 250);
    });

    setTimeout(function () {
      document.addEventListener("click", closeDropdownOutside);
    }, 0);
  }

  async function searchTaxonomy(query, listEl, sheet, label, currentCanonical) {
    if (query.length < 1) { listEl.innerHTML = ""; return; }
    try {
      var res = await apiFetch("/api/v1/taxonomy/search?q=" + encodeURIComponent(query));
      var data = await res.json();
      listEl.innerHTML = "";
      (data.items || []).forEach(function (item) {
        var div = document.createElement("div");
        div.className = "tax-option";
        div.innerHTML = esc(item.canonical_name) + '<span class="tax-cat">' + esc(item.category || "") + "</span>";
        div.addEventListener("click", function (e) {
          e.stopPropagation();
          addPendingCorrection(sheet, label, currentCanonical, item.canonical_name);
          closeDropdown();
        });
        listEl.appendChild(div);
      });
      if (!data.items || data.items.length === 0) {
        listEl.innerHTML = '<div class="tax-option" style="color:#6b7280">No matches</div>';
      }
    } catch (err) {
      listEl.innerHTML = '<div class="tax-option" style="color:#dc2626">Search failed</div>';
    }
  }

  function addPendingCorrection(sheet, label, oldCanonical, newCanonical) {
    if (newCanonical === oldCanonical) return;
    var key = sheet + "|" + label;
    pendingCorrections[key] = {
      original_label: label,
      sheet: sheet || null,
      new_canonical_name: newCanonical,
    };
    updatePendingBanner();
    if (resultData) renderLineItems(resultData.line_items || []);
  }

  function discardCorrections() {
    pendingCorrections = {};
    updatePendingBanner();
    if (resultData) renderLineItems(resultData.line_items || []);
  }

  async function previewCorrections() {
    if (!currentJobId || !Object.keys(pendingCorrections).length) return;
    var corrections = Object.values(pendingCorrections).map(function (c) {
      return { original_label: c.original_label, new_canonical_name: c.new_canonical_name, sheet: c.sheet };
    });
    try {
      var res = await apiFetch("/api/v1/jobs/" + currentJobId + "/corrections/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrections: corrections }),
      });
      var data = await res.json();
      renderPreviewModal(data);
    } catch (err) {
      alert("Preview failed: " + err.message);
    }
  }

  function renderPreviewModal(data) {
    var body = $("#preview-body");
    var html = '<table class="diff-table"><thead><tr><th>Label</th><th>Sheet</th><th>Old</th><th>New</th></tr></thead><tbody>';
    (data.diffs || []).forEach(function (d) {
      html += "<tr><td>" + esc(d.original_label) + "</td><td>" + esc(d.sheet || "-") +
        '</td><td class="diff-old">' + esc(d.old_canonical_name) +
        '</td><td class="diff-new">' + esc(d.new_canonical_name) + "</td></tr>";
    });
    html += "</tbody></table>";
    body.innerHTML = html;

    var warningsEl = $("#preview-warnings");
    if (data.warnings && data.warnings.length) {
      warningsEl.innerHTML = '<p style="color:#dc2626;font-size:0.8rem">' + data.warnings.map(esc).join("<br>") + "</p>";
    } else {
      warningsEl.innerHTML = "";
    }
    show($("#preview-modal"));
  }

  async function applyCorrections() {
    if (!currentJobId) return;
    var corrections = Object.values(pendingCorrections).map(function (c) {
      return { original_label: c.original_label, new_canonical_name: c.new_canonical_name, sheet: c.sheet };
    });
    try {
      var res = await apiFetch("/api/v1/jobs/" + currentJobId + "/corrections/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrections: corrections }),
      });
      var data = await res.json();
      hide($("#preview-modal"));
      pendingCorrections = {};
      updatePendingBanner();
      await loadResults();
      alert(data.message);
    } catch (err) {
      alert("Apply failed: " + err.message);
    }
  }

  async function loadCorrectionHistory() {
    if (!currentJobId) return;
    var el = $("#corrections-content");
    try {
      var res = await apiFetch("/api/v1/jobs/" + currentJobId + "/corrections/history");
      var data = await res.json();
      if (!data.corrections || data.corrections.length === 0) {
        el.innerHTML = "<p>No corrections have been applied to this extraction.</p>";
        return;
      }
      var html = '<table><thead><tr><th>Label</th><th>Sheet</th><th>Old</th><th>New</th><th>Date</th><th></th></tr></thead><tbody>';
      data.corrections.forEach(function (c) {
        var cls = c.reverted ? ' class="reverted"' : "";
        html += "<tr" + cls + ">" +
          "<td>" + esc(c.original_label) + "</td>" +
          "<td>" + esc(c.sheet || "-") + "</td>" +
          "<td>" + esc(c.old_canonical_name) + "</td>" +
          "<td>" + esc(c.new_canonical_name) + "</td>" +
          "<td>" + esc(c.created_at ? new Date(c.created_at).toLocaleDateString() : "-") + "</td>" +
          "<td>" + (c.reverted ? "Reverted" : '<button class="btn-undo" data-cid="' + esc(c.id) + '">Undo</button>') + "</td>" +
          "</tr>";
      });
      html += "</tbody></table>";
      el.innerHTML = html;
      el.querySelectorAll(".btn-undo").forEach(function (btn) {
        btn.addEventListener("click", function () { undoCorrection(btn.dataset.cid); });
      });
    } catch (err) {
      el.innerHTML = '<p style="color:#dc2626">Failed to load history: ' + esc(err.message) + "</p>";
    }
  }

  async function undoCorrection(correctionId) {
    if (!confirm("Undo this correction? The original mapping will be restored.")) return;
    try {
      var res = await apiFetch("/api/v1/corrections/" + correctionId + "/undo", { method: "POST" });
      var data = await res.json();
      alert(data.message);
      await loadResults();
      loadCorrectionHistory();
    } catch (err) {
      alert("Undo failed: " + err.message);
    }
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

  $("#preview-btn").addEventListener("click", previewCorrections);
  $("#discard-btn").addEventListener("click", discardCorrections);
  $("#confirm-apply-btn").addEventListener("click", applyCorrections);
  $("#cancel-preview-btn").addEventListener("click", function () { hide($("#preview-modal")); });
})();
