// Drag-and-Drop Upload Component
import { getApiKey } from '../api.js';
import { showToast } from './toast.js';

/**
 * Render an upload drop zone.
 * @param {HTMLElement} container
 * @param {Object} opts
 * @param {boolean} [opts.compact] - compact mode for inline use
 * @param {string} [opts.entityId] - pre-set entity ID (skips dropdown)
 * @param {Function} opts.onUploadComplete - (data) => void — called with upload response JSON
 * @param {Function} [opts.onUploadStart] - () => void
 * @param {Function} [opts.onError] - (error) => void
 */
export function renderUploadZone(container, opts) {
  const compact = opts.compact ? ' drop-zone-compact' : '';
  const entitySelectHtml = opts.entityId ? '' : `
    <div style="margin-bottom:8px">
      <label style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary);display:block;margin-bottom:4px">Entity (optional)</label>
      <select id="upload-entity-select" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12.5px;background:var(--color-background-primary);color:var(--color-text-primary)">
        <option value="">No entity (standalone)</option>
      </select>
    </div>
  `;

  container.innerHTML = `
    ${entitySelectHtml}
    <div class="drop-zone${compact}" id="upload-drop-zone">
      <p class="drop-text">${opts.compact ? 'Drop Excel file here or click to upload' : 'Drag & drop an Excel file here'}</p>
      ${opts.compact ? '' : '<p class="drop-hint">or click to browse (.xlsx, .xls)</p>'}
      <input type="file" id="upload-file-input" accept=".xlsx,.xls" hidden>
    </div>
    <div class="upload-progress" id="upload-progress" style="display:none">
      <div class="upload-progress-fill" id="upload-progress-fill" style="width:0%"></div>
    </div>
    <p id="upload-status-text" class="text-secondary text-sm" style="margin-top:0.5rem"></p>
  `;

  // Populate entity dropdown if no entityId pre-set
  if (!opts.entityId) {
    const entitySelect = container.querySelector('#upload-entity-select');
    if (entitySelect) {
      const apiKey = getApiKey();
      if (apiKey) {
        fetch('/api/v1/entities/?limit=200', {
          headers: { 'Authorization': 'Bearer ' + apiKey },
        })
          .then(r => r.json())
          .then(data => {
            for (const e of (data.entities || [])) {
              const option = document.createElement('option');
              option.value = e.id;
              option.textContent = e.name + (e.industry ? ' (' + e.industry + ')' : '');
              entitySelect.appendChild(option);
            }
          })
          .catch(() => { /* best effort */ });
      }
    }
  }

  const dropZone = container.querySelector('#upload-drop-zone');
  const fileInput = container.querySelector('#upload-file-input');
  const statusText = container.querySelector('#upload-status-text');
  const progressBar = container.querySelector('#upload-progress');
  const progressFill = container.querySelector('#upload-progress-fill');

  dropZone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) doUpload(fileInput.files[0]);
    fileInput.value = '';
  });

  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) doUpload(e.dataTransfer.files[0]);
  });

  function doUpload(file) {
    if (!file.name.match(/\.xlsx?$/i)) {
      statusText.textContent = 'Only .xlsx and .xls files are accepted.';
      return;
    }

    const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100 MB
    if (file.size > MAX_FILE_SIZE) {
      statusText.textContent = `File too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum size is 100 MB.`;
      return;
    }

    const apiKey = getApiKey();
    if (!apiKey) {
      showToast('API key is required. Configure it in the sidebar.', 'error');
      return;
    }

    statusText.textContent = 'Uploading ' + file.name + '... 0%';
    progressBar.style.display = '';
    progressFill.style.width = '0%';
    if (opts.onUploadStart) opts.onUploadStart();

    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    // Attach entity_id: from opts or dropdown selection
    const entityId = opts.entityId || (container.querySelector('#upload-entity-select') || {}).value;
    if (entityId) formData.append('entity_id', entityId);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        statusText.textContent = `Uploading ${file.name}... ${pct}%`;
        progressFill.style.width = pct + '%';
      }
    };

    xhr.onload = () => {
      progressBar.style.display = 'none';
      progressFill.style.width = '0%';

      if (xhr.status >= 200 && xhr.status < 300) {
        let data;
        try {
          data = JSON.parse(xhr.responseText);
        } catch (e) {
          statusText.textContent = '';
          const err = new Error('Invalid response from server');
          if (opts.onError) { opts.onError(err); } else { showToast(err.message, 'error'); }
          return;
        }

        statusText.textContent = '';
        if (data.status === 'duplicate') {
          showToast('Duplicate file — loading existing results', 'info');
        }
        opts.onUploadComplete(data);
      } else {
        statusText.textContent = '';
        let message = `Upload failed (${xhr.status})`;
        try {
          const body = JSON.parse(xhr.responseText);
          if (body.detail) message = body.detail;
        } catch (e) { /* use default message */ }

        const err = new Error(message);
        if (opts.onError) { opts.onError(err); } else { showToast(message, 'error'); }
      }
    };

    xhr.onerror = () => {
      progressBar.style.display = 'none';
      progressFill.style.width = '0%';
      statusText.textContent = '';
      const err = new Error('Network error — upload failed');
      if (opts.onError) { opts.onError(err); } else { showToast(err.message, 'error'); }
    };

    xhr.open('POST', '/api/v1/files/upload');
    xhr.setRequestHeader('Authorization', 'Bearer ' + apiKey);
    xhr.send(formData);
  }
}
