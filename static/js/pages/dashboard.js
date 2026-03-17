// Dashboard Page — Portfolio overview + recent jobs + quick upload
import { apiGet } from '../api.js';
import { esc, timeAgo } from '../state.js';
import { navigate } from '../router.js';
import { renderUploadZone } from '../components/upload.js';
import { statusBadge, qualityBadge } from '../components/badge.js';
import { skeletonStats, skeletonTable, errorState } from '../components/loading.js';
import { emptyState } from '../components/empty-state.js';
import { showToast } from '../components/toast.js';

export async function render(container) {
  container.innerHTML = `
    <div class="content-header">
      <h2>Dashboard</h2>
    </div>
    <div class="content-body">
      <div class="grid-2" style="margin-bottom:var(--space-6)">
        <div>
          <div id="dash-stats">${skeletonStats(4)}</div>
        </div>
        <div>
          <div class="card">
            <div class="card-header"><span class="card-title">Upload Model</span></div>
            <div id="dash-upload"></div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title">Recent Extractions</span>
          <a href="#/extractions" class="btn btn-ghost btn-sm">View All</a>
        </div>
        <div id="dash-jobs">${skeletonTable(5, 5)}</div>
      </div>
    </div>
  `;

  // Render upload zone
  renderUploadZone(document.getElementById('dash-upload'), {
    compact: true,
    onUploadComplete(data) {
      const jobId = data.job_id;
      if (jobId) {
        navigate('/extractions/' + jobId);
      }
    },
  });

  // Load data
  loadStats();
  loadRecentJobs();
}

async function loadStats() {
  const el = document.getElementById('dash-stats');
  try {
    const data = await apiGet('/api/v1/analytics/portfolio/summary');
    el.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card">
          <span class="stat-value">${data.total_entities || 0}</span>
          <span class="stat-label">Entities</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">${data.total_jobs || 0}</span>
          <span class="stat-label">Extractions</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">${data.avg_confidence != null ? (data.avg_confidence * 100).toFixed(0) + '%' : 'N/A'}</span>
          <span class="stat-label">Avg Confidence</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">$${(data.total_cost || 0).toFixed(2)}</span>
          <span class="stat-label">Total Cost</span>
        </div>
      </div>
    `;
  } catch (err) {
    el.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card"><span class="stat-value">-</span><span class="stat-label">Entities</span></div>
        <div class="stat-card"><span class="stat-value">-</span><span class="stat-label">Extractions</span></div>
        <div class="stat-card"><span class="stat-value">-</span><span class="stat-label">Avg Confidence</span></div>
        <div class="stat-card"><span class="stat-value">-</span><span class="stat-label">Total Cost</span></div>
      </div>
    `;
  }
}

async function loadRecentJobs() {
  const el = document.getElementById('dash-jobs');
  try {
    const data = await apiGet('/api/v1/jobs/?limit=10&offset=0');
    const jobs = data.jobs || [];

    if (jobs.length === 0) {
      el.innerHTML = emptyState({ icon: '\uD83D\uDCC4', title: 'No extractions yet', description: 'Upload an Excel file to get started.', actionLabel: 'Go to Extractions', actionRoute: '/extractions' });
      return;
    }

    let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
    html += '<th>File</th><th>Status</th><th>Quality</th><th>Stage</th><th>Date</th>';
    html += '</tr></thead><tbody>';

    for (const job of jobs) {
      const filename = esc(job.filename || 'Unknown');
      const stage = job.current_stage ? esc(friendlyStage(job.current_stage)) : '-';
      const stageInfo = job.status === 'processing' && job.stages_completed != null
        ? `${job.stages_completed}/${job.total_stages || 5}: ${stage}`
        : stage;

      html += `<tr class="clickable" data-job-id="${esc(job.job_id)}">`;
      html += `<td><strong>${filename}</strong></td>`;
      html += `<td>${statusBadge(job.status)}</td>`;
      html += `<td>${job.quality ? qualityBadge(job.quality) : '-'}</td>`;
      html += `<td class="text-sm text-secondary">${job.status === 'processing' ? stageInfo : '-'}</td>`;
      html += `<td class="text-sm text-secondary">${timeAgo(job.created_at)}</td>`;
      html += '</tr>';
    }

    html += '</tbody></table></div>';
    el.innerHTML = html;

    // Click to navigate to job detail
    el.querySelectorAll('tr.clickable').forEach(tr => {
      tr.addEventListener('click', () => {
        navigate('/extractions/' + tr.dataset.jobId);
      });
    });
  } catch (err) {
    el.innerHTML = errorState('Failed to load recent extractions', 'Retry');
    el.querySelector('.error-retry-btn')?.addEventListener('click', () => loadRecentJobs());
  }
}

const STAGE_NAMES = {
  parsing: 'Parsing Excel',
  triage: 'Classifying Sheets',
  mapping: 'Mapping Labels',
  validation: 'Validating Data',
  enhanced_mapping: 'Refining Mappings',
};

function friendlyStage(stage) {
  return STAGE_NAMES[stage] || stage || '';
}

export function destroy() {
  // No cleanup needed
}
