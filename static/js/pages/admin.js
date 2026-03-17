// Admin / System Page — Health Dashboard, Dead Letter Queue, Learned Aliases
// Meridian Design System v1.0

import { apiGet, apiFetch } from '../api.js';
import { esc, timeAgo } from '../state.js';
import { renderTabs } from '../components/tabs.js';
import { skeletonStats, loadingPlaceholder, errorState } from '../components/loading.js';
import { emptyState } from '../components/empty-state.js';
import { showToast } from '../components/toast.js';
import { confirm } from '../components/modal.js';

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

let _refreshTimer = null;
let _autoRefreshEnabled = true;
let _container = null;
let _tabsApi = null;

// Track expanded DLQ rows by dlq_id
let _expandedDlqRows = new Set();

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function render(container) {
  _container = container;
  _expandedDlqRows = new Set();

  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1.25rem">
      <div>
        <p class="eyebrow">ADMINISTRATION</p>
        <h1 class="page-title">System</h1>
      </div>
    </div>
    <div id="admin-tabs"></div>
  `;

  const tabContainer = container.querySelector('#admin-tabs');

  _tabsApi = renderTabs(tabContainer, [
    { id: 'health',  label: 'Health',            render: renderHealthTab },
    { id: 'dlq',     label: 'Dead Letter Queue', render: renderDlqTab },
    { id: 'aliases', label: 'Learned Aliases',   render: renderAliasesTab },
  ]);
}

export function destroy() {
  _stopAutoRefresh();
  _container = null;
  _tabsApi = null;
  _expandedDlqRows = new Set();
}

// ---------------------------------------------------------------------------
// TAB 1 — Health Dashboard
// ---------------------------------------------------------------------------

async function renderHealthTab(panel) {
  panel.innerHTML = loadingPlaceholder('Loading health data...');
  _autoRefreshEnabled = true;
  await _loadHealth(panel);
  _startAutoRefresh(panel);
}

function _startAutoRefresh(panel) {
  _stopAutoRefresh();
  if (_autoRefreshEnabled) {
    _refreshTimer = setInterval(() => {
      if (_autoRefreshEnabled) _loadHealth(panel);
    }, 30000);
  }
}

function _stopAutoRefresh() {
  if (_refreshTimer) {
    clearInterval(_refreshTimer);
    _refreshTimer = null;
  }
}

async function _loadHealth(panel) {
  let dbData = null;
  let cbData = null;
  let staleData = null;
  let dbError = null;
  let cbError = null;
  let staleError = null;

  // Fetch all three health endpoints in parallel
  const [dbRes, cbRes, staleRes] = await Promise.allSettled([
    apiFetch('/health/database').then(r => r.json()),
    apiFetch('/health/circuit-breaker').then(r => r.json()),
    apiFetch('/health/stale-jobs').then(r => r.json()),
  ]);

  if (dbRes.status === 'fulfilled') dbData = dbRes.value; else dbError = dbRes.reason;
  if (cbRes.status === 'fulfilled') cbData = cbRes.value; else cbError = cbRes.reason;
  if (staleRes.status === 'fulfilled') staleData = staleRes.value; else staleError = staleRes.reason;

  // Determine overall status
  const overallStatus = _deriveOverallStatus(dbData, cbData, staleData);

  let html = '';

  // --- Overall status + refresh controls ---
  html += `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px">`;
  html += `<div style="display:flex;align-items:center;gap:10px">`;
  html += _statusDot(overallStatus);
  html += `<span style="font-size:15px;font-weight:500;color:${_statusTextColor(overallStatus)}">${_statusLabel(overallStatus)}</span>`;
  html += `</div>`;
  html += `<div style="display:flex;align-items:center;gap:12px">`;
  html += `<span style="font-size:11px;color:var(--color-text-secondary)">Last checked: ${dbData?.timestamp ? timeAgo(dbData.timestamp) : 'N/A'}</span>`;
  html += `<button id="health-refresh-btn" class="btn btn-ghost btn-sm" style="font-size:11px">Refresh</button>`;
  html += `<span id="health-auto-label" style="font-size:10.5px;color:var(--color-text-tertiary)">Auto-refresh: ${_autoRefreshEnabled ? 'ON' : 'OFF'}</span>`;
  html += `<button id="health-auto-toggle" class="btn btn-ghost btn-sm" style="font-size:10.5px">${_autoRefreshEnabled ? 'Pause' : 'Resume'}</button>`;
  html += `</div>`;
  html += `</div>`;

  // --- Stat cards ---
  if (dbData) {
    const queryMs = dbData.query_time_ms;
    const queryColor = queryMs < 100 ? '#1A7A4A' : queryMs < 500 ? '#C47D00' : '#A32626';

    const pool = dbData.pool || {};
    const totalConn = pool.total_connections || pool.size || 1;
    const checkedOut = pool.checked_out || 0;
    const utilPct = totalConn > 0 ? Math.round((checkedOut / totalConn) * 100) : 0;

    const cb = dbData.circuit_breaker || cbData || {};
    const successRate = cb.success_rate != null ? (cb.success_rate * 100).toFixed(1) : 'N/A';

    html += `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:16px">`;

    // Query Time
    html += _statCard('Query Time',
      `<span style="font-family:'DM Serif Display',serif;font-size:1.5rem;color:${queryColor}">${queryMs != null ? queryMs.toFixed(1) : '-'}</span>` +
      `<span style="font-size:12px;color:var(--color-text-secondary);margin-left:2px">ms</span>`);

    // Pool Utilization
    html += _statCard('Pool Utilization',
      `<span style="font-family:'DM Serif Display',serif;font-size:1.5rem;color:var(--color-text-primary)">${utilPct}</span>` +
      `<span style="font-size:12px;color:var(--color-text-secondary);margin-left:2px">%</span>` +
      `<span style="font-size:11px;color:var(--color-text-tertiary);margin-left:6px">${checkedOut}/${totalConn}</span>`);

    // Success Rate
    html += _statCard('Success Rate',
      `<span style="font-family:'DM Serif Display',serif;font-size:1.5rem;color:var(--color-text-primary)">${successRate}</span>` +
      `<span style="font-size:12px;color:var(--color-text-secondary);margin-left:2px">%</span>`);

    html += `</div>`;
  } else if (dbError) {
    html += `<div style="padding:12px 14px;background:#FDEAEA;border-radius:8px;margin-bottom:16px;font-size:12px;color:#8A1F1F">Failed to load database health: ${esc(dbError.message || String(dbError))}</div>`;
  }

  // --- Connection Pool card ---
  if (dbData?.pool) {
    const pool = dbData.pool;
    const totalConn = pool.total_connections || pool.size || 0;
    const utilPct = totalConn > 0 ? Math.round(((pool.checked_out || 0) / totalConn) * 100) : 0;

    html += `<div class="card" style="margin-bottom:12px">`;
    html += `<div style="padding:11px 14px;border-bottom:0.5px solid rgba(0,0,0,0.08)"><span style="font-size:13px;font-weight:500">Connection Pool</span></div>`;
    html += `<div class="table-wrapper" style="border:none;border-radius:0">`;
    html += `<table class="data-table"><thead><tr><th style="text-align:left">Property</th><th style="text-align:left">Value</th></tr></thead><tbody>`;
    html += _propRow('Pool Size', pool.size);
    html += _propRow('Checked Out', pool.checked_out);
    html += _propRow('Overflow', pool.overflow);
    html += _propRow('Total Connections', pool.total_connections);
    html += _propRow('Utilization', utilPct + '%');
    html += `</tbody></table></div></div>`;
  }

  // --- Circuit Breaker card ---
  const cbInfo = cbData || dbData?.circuit_breaker;
  if (cbInfo) {
    const cbState = (cbInfo.state || 'unknown').toLowerCase();
    const cbBadge = _cbStateBadge(cbState);

    html += `<div class="card" style="margin-bottom:12px">`;
    html += `<div style="padding:11px 14px;border-bottom:0.5px solid rgba(0,0,0,0.08);display:flex;align-items:center;gap:10px">`;
    html += `<span style="font-size:13px;font-weight:500">Circuit Breaker</span>`;
    html += cbBadge;
    html += `</div>`;
    html += `<div class="table-wrapper" style="border:none;border-radius:0">`;
    html += `<table class="data-table"><thead><tr><th style="text-align:left">Metric</th><th style="text-align:left">Value</th></tr></thead><tbody>`;
    html += _propRow('Total Requests', cbInfo.total_requests);
    html += _propRow('Failed Requests', cbInfo.failed_requests);
    html += _propRow('Rejected Requests', cbInfo.rejected_requests);
    html += _propRow('Success Rate', cbInfo.success_rate != null ? (cbInfo.success_rate * 100).toFixed(1) + '%' : '-');
    html += _propRow('Consecutive Failures', cbInfo.consecutive_failures);
    html += _propRow('Last State Change', cbInfo.last_state_change ? timeAgo(cbInfo.last_state_change) : '-');
    html += `</tbody></table></div></div>`;
  } else if (cbError) {
    html += `<div style="padding:12px 14px;background:#FDEAEA;border-radius:8px;margin-bottom:12px;font-size:12px;color:#8A1F1F">Failed to load circuit breaker: ${esc(cbError.message || String(cbError))}</div>`;
  }

  // --- Stale Jobs card ---
  if (staleData) {
    const staleCount = (staleData.stale_pending_count || 0) + (staleData.stale_processing_count || 0);
    const staleStatus = staleData.status || 'ok';
    const isOk = staleStatus === 'ok' && staleCount === 0;

    html += `<div class="card" style="margin-bottom:12px">`;
    html += `<div style="padding:11px 14px;border-bottom:0.5px solid rgba(0,0,0,0.08)"><span style="font-size:13px;font-weight:500">Stale Jobs</span></div>`;
    html += `<div style="padding:14px">`;

    if (isOk) {
      html += `<div style="display:flex;align-items:center;gap:8px">`;
      html += `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#4CAF7D"></span>`;
      html += `<span style="font-size:13px;color:#1A7A4A">No stale jobs</span>`;
      html += `</div>`;
    } else {
      html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">`;
      html += `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${staleCount > 5 ? '#A32626' : '#C47D00'}"></span>`;
      html += `<span style="font-size:13px;color:${staleCount > 5 ? '#A32626' : '#C47D00'};font-weight:500">${staleCount} stale job${staleCount !== 1 ? 's' : ''} detected</span>`;
      html += `</div>`;

      if (staleData.stale_pending && staleData.stale_pending.length > 0) {
        html += `<div style="margin-bottom:8px"><span style="font-size:11px;font-weight:500;color:var(--color-text-secondary)">Stale Pending</span></div>`;
        html += `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">`;
        for (const jobId of staleData.stale_pending) {
          html += `<a href="#/extractions/${esc(jobId)}" style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#1D6B9F;text-decoration:none;background:#E3EEF8;padding:2px 8px;border-radius:4px">${esc(jobId.substring(0, 8))}</a>`;
        }
        html += `</div>`;
      }

      if (staleData.stale_processing && staleData.stale_processing.length > 0) {
        html += `<div style="margin-bottom:8px"><span style="font-size:11px;font-weight:500;color:var(--color-text-secondary)">Stale Processing</span></div>`;
        html += `<div style="display:flex;flex-wrap:wrap;gap:6px">`;
        for (const jobId of staleData.stale_processing) {
          html += `<a href="#/extractions/${esc(jobId)}" style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#1D6B9F;text-decoration:none;background:#E3EEF8;padding:2px 8px;border-radius:4px">${esc(jobId.substring(0, 8))}</a>`;
        }
        html += `</div>`;
      }
    }

    html += `</div></div>`;
  } else if (staleError) {
    html += `<div style="padding:12px 14px;background:#FDEAEA;border-radius:8px;margin-bottom:12px;font-size:12px;color:#8A1F1F">Failed to load stale jobs: ${esc(staleError.message || String(staleError))}</div>`;
  }

  // --- Warnings ---
  const warnings = dbData?.warnings;
  if (warnings && warnings.length > 0) {
    html += `<div style="padding:12px 14px;background:#FEF3CD;border-radius:8px;margin-bottom:12px">`;
    html += `<div style="font-size:11px;font-weight:500;color:#7A5000;margin-bottom:6px">Warnings</div>`;
    for (const w of warnings) {
      html += `<div style="font-size:12px;color:#7A5000;line-height:1.5">${esc(w)}</div>`;
    }
    html += `</div>`;
  }

  // --- PostgreSQL version ---
  if (dbData?.postgresql_version) {
    html += `<div style="font-size:11px;color:var(--color-text-tertiary);margin-top:4px">PostgreSQL ${esc(dbData.postgresql_version)}</div>`;
  }

  panel.innerHTML = html;

  // Bind refresh button
  const refreshBtn = panel.querySelector('#health-refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => _loadHealth(panel));
  }

  // Bind auto-refresh toggle
  const autoToggle = panel.querySelector('#health-auto-toggle');
  if (autoToggle) {
    autoToggle.addEventListener('click', () => {
      _autoRefreshEnabled = !_autoRefreshEnabled;
      if (_autoRefreshEnabled) {
        _startAutoRefresh(panel);
      } else {
        _stopAutoRefresh();
      }
      const label = panel.querySelector('#health-auto-label');
      if (label) label.textContent = `Auto-refresh: ${_autoRefreshEnabled ? 'ON' : 'OFF'}`;
      autoToggle.textContent = _autoRefreshEnabled ? 'Pause' : 'Resume';
    });
  }
}

function _deriveOverallStatus(dbData, cbData, staleData) {
  if (!dbData) return 'unhealthy';
  if (dbData.status === 'unhealthy') return 'unhealthy';
  if (dbData.status === 'degraded') return 'degraded';

  const cbState = (cbData?.state || dbData?.circuit_breaker?.state || '').toLowerCase();
  if (cbState === 'open') return 'unhealthy';
  if (cbState === 'half_open') return 'degraded';

  const staleStatus = staleData?.status;
  if (staleStatus === 'warning') return 'degraded';

  return 'healthy';
}

function _statusDot(status) {
  const colors = { healthy: '#4CAF7D', degraded: '#C47D00', unhealthy: '#A32626' };
  const c = colors[status] || '#A32626';
  return `<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:${c};flex-shrink:0"></span>`;
}

function _statusTextColor(status) {
  const colors = { healthy: '#1A7A4A', degraded: '#C47D00', unhealthy: '#A32626' };
  return colors[status] || '#A32626';
}

function _statusLabel(status) {
  const labels = { healthy: 'Healthy', degraded: 'Degraded', unhealthy: 'Unhealthy' };
  return labels[status] || 'Unknown';
}

function _statCard(label, valueHtml) {
  return `<div style="background:var(--color-background-secondary);border-radius:8px;padding:11px 14px">` +
    `<div style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary);margin-bottom:4px">${esc(label)}</div>` +
    `<div>${valueHtml}</div>` +
    `</div>`;
}

function _propRow(label, value) {
  const display = value != null ? String(value) : '-';
  return `<tr><td style="font-size:12px">${esc(label)}</td><td style="font-family:'IBM Plex Mono',monospace;font-size:12px">${esc(display)}</td></tr>`;
}

function _cbStateBadge(state) {
  if (state === 'closed') {
    return `<span class="badge" style="background:#E6F4ED;color:#15652E;font-size:10.5px;font-weight:500;text-transform:uppercase;letter-spacing:0.5px">CLOSED</span>`;
  }
  if (state === 'half_open') {
    return `<span class="badge" style="background:#FEF3CD;color:#7A5000;font-size:10.5px;font-weight:500;text-transform:uppercase;letter-spacing:0.5px">HALF OPEN</span>`;
  }
  if (state === 'open') {
    return `<span class="badge" style="background:#FDEAEA;color:#8A1F1F;font-size:10.5px;font-weight:500;text-transform:uppercase;letter-spacing:0.5px">OPEN</span>`;
  }
  return `<span class="badge b-gray" style="font-size:10.5px;font-weight:500;text-transform:uppercase">${esc(state.toUpperCase())}</span>`;
}

// ---------------------------------------------------------------------------
// TAB 2 — Dead Letter Queue
// ---------------------------------------------------------------------------

let _dlqOnlyUnreplayed = false;

async function renderDlqTab(panel) {
  _dlqOnlyUnreplayed = false;
  _expandedDlqRows = new Set();
  panel.innerHTML = loadingPlaceholder('Loading dead letter queue...');
  await _loadDlq(panel);
}

async function _loadDlq(panel) {
  try {
    const data = await apiGet(`/api/v1/admin/dlq/?limit=50&offset=0&only_unreplayed=${_dlqOnlyUnreplayed}`);
    const entries = data.entries || [];
    const count = data.count || entries.length;

    let html = '';

    // Header
    html += `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">`;
    html += `<div>`;
    html += `<span style="font-size:15px;font-weight:500">Dead Letter Queue</span>`;
    html += `<span style="font-size:12px;color:var(--color-text-secondary);margin-left:8px">${count} entr${count === 1 ? 'y' : 'ies'}</span>`;
    html += `</div>`;
    html += `<label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--color-text-secondary);cursor:pointer">`;
    html += `<input type="checkbox" id="dlq-unreplayed-filter" ${_dlqOnlyUnreplayed ? 'checked' : ''} style="accent-color:#1D6B9F">`;
    html += `Show only unreplayed`;
    html += `</label>`;
    html += `</div>`;

    if (entries.length === 0) {
      html += emptyState({ icon: '\u2713', title: 'Queue empty', description: 'No failed tasks in the dead letter queue.' });
    } else {
      html += `<div class="card" style="padding:0;overflow:hidden">`;
      html += `<div class="table-wrapper" style="border:none;border-radius:0">`;
      html += `<table class="data-table"><thead><tr>`;
      html += `<th style="text-align:left">Task Name</th>`;
      html += `<th style="text-align:left">Error</th>`;
      html += `<th style="text-align:left">Status</th>`;
      html += `<th style="text-align:left">Created</th>`;
      html += `<th style="text-align:left">Actions</th>`;
      html += `</tr></thead><tbody>`;

      for (const entry of entries) {
        const isReplayed = !!entry.replayed;
        const errorTruncated = _truncate(entry.error || '', 80);
        const isExpanded = _expandedDlqRows.has(entry.dlq_id);

        // Main data row
        html += `<tr class="clickable dlq-row" data-dlq-id="${esc(entry.dlq_id)}" style="cursor:pointer">`;
        html += `<td style="font-family:'IBM Plex Mono',monospace;font-size:12px">${esc(entry.task_name || '-')}</td>`;
        html += `<td style="font-size:12px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(entry.error || '')}">${esc(errorTruncated)}</td>`;
        html += `<td>${isReplayed
          ? '<span class="badge" style="background:#E6F4ED;color:#15652E;font-size:10.5px">Replayed</span>'
          : '<span class="badge" style="background:#FEF3CD;color:#7A5000;font-size:10.5px">Pending</span>'}</td>`;
        html += `<td style="font-size:12px;color:var(--color-text-secondary)">${timeAgo(entry.created_at)}</td>`;
        html += `<td>`;
        html += `<div style="display:flex;gap:6px" onclick="event.stopPropagation()">`;
        if (!isReplayed) {
          html += `<button class="btn btn-sm dlq-replay-btn" data-dlq-id="${esc(entry.dlq_id)}" style="font-size:11px;background:#1D6B9F;color:white;border:none;padding:3px 10px;border-radius:6px;cursor:pointer">Replay</button>`;
        }
        html += `<button class="btn btn-sm btn-ghost dlq-delete-btn" data-dlq-id="${esc(entry.dlq_id)}" style="font-size:11px;color:#A32626;padding:3px 10px;border-radius:6px;cursor:pointer">Delete</button>`;
        html += `</div>`;
        html += `</td>`;
        html += `</tr>`;

        // Expandable detail row
        html += `<tr class="dlq-detail-row" data-dlq-detail="${esc(entry.dlq_id)}" style="display:${isExpanded ? 'table-row' : 'none'}">`;
        html += `<td colspan="5" style="padding:0">`;
        html += `<div id="dlq-detail-${esc(entry.dlq_id)}" style="padding:12px 16px;background:var(--color-background-secondary);border-top:0.5px solid rgba(0,0,0,0.08)">`;
        if (isExpanded) {
          html += `<div style="text-align:center;padding:8px"><span class="spinner"></span></div>`;
        }
        html += `</div>`;
        html += `</td></tr>`;
      }

      html += `</tbody></table></div></div>`;
    }

    panel.innerHTML = html;

    // Bind filter toggle
    const filterCheckbox = panel.querySelector('#dlq-unreplayed-filter');
    if (filterCheckbox) {
      filterCheckbox.addEventListener('change', () => {
        _dlqOnlyUnreplayed = filterCheckbox.checked;
        _expandedDlqRows = new Set();
        _loadDlq(panel);
      });
    }

    // Bind row expand/collapse
    panel.querySelectorAll('.dlq-row').forEach(row => {
      row.addEventListener('click', (e) => {
        // Don't toggle if clicking action buttons
        if (e.target.closest('.dlq-replay-btn') || e.target.closest('.dlq-delete-btn')) return;
        const dlqId = row.dataset.dlqId;
        _toggleDlqDetail(panel, dlqId);
      });
    });

    // Bind replay buttons
    panel.querySelectorAll('.dlq-replay-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const dlqId = btn.dataset.dlqId;
        await _replayDlqEntry(panel, dlqId);
      });
    });

    // Bind delete buttons
    panel.querySelectorAll('.dlq-delete-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const dlqId = btn.dataset.dlqId;
        await _deleteDlqEntry(panel, dlqId);
      });
    });

    // Load details for any already-expanded rows
    for (const dlqId of _expandedDlqRows) {
      _fetchDlqDetail(dlqId);
    }
  } catch (err) {
    panel.innerHTML = errorState('Failed to load DLQ: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => _loadDlq(panel));
  }
}

async function _toggleDlqDetail(panel, dlqId) {
  const detailRow = panel.querySelector(`tr[data-dlq-detail="${dlqId}"]`);
  if (!detailRow) return;

  if (_expandedDlqRows.has(dlqId)) {
    _expandedDlqRows.delete(dlqId);
    detailRow.style.display = 'none';
  } else {
    _expandedDlqRows.add(dlqId);
    detailRow.style.display = 'table-row';
    _fetchDlqDetail(dlqId);
  }
}

async function _fetchDlqDetail(dlqId) {
  const container = document.getElementById(`dlq-detail-${dlqId}`);
  if (!container) return;

  container.innerHTML = `<div style="text-align:center;padding:8px"><span class="spinner"></span></div>`;

  try {
    const detail = await apiGet(`/api/v1/admin/dlq/${dlqId}`);

    let html = '';

    if (detail.task_id) {
      html += `<div style="margin-bottom:8px"><span style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary)">Task ID</span>`;
      html += `<div style="font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--color-text-primary)">${esc(detail.task_id)}</div></div>`;
    }

    if (detail.replayed && detail.replayed_at) {
      html += `<div style="margin-bottom:8px"><span style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary)">Replayed At</span>`;
      html += `<div style="font-size:11.5px;color:var(--color-text-primary)">${timeAgo(detail.replayed_at)}</div></div>`;
    }

    if (detail.task_args) {
      html += `<div style="margin-bottom:8px"><span style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary)">Task Args</span>`;
      html += `<pre style="font-family:'IBM Plex Mono',monospace;font-size:11px;background:var(--color-background-primary);border:0.5px solid rgba(0,0,0,0.08);border-radius:6px;padding:8px 10px;margin:4px 0 0;overflow-x:auto;white-space:pre-wrap;word-break:break-all">${esc(typeof detail.task_args === 'string' ? detail.task_args : JSON.stringify(detail.task_args, null, 2))}</pre></div>`;
    }

    if (detail.task_kwargs) {
      html += `<div style="margin-bottom:8px"><span style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary)">Task Kwargs</span>`;
      html += `<pre style="font-family:'IBM Plex Mono',monospace;font-size:11px;background:var(--color-background-primary);border:0.5px solid rgba(0,0,0,0.08);border-radius:6px;padding:8px 10px;margin:4px 0 0;overflow-x:auto;white-space:pre-wrap;word-break:break-all">${esc(typeof detail.task_kwargs === 'string' ? detail.task_kwargs : JSON.stringify(detail.task_kwargs, null, 2))}</pre></div>`;
    }

    // Full error
    if (detail.error) {
      html += `<div style="margin-bottom:8px"><span style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary)">Error</span>`;
      html += `<pre style="font-family:'IBM Plex Mono',monospace;font-size:11px;background:#FDEAEA;border:0.5px solid rgba(163,38,38,0.15);border-radius:6px;padding:8px 10px;margin:4px 0 0;overflow-x:auto;white-space:pre-wrap;word-break:break-all;color:#8A1F1F">${esc(detail.error)}</pre></div>`;
    }

    // Traceback
    if (detail.traceback) {
      html += `<div><span style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary)">Traceback</span>`;
      html += `<pre style="font-family:'IBM Plex Mono',monospace;font-size:11px;background:var(--color-background-primary);border:0.5px solid rgba(0,0,0,0.08);border-radius:6px;padding:8px 10px;margin:4px 0 0;overflow-x:auto;white-space:pre-wrap;word-break:break-all;max-height:300px;overflow-y:auto">${esc(detail.traceback)}</pre></div>`;
    }

    container.innerHTML = html || '<div style="font-size:12px;color:var(--color-text-secondary)">No additional detail available.</div>';
  } catch (err) {
    container.innerHTML = `<div style="font-size:12px;color:#A32626">Failed to load details: ${esc(err.message)}</div>`;
  }
}

async function _replayDlqEntry(panel, dlqId) {
  const ok = await confirm(
    'Replay Task',
    `<p style="font-size:13px">Are you sure you want to replay this failed task?</p><p style="font-size:11px;color:var(--color-text-secondary);margin-top:4px">DLQ ID: <code>${esc(dlqId)}</code></p>`,
    { confirmText: 'Replay', confirmClass: 'btn' }
  );
  if (!ok) return;

  try {
    const res = await apiFetch(`/api/v1/admin/dlq/${dlqId}/replay`, { method: 'POST' });
    const result = await res.json();
    showToast('Task replayed', 'success', 4000, `New task ID: ${result.new_task_id || 'N/A'}`);
    _expandedDlqRows = new Set();
    await _loadDlq(panel);
  } catch (err) {
    showToast('Replay failed', 'error', 5000, err.message);
  }
}

async function _deleteDlqEntry(panel, dlqId) {
  const ok = await confirm(
    'Delete DLQ Entry',
    `<p style="font-size:13px">Permanently delete this dead letter queue entry?</p><p style="font-size:11px;color:var(--color-text-secondary);margin-top:4px">DLQ ID: <code>${esc(dlqId)}</code></p>`,
    { confirmText: 'Delete', confirmClass: 'btn', }
  );
  if (!ok) return;

  try {
    await apiFetch(`/api/v1/admin/dlq/${dlqId}`, { method: 'DELETE' });
    showToast('Entry deleted', 'success');
    _expandedDlqRows.delete(dlqId);
    await _loadDlq(panel);
  } catch (err) {
    showToast('Delete failed', 'error', 5000, err.message);
  }
}

function _truncate(str, maxLen) {
  if (!str || str.length <= maxLen) return str;
  return str.substring(0, maxLen) + '...';
}

// ---------------------------------------------------------------------------
// TAB 3 — Learned Aliases
// ---------------------------------------------------------------------------

let _aliasMinOccurrences = 1;

async function renderAliasesTab(panel) {
  _aliasMinOccurrences = 1;
  panel.innerHTML = loadingPlaceholder('Loading learned aliases...');
  await _loadAliases(panel);
}

async function _loadAliases(panel) {
  try {
    const data = await apiGet(`/api/v1/learned-aliases?min_occurrences=${_aliasMinOccurrences}&limit=100`);
    const aliases = data.aliases || [];
    const total = data.total || aliases.length;

    let html = '';

    // Header
    html += `<div style="margin-bottom:12px">`;
    html += `<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">`;
    html += `<div>`;
    html += `<span style="font-size:15px;font-weight:500">Learned Aliases</span>`;
    html += `<span style="font-size:12px;color:var(--color-text-secondary);margin-left:8px">${total} total</span>`;
    html += `</div>`;
    html += `<div style="display:flex;align-items:center;gap:8px">`;
    html += `<label style="font-size:11px;color:var(--color-text-secondary)">Min occurrences</label>`;
    html += `<input type="number" id="alias-min-occ" value="${_aliasMinOccurrences}" min="1" max="1000" style="width:56px;padding:4px 6px;border:0.5px solid var(--color-border-secondary);border-radius:6px;font-size:12px;font-family:'IBM Plex Mono',monospace;text-align:center">`;
    html += `</div>`;
    html += `</div>`;
    html += `<p style="font-size:12px;color:var(--color-text-secondary);margin-top:4px">Patterns discovered across extractions, pending promotion to the canonical taxonomy</p>`;
    html += `</div>`;

    if (aliases.length === 0) {
      html += emptyState({ title: 'No aliases', description: 'Aliases are discovered during extraction when similar labels are mapped to the same canonical name.' });
    } else {
      html += `<div class="card" style="padding:0;overflow:hidden">`;
      html += `<div class="table-wrapper" style="border:none;border-radius:0">`;
      html += `<table class="data-table"><thead><tr>`;
      html += `<th style="text-align:left">Alias Text</th>`;
      html += `<th style="text-align:left">Canonical Name</th>`;
      html += `<th style="text-align:right">Occurrences</th>`;
      html += `<th style="text-align:left">Source Entities</th>`;
      html += `<th style="text-align:left">Status</th>`;
      html += `<th style="text-align:left">Actions</th>`;
      html += `</tr></thead><tbody>`;

      for (const alias of aliases) {
        const isPromoted = !!alias.promoted;
        const sources = _formatSourceEntities(alias.source_entities);

        html += `<tr data-alias-id="${alias.id}">`;
        html += `<td style="font-size:12px;font-weight:500">${esc(alias.alias_text)}</td>`;
        html += `<td style="font-family:'IBM Plex Mono',monospace;font-size:12px">${esc(alias.canonical_name)}</td>`;
        html += `<td style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:12px">${alias.occurrence_count != null ? alias.occurrence_count : '-'}</td>`;
        html += `<td style="font-size:11px;color:var(--color-text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(sources)}">${esc(sources)}</td>`;
        html += `<td>${isPromoted
          ? '<span class="badge" style="background:#E6F4ED;color:#15652E;font-size:10.5px">Promoted</span>'
          : '<span class="badge" style="background:#FEF3CD;color:#7A5000;font-size:10.5px">Pending</span>'}</td>`;
        html += `<td>`;
        if (!isPromoted) {
          html += `<button class="btn btn-sm alias-promote-btn" data-alias-id="${alias.id}" style="font-size:11px;background:#1D6B9F;color:white;border:none;padding:3px 10px;border-radius:6px;cursor:pointer">Promote</button>`;
        } else {
          html += `<button class="btn btn-sm" disabled style="font-size:11px;padding:3px 10px;border-radius:6px;opacity:0.4;cursor:default">Promoted</button>`;
        }
        html += `</td>`;
        html += `</tr>`;
      }

      html += `</tbody></table></div></div>`;
    }

    panel.innerHTML = html;

    // Bind min occurrences filter
    const minOccInput = panel.querySelector('#alias-min-occ');
    if (minOccInput) {
      let debounceTimer = null;
      minOccInput.addEventListener('input', () => {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          const val = parseInt(minOccInput.value, 10);
          if (!isNaN(val) && val >= 1) {
            _aliasMinOccurrences = val;
            _loadAliases(panel);
          }
        }, 500);
      });
    }

    // Bind promote buttons
    panel.querySelectorAll('.alias-promote-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const aliasId = btn.dataset.aliasId;
        await _promoteAlias(panel, aliasId, btn);
      });
    });
  } catch (err) {
    panel.innerHTML = errorState('Failed to load aliases: ' + err.message, 'Retry');
    panel.querySelector('.error-retry-btn')?.addEventListener('click', () => _loadAliases(panel));
  }
}

async function _promoteAlias(panel, aliasId, btn) {
  try {
    btn.disabled = true;
    btn.textContent = 'Promoting...';

    const res = await apiFetch(`/api/v1/learned-aliases/${aliasId}/promote`, { method: 'POST' });
    const result = await res.json();

    showToast('Alias promoted', 'success', 4000, result.message || `${result.alias_text} promoted to taxonomy`);

    // Update the row in-place
    const row = panel.querySelector(`tr[data-alias-id="${aliasId}"]`);
    if (row) {
      const statusCell = row.querySelector('td:nth-child(5)');
      if (statusCell) {
        statusCell.innerHTML = '<span class="badge" style="background:#E6F4ED;color:#15652E;font-size:10.5px">Promoted</span>';
      }
      const actionCell = row.querySelector('td:nth-child(6)');
      if (actionCell) {
        actionCell.innerHTML = '<button class="btn btn-sm" disabled style="font-size:11px;padding:3px 10px;border-radius:6px;opacity:0.4;cursor:default">Promoted</button>';
      }
    }
  } catch (err) {
    showToast('Promote failed', 'error', 5000, err.message);
    btn.disabled = false;
    btn.textContent = 'Promote';
  }
}

function _formatSourceEntities(sources) {
  if (!sources) return '-';
  if (Array.isArray(sources)) return sources.join(', ');
  if (typeof sources === 'string') {
    try {
      const parsed = JSON.parse(sources);
      if (Array.isArray(parsed)) return parsed.join(', ');
    } catch { /* not JSON */ }
    return sources;
  }
  return String(sources);
}
