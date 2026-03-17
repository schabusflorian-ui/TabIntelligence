// Taxonomy Browser Page — Meridian Design System
import { apiGet } from '../api.js';
import { esc } from '../state.js';
import { loadingPlaceholder, errorState } from '../components/loading.js';
import { showToast } from '../components/toast.js';
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
    const items = data.items || [];

    if (items.length === 0) {
      main.innerHTML = `<div style="padding:2rem;text-align:center;color:var(--color-text-secondary)">No results for "${esc(query)}"</div>`;
      return;
    }

    _renderSearchResults(items);
  } catch (err) {
    main.innerHTML = errorState('Search failed: ' + err.message, 'Retry');
    main.querySelector('.error-retry-btn')?.addEventListener('click', () => _performSearch(query));
  }
}

function _renderSearchResults(items) {
  const main = document.getElementById('tax-main');
  if (!main) return;

  let html = '<div class="card" style="padding:0;overflow:hidden">';
  html += '<div style="padding:11px 14px;border-bottom:0.5px solid var(--color-border-tertiary)">';
  html += `<span style="font-size:13px;font-weight:500">${items.length} result${items.length !== 1 ? 's' : ''}</span>`;
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

    // data is { parent_canonical: { canonical_name, display_name, category, children: [...] } }
    // Parents are keyed by their canonical_name. Stand-alone items appear as parents with no children.
    const parents = data || {};
    const parentKeys = Object.keys(parents);

    if (parentKeys.length === 0) {
      // Fallback: load flat list
      await _renderFlatCategory(category);
      return;
    }

    _renderHierarchyTable(parents, parentKeys);
  } catch (err) {
    // Fallback to flat list on hierarchy endpoint failure
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
    html += '</div>';
    if (item.display_name) {
      html += `<div style="font-size:13px;color:var(--color-text-secondary);margin-top:4px">${esc(item.display_name)}</div>`;
    }
    html += '</div>';

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
    html += '</div>';

    el.innerHTML = html;

    // Bind close button
    const closeBtn = document.getElementById('tax-detail-close');
    if (closeBtn) {
      const handler = () => _closeDetail();
      closeBtn.addEventListener('click', handler);
      _cleanupFns.push(() => closeBtn.removeEventListener('click', handler));
    }

    // Scroll detail into view
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    if (_detailItem !== canonicalName) return;
    el.innerHTML = `<div class="card" style="margin-top:12px">${errorState('Failed to load item: ' + err.message, 'Retry')}</div>`;
    el.querySelector('.error-retry-btn')?.addEventListener('click', () => _showDetail(canonicalName));
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

// --- Helpers ---

function _formatAliases(aliases) {
  if (!aliases) return '';
  if (Array.isArray(aliases)) return aliases.join(', ');
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
