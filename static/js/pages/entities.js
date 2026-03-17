// Entity List Page — Meridian Design System
import { apiGet, apiFetch } from '../api.js';
import { esc, timeAgo } from '../state.js';
import { navigate } from '../router.js';
import { showModal } from '../components/modal.js';
import { skeletonTable, errorState } from '../components/loading.js';
import { emptyState } from '../components/empty-state.js';
import { showToast } from '../components/toast.js';

let allEntities = [];

export async function render(container) {
  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1.25rem">
      <div>
        <p class="eyebrow">PORTFOLIO</p>
        <h1 class="page-title">Entities</h1>
      </div>
      <div>
        <button class="btn" id="ent-create-btn" style="background:#1D6B9F;color:white;border:none;border-radius:var(--border-radius-md);padding:7px 16px;font-size:13px;font-weight:500;cursor:pointer">Create Entity</button>
      </div>
    </div>
    <div class="content-body">
      <div class="card">
        <div style="padding:11px 14px;border-bottom:0.5px solid var(--color-border-tertiary);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
          <span style="font-size:13px;font-weight:500">All Entities</span>
          <input type="text" id="ent-search" placeholder="Search by name..." style="width:auto;min-width:220px;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
        </div>
        <div id="ent-table">${skeletonTable(8, 6)}</div>
      </div>
    </div>
  `;

  document.getElementById('ent-create-btn').addEventListener('click', openCreateModal);
  document.getElementById('ent-search').addEventListener('input', onSearch);

  await loadEntities();
}

async function loadEntities() {
  const el = document.getElementById('ent-table');
  try {
    const data = await apiGet('/api/v1/entities/?limit=200');
    allEntities = data.entities || [];
    renderTable(allEntities);
  } catch (err) {
    el.innerHTML = errorState('Failed to load entities: ' + err.message, 'Retry');
    el.querySelector('.error-retry-btn')?.addEventListener('click', () => loadEntities());
  }
}

function onSearch() {
  const q = (document.getElementById('ent-search')?.value || '').toLowerCase().trim();
  if (!q) {
    renderTable(allEntities);
    return;
  }
  const filtered = allEntities.filter(e => (e.name || '').toLowerCase().includes(q));
  renderTable(filtered);
}

function renderTable(entities) {
  const el = document.getElementById('ent-table');
  if (!el) return;

  if (entities.length === 0) {
    if (allEntities.length === 0) {
      el.innerHTML = emptyState({
        icon: '\u2617',
        title: 'No entities yet',
        description: 'Create your first entity to start tracking extraction patterns.',
      });
    } else {
      el.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No entities match your search.</div>`;
    }
    return;
  }

  let html = '<div class="table-wrapper"><table class="data-table"><thead><tr>';
  html += '<th style="text-align:left">Name</th>';
  html += '<th style="text-align:left">Industry</th>';
  html += '<th style="text-align:center">Currency</th>';
  html += '<th style="text-align:right">Patterns</th>';
  html += '<th style="text-align:right">Files</th>';
  html += '<th style="text-align:right">Avg Confidence</th>';
  html += '<th style="text-align:left">Last Extraction</th>';
  html += '</tr></thead><tbody>';

  for (const e of entities) {
    html += `<tr class="clickable" data-entity-id="${esc(e.id)}">`;
    html += `<td style="text-align:left;font-weight:500">${esc(e.name)}</td>`;
    html += `<td style="text-align:left;color:var(--color-text-secondary)">${esc(e.industry || '\u2014')}</td>`;
    html += `<td style="text-align:center;font-family:'IBM Plex Mono',monospace;font-size:11.5px">${e.default_currency ? esc(e.default_currency) : '\u2014'}</td>`;
    html += `<td style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:11.5px;font-variant-numeric:tabular-nums">${e.patterns_count != null ? e.patterns_count : '\u2014'}</td>`;
    html += `<td style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:11.5px;font-variant-numeric:tabular-nums">${e.files_count != null ? e.files_count : '\u2014'}</td>`;
    html += `<td style="text-align:right;font-family:'IBM Plex Mono',monospace;font-size:11.5px;font-variant-numeric:tabular-nums">${e.avg_confidence != null ? (e.avg_confidence * 100).toFixed(0) + '%' : '\u2014'}</td>`;
    html += `<td style="text-align:left;font-size:11.5px;color:var(--color-text-secondary)">${timeAgo(e.created_at)}</td>`;
    html += '</tr>';
  }

  html += '</tbody></table></div>';
  el.innerHTML = html;

  el.querySelectorAll('tr.clickable').forEach(tr => {
    tr.addEventListener('click', () => {
      navigate('/entities/' + tr.dataset.entityId);
    });
  });
}

function openCreateModal() {
  const monthOptions = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    .map((name, i) => `<option value="${i + 1}">${name}</option>`).join('');

  const { close, el: box } = showModal(`
    <h3 style="margin:0 0 16px">Create Entity</h3>
    <form id="ent-create-form">
      <div style="margin-bottom:12px">
        <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Name <span style="color:#A32626">*</span></label>
        <input type="text" id="ent-name" required style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
      </div>
      <div style="margin-bottom:12px">
        <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Industry</label>
        <input type="text" id="ent-industry" placeholder="e.g. Energy, Manufacturing..." style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
      </div>
      <div style="display:flex;gap:12px;margin-bottom:16px">
        <div style="flex:1">
          <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Fiscal Year End</label>
          <select id="ent-fye" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
            <option value="">Not set</option>
            ${monthOptions}
          </select>
        </div>
        <div style="flex:1">
          <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Currency</label>
          <input type="text" id="ent-currency" placeholder="USD" maxlength="3" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary);text-transform:uppercase;font-family:'IBM Plex Mono',monospace">
        </div>
        <div style="flex:1">
          <label style="font-size:11.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Reporting Standard</label>
          <select id="ent-standard" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
            <option value="">Not set</option>
            <option value="GAAP">GAAP</option>
            <option value="IFRS">IFRS</option>
            <option value="Other">Other</option>
          </select>
        </div>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:8px">
        <button type="button" class="modal-cancel-btn" style="background:transparent;color:var(--color-text-secondary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:7px 16px;font-size:13px;cursor:pointer">Cancel</button>
        <button type="submit" style="background:#1D6B9F;color:white;border:none;border-radius:var(--border-radius-md);padding:7px 16px;font-size:13px;font-weight:500;cursor:pointer">Create</button>
      </div>
    </form>
  `);

  box.querySelector('.modal-cancel-btn').addEventListener('click', close);

  box.querySelector('#ent-create-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = box.querySelector('#ent-name').value.trim();
    const industry = box.querySelector('#ent-industry').value.trim() || null;
    const fyeVal = box.querySelector('#ent-fye').value;
    const fiscal_year_end = fyeVal ? parseInt(fyeVal) : null;
    const default_currency = box.querySelector('#ent-currency').value.trim().toUpperCase() || null;
    const reporting_standard = box.querySelector('#ent-standard').value || null;

    if (!name) {
      showToast('Entity name is required', 'error');
      return;
    }

    const submitBtn = box.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating...';

    try {
      await apiFetch('/api/v1/entities/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, industry, fiscal_year_end, default_currency, reporting_standard }),
      });
      close();
      showToast('Entity created', 'success');
      await loadEntities();
    } catch (err) {
      showToast('Failed to create entity: ' + err.message, 'error');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create';
    }
  });

  box.querySelector('#ent-name').focus();
}

export function destroy() {
  allEntities = [];
}
