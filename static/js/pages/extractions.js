// Extractions Page — Job list + upload zone + status filters
import { apiGet, apiFetch } from '../api.js';
import { esc, timeAgo } from '../state.js';
import { navigate } from '../router.js';
import { renderUploadZone } from '../components/upload.js';
import { renderPagination } from '../components/pagination.js';
import { statusBadge, qualityBadge } from '../components/badge.js';
import { skeletonTable } from '../components/loading.js';
import { emptyState } from '../components/empty-state.js';
import { showToast } from '../components/toast.js';

let pollTimers = {};
let currentOffset = 0;

export async function render(container) {
  container.innerHTML = `
    <div class="content-header">
      <h2>Extractions</h2>
    </div>
    <div class="content-body">
      <div class="card" style="margin-bottom:var(--space-4)">
        <div id="ext-upload"></div>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title">All Extractions</span>
        </div>
        <div class="filter-bar">
          <select class="form-input" id="ext-status-filter" style="width:auto;min-width:140px">
            <option value="">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="processing">Processing</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
            <option value="needs_review">Needs Review</option>
          </select>
        </div>
        <div id="ext-table">${skeletonTable(8, 6)}</div>
        <div id="ext-pagination"></div>
      </div>
    </div>
  `;

  // Upload zone
  renderUploadZone(document.getElementById('ext-upload'), {
    compact: true,
    onUploadComplete(data) {
      if (data.job_id) {
        navigate('/extractions/' + data.job_id);
      }
    },
  });

  // Filter handler
  document.getElementById('ext-status-filter').addEventListener('change', () => loadJobs(0));

  // Initial load
  loadJobs(0);
}

const LIMIT = 20;

async function loadJobs(offset) {
  currentOffset = offset;
  const el = document.getElementById('ext-table');
  const paginationEl = document.getElementById('ext-pagination');
  const statusFilter = document.getElementById('ext-status-filter')?.value || '';

  try {
    let url = `/api/v1/jobs/?limit=${LIMIT}&offset=${offset}`;
    if (statusFilter) url += `&status=${statusFilter}`;

    const data = await apiGet(url);
    const jobs = data.jobs || [];
    const total = data.total || jobs.length;

    if (jobs.length === 0 && offset === 0) {
      el.innerHTML = emptyState({
        icon: '\uD83D\uDCC4',
        title: 'No extractions yet',
        description: 'Upload an Excel financial model to start extracting structured data.',
      });
      paginationEl.innerHTML = '';
      return;
    }

    let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th>File</th><th>Entity</th><th>Status</th><th>Quality</th><th>Cost</th><th>Date</th><th class="col-actions"></th>';
    html += '</tr></thead><tbody>';

    for (const job of jobs) {
      const filename = esc(job.filename || 'Unknown');
      const entity = esc(job.entity_name || '-');
      const cost = job.cost_usd != null ? '$' + job.cost_usd.toFixed(3) : '-';
      const processing = job.status === 'processing';

      html += `<tr class="clickable" data-job-id="${esc(job.job_id)}">`;
      html += `<td><strong>${filename}</strong></td>`;
      html += `<td class="text-secondary">${entity}</td>`;
      html += `<td>${statusBadge(job.status)}${processing ? progressIndicator(job) : ''}</td>`;
      html += `<td>${job.quality ? qualityBadge(job.quality) : '-'}</td>`;
      html += `<td class="col-number">${cost}</td>`;
      html += `<td class="text-sm text-secondary">${timeAgo(job.created_at)}</td>`;
      html += `<td class="col-actions">${job.status === 'failed' ? '<button class="btn btn-sm btn-ghost retry-btn" data-job-id="' + esc(job.job_id) + '">Retry</button>' : ''}</td>`;
      html += '</tr>';

      // Poll processing jobs
      if (processing) {
        startPollJob(job.job_id);
      }
    }

    html += '</tbody></table></div>';
    el.innerHTML = html;

    // Row click → job detail
    el.querySelectorAll('tr.clickable').forEach(tr => {
      tr.addEventListener('click', (e) => {
        if (e.target.classList.contains('retry-btn')) return;
        navigate('/extractions/' + tr.dataset.jobId);
      });
    });

    // Retry buttons
    el.querySelectorAll('.retry-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          const res = await apiFetch('/api/v1/jobs/' + btn.dataset.jobId + '/retry', { method: 'POST' });
          const data = await res.json();
          showToast('Retry started', 'success');
          navigate('/extractions/' + data.new_job_id);
        } catch (err) {
          showToast('Retry failed: ' + err.message, 'error');
        }
      });
    });

    // Pagination
    renderPagination(paginationEl, {
      total,
      limit: LIMIT,
      offset,
      onChange: (newOffset) => loadJobs(newOffset),
    });
  } catch (err) {
    el.innerHTML = `<div class="text-center text-secondary" style="padding:2rem">Failed to load extractions: ${esc(err.message)}</div>`;
  }
}

function progressIndicator(job) {
  if (!job.stages_completed && job.stages_completed !== 0) return '';
  const pct = job.progress_percent || 0;
  return `<div class="progress-bar" style="margin-top:4px;height:4px"><div class="progress-fill" style="width:${Math.min(pct, 95)}%"></div></div>`;
}

function startPollJob(jobId) {
  if (pollTimers[jobId]) return;
  pollTimers[jobId] = setTimeout(async () => {
    delete pollTimers[jobId];
    try {
      const job = await apiGet('/api/v1/jobs/' + jobId);
      if (job.status === 'processing' || job.status === 'pending') {
        startPollJob(jobId);
      }
      // Reload the table to show updated status
      loadJobs(currentOffset);
    } catch {
      // Silently stop polling on error
    }
  }, 5000);
}

export function destroy() {
  // Clear all poll timers
  Object.keys(pollTimers).forEach(id => {
    clearTimeout(pollTimers[id]);
    delete pollTimers[id];
  });
}
