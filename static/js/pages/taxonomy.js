// Taxonomy Browser Page — Meridian Design System
import { apiGet, apiPost, apiFetch } from '../api.js';
import { esc, timeAgo } from '../state.js';
import { loadingPlaceholder, errorState } from '../components/loading.js';
import { showToast } from '../components/toast.js';
import { renderTabs } from '../components/tabs.js';
import { confirm as confirmModal } from '../components/modal.js';
import { CATEGORY_LABELS, CATEGORY_BADGE_CLASS } from '../constants/categories.js';

const DEBOUNCE_MS = 300;

// --- Module state ---

let _container = null;
let _stats = null;
let _activeCategory = 'all';
let _searchTimer = null;
let _searchQuery = '';
let _detailItem = null;
let _expandedParents = new Set();
let _cleanupFns = [];
let _tabControls = null;

// --- Public API ---

export async function render(container) {
  _container = container;
  _activeCategory = 'all';
  _searchQuery = '';
  _detailItem = null;
  _expandedParents = new Set();

  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1.25rem">
      <div>
        <p class="eyebrow">REFERENCE</p>
        <h1 class="page-title">Taxonomy</h1>
        <p id="tax-subtitle" class="text-secondary text-sm" style="margin-top:2px">Loading...</p>
      </div>
    </div>
    <div id="tax-tabs-container"></div>
  `;

  const tabContainer = document.getElementById('tax-tabs-container');
  _tabControls = renderTabs(tabContainer, [
    { id: 'browse', label: 'Browse', render: _renderBrowseTab },
    { id: 'suggestions', label: 'Suggestions', render: _renderSuggestionsTab },
    { id: 'changelog', label: 'Changelog', render: _renderChangelogTab },
  ], 'browse');
}

export function destroy() {
  for (const fn of _cleanupFns) fn();
  _cleanupFns = [];
  if (_searchTimer) clearTimeout(_searchTimer);
  _searchTimer = null;
  _container = null;
  _stats = null;
  _activeCategory = 'all';
  _searchQuery = '';
  _detailItem = null;
  _expandedParents = new Set();
  _tabControls = null;
}

// ============================================================================
// BROWSE TAB
// ============================================================================

async function _renderBrowseTab(panel) {
  panel.innerHTML = `
    <div class="content-body">
      <div id="tax-search-bar" style="margin-bottom:12px">
        <div style="position:relative">
          <input type="text" id="tax-search-input"
            placeholder="Search taxonomy by name or alias..."
            style="width:100%;padding:8px 36px 8px 12px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:13px;background:var(--color-background-primary);color:var(--color-text-primary)">
          <button id="tax-search-clear"
            style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;font-size:16px;color:var(--color-text-tertiary);display:none;padding:2px 4px"
            aria-label="Clear search">&times;</button>
        </div>
      </div>
      <div id="tax-pills" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px"></div>
      <div id="tax-main">${loadingPlaceholder('Loading taxonomy...')}</div>
      <div id="tax-detail"></div>
    </div>
  `;

  _bindSearch();
  await _loadStats();
}

// --- Data loading ---

async function _loadStats() {
  try {
    _stats = await apiGet('/api/v1/taxonomy/stats');
    const subtitle = document.getElementById('tax-subtitle');
    if (subtitle) {
      subtitle.textContent = `${_stats.total_items || 0} items across ${Object.keys(_stats.categories || {}).length} categories`;
    }
    _renderPills();
    _renderMainContent();
  } catch (err) {
    const main = document.getElementById('tax-main');
    if (main) {
      main.innerHTML = errorState('Failed to load taxonomy: ' + err.message, 'Retry');
      main.querySelector('.error-retry-btn')?.addEventListener('click', () => _loadStats());
    }
  }
}

// --- Search ---

function _bindSearch() {
  const input = document.getElementById('tax-search-input');
  const clearBtn = document.getElementById('tax-search-clear');
  if (!input || !clearBtn) return;

  const onInput = () => {
    const q = input.value.trim();
    clearBtn.style.display = q ? 'block' : 'none';

    if (_searchTimer) clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => {
      _searchQuery = q;
      if (q) {
        _performSearch(q);
      } else {
        _renderMainContent();
      }
    }, DEBOUNCE_MS);
  };

  const onClear = () => {
    input.value = '';
    clearBtn.style.display = 'none';
    _searchQuery = '';
    if (_searchTimer) clearTimeout(_searchTimer);
    _closeDetail();
    _renderMainContent();
    input.focus();
  };

  input.addEventListener('input', onInput);
  clearBtn.addEventListener('click', onClear);

  _cleanupFns.push(() => {
    input.removeEventListener('input', onInput);
    clearBtn.removeEventListener('click', onClear);
  });
}

async function _performSearch(query) {
  const main = document.getElementById('tax-main');
  if (!main) return;

  main.innerHTML = loadingPlaceholder('Searching...');
  _closeDetail();

  try {
    const data = await apiGet(`/api/v1/taxonomy/search?q=${encodeURIComponent(query)}`);
    const allItems = data.items || [];

    if (allItems.length === 0) {
      main.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No results for "${esc(query)}"</div>`;
      return;
    }

    const MAX_SEARCH_RESULTS = 100;
    const items = allItems.slice(0, MAX_SEARCH_RESULTS);
    const truncated = allItems.length > MAX_SEARCH_RESULTS;
    _renderSearchResults(items, truncated ? allItems.length : null);
  } catch (err) {
    main.innerHTML = errorState('Search failed: ' + err.message, 'Retry');
    main.querySelector('.error-retry-btn')?.addEventListener('click', () => _performSearch(query));
  }
}

function _renderSearchResults(items, totalCount) {
  const main = document.getElementById('tax-main');
  if (!main) return;

  let html = '<div class="card" style="padding:0;overflow:hidden">';
  html += '<div style="padding:11px 14px;border-bottom:0.5px solid var(--color-border-tertiary)">';
  const countLabel = totalCount
    ? `Showing ${items.length} of ${totalCount} results`
    : `${items.length} result${items.length !== 1 ? 's' : ''}`;
  html += `<span style="font-size:13px;font-weight:500">${countLabel}</span>`;
  html += '</div>';
  html += '<div class="table-wrapper" style="border:none;border-radius:0">';
  html += '<table class="data-table"><thead><tr>';
  html += '<th style="text-align:left">Canonical Name</th>';
  html += '<th style="text-align:left">Category</th>';
  html += '<th style="text-align:left">Display Name</th>';
  html += '<th style="text-align:left">Typical Sign</th>';
  html += '</tr></thead><tbody>';

  for (const item of items) {
    const badgeClass = CATEGORY_BADGE_CLASS[item.category] || 'b-gray';
    const catLabel = CATEGORY_LABELS[item.category] || item.category || '';
    html += `<tr class="clickable" data-canonical="${esc(item.canonical_name)}">`;
    html += `<td><span class="text-mono">${esc(item.canonical_name)}</span></td>`;
    html += `<td><span class="badge ${badgeClass}">${esc(catLabel)}</span></td>`;
    html += `<td>${esc(item.display_name || '')}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary)">${esc(item.typical_sign || '\u2014')}</td>`;
    html += '</tr>';
  }

  html += '</tbody></table></div></div>';
  main.innerHTML = html;

  _bindRowClicks(main);
}

// --- Category Pills ---

function _renderPills() {
  const el = document.getElementById('tax-pills');
  if (!el) return;

  const categories = _stats?.categories ? Object.keys(_stats.categories) : [];

  let html = _pillHtml('all', 'All', _activeCategory === 'all');
  for (const cat of categories) {
    const label = CATEGORY_LABELS[cat] || cat;
    html += _pillHtml(cat, label, _activeCategory === cat);
  }
  el.innerHTML = html;

  // Bind pill clicks
  el.querySelectorAll('[data-pill]').forEach(btn => {
    const handler = () => {
      _activeCategory = btn.dataset.pill;
      _searchQuery = '';
      const input = document.getElementById('tax-search-input');
      const clearBtn = document.getElementById('tax-search-clear');
      if (input) input.value = '';
      if (clearBtn) clearBtn.style.display = 'none';
      _closeDetail();
      _expandedParents = new Set();
      _renderPills();
      _renderMainContent();
    };
    btn.addEventListener('click', handler);
    _cleanupFns.push(() => btn.removeEventListener('click', handler));
  });
}

function _pillHtml(value, label, active) {
  const bg = active ? '#1D6B9F' : 'var(--color-background-secondary)';
  const color = active ? '#FFFFFF' : 'var(--color-text-secondary)';
  const border = active ? '0.5px solid #1D6B9F' : '0.5px solid var(--color-border-tertiary)';
  return `<button data-pill="${esc(value)}" style="display:inline-flex;align-items:center;padding:4px 14px;border-radius:100px;border:${border};background:${bg};color:${color};font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background 0.15s ease,color 0.15s ease">${esc(label)}</button>`;
}

// --- Main Content ---

function _renderMainContent() {
  if (_searchQuery) return; // search results are handled separately

  if (_activeCategory === 'all') {
    _renderCategoryOverview();
  } else {
    _renderCategoryDetail(_activeCategory);
  }
}

// --- Category Overview (grid of cards) ---

function _renderCategoryOverview() {
  const main = document.getElementById('tax-main');
  if (!main || !_stats) return;

  const categories = _stats.categories || {};
  const catKeys = Object.keys(categories);

  if (catKeys.length === 0) {
    main.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No categories found.</div>`;
    return;
  }

  let html = '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px">';

  for (const cat of catKeys) {
    const label = CATEGORY_LABELS[cat] || cat;
    const count = categories[cat] || 0;
    const badgeClass = CATEGORY_BADGE_CLASS[cat] || 'b-gray';

    html += `<div class="card" data-cat-card="${esc(cat)}" style="cursor:pointer;padding:16px 18px;transition:border-color 0.15s ease">`;
    html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">`;
    html += `<span class="badge ${badgeClass}" style="font-size:10px;padding:1px 7px">${esc(label)}</span>`;
    html += '</div>';
    html += `<div style="font-family:var(--font-serif);font-size:1.25rem;font-weight:400;color:var(--color-text-primary);line-height:1.1">${count}</div>`;
    html += `<div style="font-size:11px;color:var(--color-text-secondary);margin-top:2px">item${count !== 1 ? 's' : ''}</div>`;
    html += '</div>';
  }

  html += '</div>';
  main.innerHTML = html;

  // Bind card clicks to select category pill
  main.querySelectorAll('[data-cat-card]').forEach(card => {
    const handler = () => {
      _activeCategory = card.dataset.catCard;
      _closeDetail();
      _expandedParents = new Set();
      _renderPills();
      _renderMainContent();
    };
    card.addEventListener('click', handler);
    _cleanupFns.push(() => card.removeEventListener('click', handler));
  });
}

// --- Category Detail (hierarchy tree) ---

async function _renderCategoryDetail(category) {
  const main = document.getElementById('tax-main');
  if (!main) return;

  main.innerHTML = loadingPlaceholder('Loading hierarchy...');
  _closeDetail();

  try {
    const data = await apiGet(`/api/v1/taxonomy/hierarchy?category=${encodeURIComponent(category)}`);

    const parents = data || {};
    const parentKeys = Object.keys(parents);

    if (parentKeys.length === 0) {
      await _renderFlatCategory(category);
      return;
    }

    _renderHierarchyTable(parents, parentKeys);
  } catch (err) {
    try {
      await _renderFlatCategory(category);
    } catch (err2) {
      main.innerHTML = errorState('Failed to load category: ' + err2.message, 'Retry');
      main.querySelector('.error-retry-btn')?.addEventListener('click', () => _renderCategoryDetail(category));
    }
  }
}

async function _renderFlatCategory(category) {
  const main = document.getElementById('tax-main');
  if (!main) return;

  const data = await apiGet(`/api/v1/taxonomy/?category=${encodeURIComponent(category)}`);
  const items = data.items || [];

  if (items.length === 0) {
    main.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No items in this category.</div>`;
    return;
  }

  let html = '<div class="card" style="padding:0;overflow:hidden">';
  html += `<div style="padding:11px 14px;border-bottom:0.5px solid var(--color-border-tertiary)">`;
  html += `<span style="font-size:13px;font-weight:500">${CATEGORY_LABELS[category] || category}</span>`;
  html += `<span style="font-size:11px;color:var(--color-text-secondary);margin-left:8px">${items.length} items</span>`;
  html += '</div>';
  html += '<div class="table-wrapper" style="border:none;border-radius:0">';
  html += '<table class="data-table"><thead><tr>';
  html += '<th style="text-align:left">Canonical Name</th>';
  html += '<th style="text-align:left">Display Name</th>';
  html += '<th style="text-align:left">Typical Sign</th>';
  html += '<th style="text-align:left">Aliases</th>';
  html += '</tr></thead><tbody>';

  for (const item of items) {
    const aliases = _formatAliases(item.aliases);
    html += `<tr class="clickable" data-canonical="${esc(item.canonical_name)}">`;
    html += `<td><span class="text-mono">${esc(item.canonical_name)}</span></td>`;
    html += `<td>${esc(item.display_name || '')}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary)">${esc(item.typical_sign || '\u2014')}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(aliases)}</td>`;
    html += '</tr>';
  }

  html += '</tbody></table></div></div>';
  main.innerHTML = html;

  _bindRowClicks(main);
}

function _renderHierarchyTable(parents, parentKeys) {
  const main = document.getElementById('tax-main');
  if (!main) return;

  const catLabel = CATEGORY_LABELS[_activeCategory] || _activeCategory;

  let html = '<div class="card" style="padding:0;overflow:hidden">';
  html += `<div style="padding:11px 14px;border-bottom:0.5px solid var(--color-border-tertiary)">`;
  html += `<span style="font-size:13px;font-weight:500">${esc(catLabel)}</span>`;
  html += `<span style="font-size:11px;color:var(--color-text-secondary);margin-left:8px">${parentKeys.length} group${parentKeys.length !== 1 ? 's' : ''}</span>`;
  html += '</div>';
  html += '<div class="table-wrapper" style="border:none;border-radius:0">';
  html += '<table class="data-table"><thead><tr>';
  html += '<th style="text-align:left;width:28px"></th>';
  html += '<th style="text-align:left">Canonical Name</th>';
  html += '<th style="text-align:left">Display Name</th>';
  html += '<th style="text-align:left">Typical Sign</th>';
  html += '<th style="text-align:left">Aliases</th>';
  html += '</tr></thead><tbody>';

  function renderNodeRows(node, depth) {
    const children = node.children || [];
    const hasChildren = children.length > 0;
    const isExpanded = _expandedParents.has(node.canonical_name);
    const chevron = hasChildren ? (isExpanded ? '\u25BC' : '\u25B6') : '';
    const indent = depth * 20;
    const isRoot = depth === 0;
    const fontSize = isRoot ? '12px' : '11px';
    const weight = isRoot ? 'font-weight:500' : '';
    const bg = depth > 0 ? 'background:var(--color-background-secondary)' : '';

    html += `<tr class="clickable" data-canonical="${esc(node.canonical_name)}" style="${weight};${bg}">`;
    html += `<td style="text-align:center;font-size:9px;color:var(--color-text-tertiary);padding:6px 4px;width:28px;cursor:${hasChildren ? 'pointer' : 'default'}" data-toggle="${esc(node.canonical_name)}">${chevron}</td>`;
    html += `<td style="padding-left:${indent}px"><span class="text-mono" style="font-size:${fontSize}">${esc(node.canonical_name)}</span></td>`;
    html += `<td style="font-size:${fontSize}">${esc(node.display_name || '')}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary)">${esc(node.typical_sign || '\u2014')}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(_formatAliases(node.aliases))}</td>`;
    html += '</tr>';

    if (hasChildren && isExpanded) {
      for (const child of children) {
        renderNodeRows(child, depth + 1);
      }
    }
  }

  for (const key of parentKeys) {
    renderNodeRows(parents[key], 0);
  }

  html += '</tbody></table></div></div>';
  main.innerHTML = html;

  // Bind expand/collapse toggles
  main.querySelectorAll('[data-toggle]').forEach(td => {
    const handler = (e) => {
      e.stopPropagation();
      const key = td.dataset.toggle;

      if (_expandedParents.has(key)) {
        _expandedParents.delete(key);
      } else {
        _expandedParents.add(key);
      }
      _renderHierarchyTable(parents, parentKeys);
    };
    td.addEventListener('click', handler);
    _cleanupFns.push(() => td.removeEventListener('click', handler));
  });

  // Bind row clicks for detail view
  main.querySelectorAll('tr.clickable[data-canonical]').forEach(tr => {
    const handler = (e) => {
      if (e.target.closest('[data-toggle]')) return;
      const canonical = tr.dataset.canonical;
      if (canonical) _showDetail(canonical);
    };
    tr.addEventListener('click', handler);
    _cleanupFns.push(() => tr.removeEventListener('click', handler));
  });
}

// --- Row click binding (for search results and flat list) ---

function _bindRowClicks(container) {
  container.querySelectorAll('tr.clickable[data-canonical]').forEach(tr => {
    const handler = () => _showDetail(tr.dataset.canonical);
    tr.addEventListener('click', handler);
    _cleanupFns.push(() => tr.removeEventListener('click', handler));
  });
}

// --- Item Detail Panel ---

async function _showDetail(canonicalName) {
  const el = document.getElementById('tax-detail');
  if (!el) return;

  _detailItem = canonicalName;

  el.innerHTML = `
    <div class="card" style="margin-top:12px;position:relative">
      <div style="text-align:center;padding:1.5rem">
        <span class="spinner"></span>
        <p class="text-secondary text-sm" style="margin-top:8px">Loading item...</p>
      </div>
    </div>
  `;

  try {
    const item = await apiGet(`/api/v1/taxonomy/${encodeURIComponent(canonicalName)}`);

    // If a different item was selected while loading, skip render
    if (_detailItem !== canonicalName) return;

    const badgeClass = CATEGORY_BADGE_CLASS[item.category] || 'b-gray';
    const catLabel = CATEGORY_LABELS[item.category] || item.category || '';
    const aliases = _formatAliases(item.aliases);
    const validationRules = _formatValidationRules(item.validation_rules);

    let html = '<div class="card" style="margin-top:12px;position:relative">';

    // Close button
    html += '<button id="tax-detail-close" style="position:absolute;top:10px;right:14px;background:none;border:none;cursor:pointer;font-size:18px;color:var(--color-text-tertiary);padding:2px 6px;line-height:1" aria-label="Close detail">&times;</button>';

    // Header
    html += '<div style="margin-bottom:12px">';
    html += `<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">`;
    html += `<span class="text-mono" style="font-size:14px;font-weight:500">${esc(item.canonical_name)}</span>`;
    html += `<span class="badge ${badgeClass}">${esc(catLabel)}</span>`;

    // Deprecated badge
    if (item.deprecated) {
      html += `<span class="badge b-bad" style="font-size:10px">Deprecated</span>`;
    }

    html += '</div>';
    if (item.display_name) {
      html += `<div style="font-size:13px;color:var(--color-text-secondary);margin-top:4px">${esc(item.display_name)}</div>`;
    }
    html += '</div>';

    // Deprecation notice
    if (item.deprecated) {
      html += '<div style="background:#FDEAEA;border:1px solid #E8CACA;border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:12px">';
      html += '<strong style="color:#A32626">This item is deprecated.</strong>';
      if (item.deprecated_redirect) {
        html += ` Redirects to <span class="text-mono" style="cursor:pointer;color:#1D6B9F;text-decoration:underline" data-goto-canonical="${esc(item.deprecated_redirect)}">${esc(item.deprecated_redirect)}</span>.`;
      }
      if (item.deprecated_at) {
        html += ` <span style="color:var(--color-text-secondary)">(${esc(timeAgo(item.deprecated_at))})</span>`;
      }
      html += '</div>';
    }

    // Detail grid
    html += '<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 24px">';

    html += _detailField('Definition', item.definition || '\u2014');
    html += _detailField('Typical Sign', item.typical_sign || '\u2014');
    html += _detailField('Parent', item.parent_canonical ? item.parent_canonical : '\u2014', true);
    html += _detailField('Aliases', aliases || '\u2014');

    if (validationRules) {
      html += `<div style="grid-column:1/-1">${_detailField('Validation Rules', validationRules)}</div>`;
    }

    html += '</div>';

    // Deprecate action (only if not already deprecated)
    if (!item.deprecated) {
      html += '<div style="margin-top:16px;padding-top:12px;border-top:0.5px solid var(--color-border-tertiary)">';
      html += `<button class="btn btn-sm btn-ghost" id="tax-deprecate-btn" style="font-size:11px;color:var(--color-text-secondary)">Deprecate this item...</button>`;
      html += '</div>';
    }

    html += '</div>';

    el.innerHTML = html;

    // Bind close button
    const closeBtn = document.getElementById('tax-detail-close');
    if (closeBtn) {
      const handler = () => _closeDetail();
      closeBtn.addEventListener('click', handler);
      _cleanupFns.push(() => closeBtn.removeEventListener('click', handler));
    }

    // Bind deprecate button
    const deprecateBtn = document.getElementById('tax-deprecate-btn');
    if (deprecateBtn) {
      const handler = () => _handleDeprecate(item.canonical_name);
      deprecateBtn.addEventListener('click', handler);
      _cleanupFns.push(() => deprecateBtn.removeEventListener('click', handler));
    }

    // Bind redirect link
    el.querySelectorAll('[data-goto-canonical]').forEach(link => {
      const handler = (e) => {
        e.preventDefault();
        _showDetail(link.dataset.gotoCanonical);
      };
      link.addEventListener('click', handler);
      _cleanupFns.push(() => link.removeEventListener('click', handler));
    });

    // Scroll detail into view
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    if (_detailItem !== canonicalName) return;
    el.innerHTML = `<div class="card" style="margin-top:12px">${errorState('Failed to load item: ' + err.message, 'Retry')}</div>`;
    el.querySelector('.error-retry-btn')?.addEventListener('click', () => _showDetail(canonicalName));
  }
}

async function _handleDeprecate(canonicalName) {
  // Use showModal for manual control so we can read the redirect input before closing.
  const { showModal: openModal } = await import('../components/modal.js');
  const { close, el } = openModal(`
    <h3 style="margin:0 0 12px">${esc('Deprecate Taxonomy Item')}</h3>
    <p style="margin-bottom:12px">Are you sure you want to deprecate <strong>${esc(canonicalName)}</strong>?</p>
    <p style="font-size:12px;color:var(--color-text-secondary)">Deprecated items are excluded from extraction prompts and will no longer be used for mapping. This action is recorded in the changelog.</p>
    <div style="margin-top:12px">
      <label style="font-size:12px;font-weight:500;display:block;margin-bottom:4px">Redirect to (optional):</label>
      <input type="text" id="deprecate-redirect-input" placeholder="e.g. total_revenue" style="width:100%;padding:6px 10px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12px;font-family:var(--font-mono)">
    </div>
    <div class="modal-actions" style="margin-top:16px">
      <button class="btn btn-secondary modal-cancel">Cancel</button>
      <button class="btn btn-destructive modal-confirm">Deprecate</button>
    </div>
  `);

  const confirmed = await new Promise(resolve => {
    el.querySelector('.modal-cancel').addEventListener('click', () => { close(); resolve(false); });
    el.querySelector('.modal-confirm').addEventListener('click', () => resolve(true));
  });

  if (!confirmed) return;

  // Capture redirect value BEFORE closing the modal
  const redirectTo = el.querySelector('#deprecate-redirect-input')?.value?.trim() || '';
  close();

  try {
    const params = redirectTo ? `?redirect_to=${encodeURIComponent(redirectTo)}` : '';
    const res = await apiFetch(`/api/v1/taxonomy/${encodeURIComponent(canonicalName)}/deprecate${params}`, {
      method: 'POST',
    });
    const data = await res.json();
    showToast(`${esc(canonicalName)} deprecated successfully`, 'success');
    _showDetail(canonicalName); // refresh detail
    if (_tabControls) _tabControls.reloadTab('changelog'); // refresh changelog
  } catch (err) {
    showToast('Failed to deprecate: ' + err.message, 'error');
  }
}

function _closeDetail() {
  _detailItem = null;
  const el = document.getElementById('tax-detail');
  if (el) el.innerHTML = '';
}

function _detailField(label, value, isMono) {
  const style = isMono ? 'font-family:var(--font-mono);font-size:11.5px' : 'font-size:12px';
  return `
    <div>
      <div style="font-size:10.5px;font-weight:500;color:var(--color-text-secondary);margin-bottom:2px">${esc(label)}</div>
      <div style="${style};color:var(--color-text-primary);line-height:1.5">${esc(value)}</div>
    </div>
  `;
}


// ============================================================================
// SUGGESTIONS TAB
// ============================================================================

let _suggestionsFilter = 'pending';

async function _renderSuggestionsTab(panel) {
  panel.innerHTML = `
    <div class="content-body">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div style="display:flex;gap:6px" id="sug-filters"></div>
        <div style="font-size:12px;color:var(--color-text-secondary)" id="sug-count"></div>
      </div>
      <div id="sug-main">${loadingPlaceholder('Loading suggestions...')}</div>
    </div>
  `;

  _renderSuggestionFilters(panel);
  await _loadSuggestions(panel);
}

function _renderSuggestionFilters(panel) {
  const el = panel.querySelector('#sug-filters');
  if (!el) return;

  const filters = ['pending', 'accepted', 'rejected', 'all'];
  let html = '';
  for (const f of filters) {
    const label = f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1);
    const active = _suggestionsFilter === f;
    const bg = active ? '#1D6B9F' : 'var(--color-background-secondary)';
    const color = active ? '#FFFFFF' : 'var(--color-text-secondary)';
    const border = active ? '0.5px solid #1D6B9F' : '0.5px solid var(--color-border-tertiary)';
    html += `<button data-sug-filter="${f}" style="display:inline-flex;align-items:center;padding:4px 14px;border-radius:100px;border:${border};background:${bg};color:${color};font-size:12px;font-weight:500;cursor:pointer;white-space:nowrap;transition:background 0.15s ease">${esc(label)}</button>`;
  }
  el.innerHTML = html;

  el.querySelectorAll('[data-sug-filter]').forEach(btn => {
    const handler = () => {
      _suggestionsFilter = btn.dataset.sugFilter;
      _renderSuggestionFilters(panel);
      _loadSuggestions(panel);
    };
    btn.addEventListener('click', handler);
    _cleanupFns.push(() => btn.removeEventListener('click', handler));
  });
}

async function _loadSuggestions(panel) {
  const main = panel.querySelector('#sug-main');
  const countEl = panel.querySelector('#sug-count');
  if (!main) return;

  main.innerHTML = loadingPlaceholder('Loading suggestions...');

  try {
    const statusParam = _suggestionsFilter === 'all' ? '' : `?status=${_suggestionsFilter}`;
    const data = await apiGet(`/api/v1/taxonomy/suggestions${statusParam}`);
    const suggestions = data.suggestions || [];

    if (countEl) countEl.textContent = `${suggestions.length} suggestion${suggestions.length !== 1 ? 's' : ''}`;

    if (suggestions.length === 0) {
      main.innerHTML = `
        <div class="card" style="text-align:center;padding:2.5rem 1rem">
          <div style="font-size:32px;margin-bottom:8px;opacity:0.3">&#x1F4AD;</div>
          <div style="font-size:14px;font-weight:500;color:var(--color-text-primary);margin-bottom:4px">No suggestions</div>
          <div style="font-size:12px;color:var(--color-text-secondary)">Suggestions are generated automatically from frequently unmapped labels during extraction.</div>
        </div>
      `;
      return;
    }

    _renderSuggestionsTable(main, suggestions, panel);
  } catch (err) {
    main.innerHTML = errorState('Failed to load suggestions: ' + err.message, 'Retry');
    main.querySelector('.error-retry-btn')?.addEventListener('click', () => _loadSuggestions(panel));
  }
}

function _renderSuggestionsTable(main, suggestions, panel) {
  let html = '<div class="card" style="padding:0;overflow:hidden">';
  html += '<div class="table-wrapper" style="border:none;border-radius:0">';
  html += '<table class="data-table"><thead><tr>';
  html += '<th style="text-align:left">Type</th>';
  html += '<th style="text-align:left">Suggested Text</th>';
  html += '<th style="text-align:left">Maps To</th>';
  html += '<th style="text-align:center">Evidence</th>';
  html += '<th style="text-align:left">Status</th>';
  html += '<th style="text-align:center;width:140px">Actions</th>';
  html += '</tr></thead><tbody>';

  for (const s of suggestions) {
    const typeBadge = _suggestionTypeBadge(s.suggestion_type);
    const statusBadge = _suggestionStatusBadge(s.status);
    const isPending = s.status === 'pending';

    html += '<tr>';
    html += `<td>${typeBadge}</td>`;
    html += `<td><span class="text-mono" style="font-size:12px">${esc(s.suggested_text)}</span></td>`;
    html += `<td>${s.canonical_name ? `<span class="text-mono" style="font-size:11px">${esc(s.canonical_name)}</span>` : '<span style="color:var(--color-text-tertiary);font-size:11px">\u2014</span>'}</td>`;
    html += `<td style="text-align:center"><span style="font-family:var(--font-mono);font-size:12px">${s.evidence_count}</span></td>`;
    html += `<td>${statusBadge}</td>`;
    html += '<td style="text-align:center">';
    if (isPending) {
      html += `<button class="btn btn-sm" data-accept-id="${s.id}" style="font-size:10px;padding:3px 10px;margin-right:4px">Accept</button>`;
      html += `<button class="btn btn-sm btn-ghost" data-reject-id="${s.id}" style="font-size:10px;padding:3px 10px">Reject</button>`;
    } else {
      const resolvedInfo = s.resolved_by ? `by ${esc(s.resolved_by)}` : '';
      html += `<span style="font-size:10px;color:var(--color-text-tertiary)">${resolvedInfo}</span>`;
    }
    html += '</td>';
    html += '</tr>';
  }

  html += '</tbody></table></div></div>';
  main.innerHTML = html;

  // Bind accept buttons
  main.querySelectorAll('[data-accept-id]').forEach(btn => {
    const handler = async () => {
      btn.disabled = true;
      btn.textContent = '...';
      try {
        await apiPost(`/api/v1/taxonomy/suggestions/${btn.dataset.acceptId}/accept`, {});
        showToast('Suggestion accepted', 'success');
        await _loadSuggestions(panel);
      } catch (err) {
        showToast('Failed: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Accept';
      }
    };
    btn.addEventListener('click', handler);
    _cleanupFns.push(() => btn.removeEventListener('click', handler));
  });

  // Bind reject buttons
  main.querySelectorAll('[data-reject-id]').forEach(btn => {
    const handler = async () => {
      btn.disabled = true;
      btn.textContent = '...';
      try {
        await apiPost(`/api/v1/taxonomy/suggestions/${btn.dataset.rejectId}/reject`, {});
        showToast('Suggestion rejected', 'info');
        await _loadSuggestions(panel);
      } catch (err) {
        showToast('Failed: ' + err.message, 'error');
        btn.disabled = false;
        btn.textContent = 'Reject';
      }
    };
    btn.addEventListener('click', handler);
    _cleanupFns.push(() => btn.removeEventListener('click', handler));
  });
}

function _suggestionTypeBadge(type) {
  const map = {
    'new_alias': { label: 'New Alias', cls: 'b-blue' },
    'new_item': { label: 'New Item', cls: 'b-ok' },
    'fix_conflict': { label: 'Fix Conflict', cls: 'b-warn' },
  };
  const info = map[type] || { label: type, cls: 'b-gray' };
  return `<span class="badge ${info.cls}" style="font-size:10px">${esc(info.label)}</span>`;
}

function _suggestionStatusBadge(status) {
  const map = {
    'pending': { label: 'Pending', cls: 'b-warn' },
    'accepted': { label: 'Accepted', cls: 'b-ok' },
    'rejected': { label: 'Rejected', cls: 'b-gray' },
  };
  const info = map[status] || { label: status, cls: 'b-gray' };
  return `<span class="badge ${info.cls}" style="font-size:10px">${esc(info.label)}</span>`;
}


// ============================================================================
// CHANGELOG TAB
// ============================================================================

let _changelogFilter = '';

async function _renderChangelogTab(panel) {
  panel.innerHTML = `
    <div class="content-body">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <div style="position:relative;flex:1;max-width:300px">
          <input type="text" id="changelog-filter-input"
            placeholder="Filter by canonical name..."
            style="width:100%;padding:7px 12px;border:0.5px solid var(--color-border-secondary);border-radius:var(--border-radius-md);font-size:12px;font-family:var(--font-mono);background:var(--color-background-primary);color:var(--color-text-primary)">
        </div>
        <div style="font-size:12px;color:var(--color-text-secondary)" id="changelog-count"></div>
      </div>
      <div id="changelog-main">${loadingPlaceholder('Loading changelog...')}</div>
    </div>
  `;

  // Bind filter input
  const input = panel.querySelector('#changelog-filter-input');
  if (input) {
    let timer = null;
    const handler = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        _changelogFilter = input.value.trim();
        _loadChangelog(panel);
      }, DEBOUNCE_MS);
    };
    input.addEventListener('input', handler);
    _cleanupFns.push(() => {
      input.removeEventListener('input', handler);
      if (timer) clearTimeout(timer);
    });
  }

  await _loadChangelog(panel);
}

async function _loadChangelog(panel) {
  const main = panel.querySelector('#changelog-main');
  const countEl = panel.querySelector('#changelog-count');
  if (!main) return;

  main.innerHTML = loadingPlaceholder('Loading changelog...');

  try {
    let url = '/api/v1/taxonomy/changelog?limit=200';
    if (_changelogFilter) url += `&canonical_name=${encodeURIComponent(_changelogFilter)}`;

    const data = await apiGet(url);
    const entries = data.entries || [];

    if (countEl) countEl.textContent = `${entries.length} entr${entries.length !== 1 ? 'ies' : 'y'}`;

    if (entries.length === 0) {
      main.innerHTML = `
        <div class="card" style="text-align:center;padding:2.5rem 1rem">
          <div style="font-size:32px;margin-bottom:8px;opacity:0.3">&#x1F4DD;</div>
          <div style="font-size:14px;font-weight:500;color:var(--color-text-primary);margin-bottom:4px">No changelog entries</div>
          <div style="font-size:12px;color:var(--color-text-secondary)">${_changelogFilter ? 'No changes found for this item.' : 'Changes to taxonomy items (deprecation, alias updates, etc.) will appear here.'}</div>
        </div>
      `;
      return;
    }

    _renderChangelogTable(main, entries);
  } catch (err) {
    main.innerHTML = errorState('Failed to load changelog: ' + err.message, 'Retry');
    main.querySelector('.error-retry-btn')?.addEventListener('click', () => _loadChangelog(panel));
  }
}

function _renderChangelogTable(main, entries) {
  let html = '<div class="card" style="padding:0;overflow:hidden">';
  html += '<div class="table-wrapper" style="border:none;border-radius:0">';
  html += '<table class="data-table"><thead><tr>';
  html += '<th style="text-align:left">Item</th>';
  html += '<th style="text-align:left">Field</th>';
  html += '<th style="text-align:left">Old Value</th>';
  html += '<th style="text-align:left">New Value</th>';
  html += '<th style="text-align:left">Changed By</th>';
  html += '<th style="text-align:left">Version</th>';
  html += '<th style="text-align:left">When</th>';
  html += '</tr></thead><tbody>';

  for (const e of entries) {
    html += '<tr>';
    html += `<td><span class="text-mono" style="font-size:11px">${esc(e.canonical_name)}</span></td>`;
    html += `<td><span style="font-size:12px">${esc(e.field_name)}</span></td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(e.old_value || '\u2014')}</td>`;
    html += `<td style="font-size:11px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(e.new_value || '\u2014')}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary)">${esc(e.changed_by)}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-tertiary)">${e.taxonomy_version ? esc(e.taxonomy_version) : '\u2014'}</td>`;
    html += `<td style="font-size:11px;color:var(--color-text-secondary)">${e.created_at ? esc(timeAgo(e.created_at)) : '\u2014'}</td>`;
    html += '</tr>';
  }

  html += '</tbody></table></div></div>';
  main.innerHTML = html;
}


// ============================================================================
// HELPERS
// ============================================================================

function _formatAliases(aliases) {
  if (!aliases) return '';
  if (Array.isArray(aliases)) {
    return aliases.map(a => {
      if (typeof a === 'object' && a !== null && a.text) return a.text;
      return String(a);
    }).join(', ');
  }
  if (typeof aliases === 'string') {
    try {
      const parsed = JSON.parse(aliases);
      if (Array.isArray(parsed)) return parsed.join(', ');
    } catch { /* not JSON */ }
    return aliases;
  }
  return String(aliases);
}

function _formatValidationRules(rules) {
  if (!rules) return '';
  if (typeof rules === 'string') return rules;
  if (typeof rules === 'object') {
    try {
      return JSON.stringify(rules, null, 2);
    } catch { return ''; }
  }
  return String(rules);
}
