// Reusable Multi-Select Dropdown Component — Meridian Design System
import { esc } from '../state.js';

/**
 * Create a multi-select dropdown.
 * @param {HTMLElement} container - Element to render into
 * @param {Object} opts
 * @param {Array<{value: string, label: string, group?: string}>} opts.options
 * @param {Set|Array} [opts.selected] - Initially selected values
 * @param {string} [opts.placeholder] - Placeholder text
 * @param {boolean} [opts.multi] - Allow multi-select (default true)
 * @param {boolean} [opts.searchable] - Show search input (default true)
 * @param {Function} [opts.onChange] - Called with Set of selected values
 * @returns {{ getSelected, setSelected, destroy }}
 */
export function createDropdown(container, opts = {}) {
  const {
    options = [],
    placeholder = 'Select...',
    multi = true,
    searchable = true,
    onChange,
  } = opts;

  let selected = new Set(opts.selected || []);
  let isOpen = false;
  let highlightIndex = -1;
  let filteredOptions = [...options];

  function render() {
    const selectedLabels = options
      .filter(o => selected.has(o.value))
      .map(o => o.label);
    const displayText = selectedLabels.length > 0
      ? (selectedLabels.length <= 2 ? selectedLabels.join(', ') : `${selectedLabels.length} selected`)
      : placeholder;

    container.innerHTML = `
      <div class="dd-wrap" style="position:relative">
        <button type="button" class="dd-trigger" style="
          display:flex;align-items:center;justify-content:space-between;gap:8px;
          width:100%;padding:6px 10px;
          background:var(--color-background-primary);
          border:0.5px solid var(--color-border-secondary);
          border-radius:var(--border-radius-md);
          font-size:12.5px;color:var(--color-text-primary);
          cursor:pointer;text-align:left;
        ">
          <span class="dd-text" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(displayText)}</span>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" style="flex-shrink:0;opacity:0.5;transition:transform 0.15s ease;${isOpen ? 'transform:rotate(180deg)' : ''}">
            <polyline points="2,3.5 5,6.5 8,3.5"/>
          </svg>
        </button>
        ${isOpen ? renderDropdownList() : ''}
      </div>
    `;

    // Bind events
    const trigger = container.querySelector('.dd-trigger');
    trigger.addEventListener('click', toggleOpen);

    if (isOpen) {
      bindListEvents();
    }
  }

  function renderDropdownList() {
    let html = `<div class="dd-list" style="
      position:absolute;top:calc(100% + 4px);left:0;right:0;
      background:var(--color-background-primary);
      border:0.5px solid var(--color-border-secondary);
      border-radius:var(--border-radius-md);
      box-shadow:0 4px 12px rgba(0,0,0,0.08);
      z-index:1000;max-height:260px;overflow:hidden;
      display:flex;flex-direction:column;
    ">`;

    if (searchable) {
      html += `<div style="padding:6px 8px;border-bottom:0.5px solid var(--color-border-tertiary)">
        <input type="text" class="dd-search" placeholder="Search..." style="
          width:100%;padding:4px 8px;
          border:0.5px solid var(--color-border-tertiary);
          border-radius:4px;font-size:11.5px;
          background:var(--color-background-primary);
          color:var(--color-text-primary);
        ">
      </div>`;
    }

    if (multi) {
      html += `<div style="padding:4px 8px;border-bottom:0.5px solid var(--color-border-tertiary);display:flex;gap:8px">
        <button type="button" class="dd-select-all" style="font-size:10.5px;color:var(--color-steel);background:none;border:none;cursor:pointer;padding:0">Select All</button>
        <button type="button" class="dd-clear-all" style="font-size:10.5px;color:var(--color-text-secondary);background:none;border:none;cursor:pointer;padding:0">Clear</button>
      </div>`;
    }

    html += '<div class="dd-options" style="overflow-y:auto;max-height:200px;padding:4px 0">';

    let currentGroup = null;
    for (let i = 0; i < filteredOptions.length; i++) {
      const opt = filteredOptions[i];
      if (opt.group && opt.group !== currentGroup) {
        currentGroup = opt.group;
        html += `<div style="padding:4px 10px 2px;font-size:10px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:var(--color-text-tertiary)">${esc(currentGroup)}</div>`;
      }
      const isSelected = selected.has(opt.value);
      const isHighlighted = i === highlightIndex;
      html += `<div class="dd-option${isHighlighted ? ' dd-highlighted' : ''}" data-value="${esc(opt.value)}" data-index="${i}" style="
        display:flex;align-items:center;gap:6px;
        padding:5px 10px;font-size:11.5px;cursor:pointer;
        background:${isHighlighted ? 'var(--color-background-secondary)' : 'transparent'};
        color:var(--color-text-primary);
      ">`;
      if (multi) {
        html += `<span style="
          width:14px;height:14px;border:0.5px solid ${isSelected ? '#1D6B9F' : 'var(--color-border-secondary)'};
          border-radius:3px;display:flex;align-items:center;justify-content:center;flex-shrink:0;
          background:${isSelected ? '#1D6B9F' : 'transparent'};
        ">${isSelected ? '<svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="white" stroke-width="1.5"><polyline points="2,5 4.5,7.5 8,3"/></svg>' : ''}</span>`;
      } else if (isSelected) {
        html += '<span style="color:#1D6B9F;font-size:12px;flex-shrink:0">&#10003;</span>';
      }
      html += `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(opt.label)}</span>`;
      html += '</div>';
    }

    if (filteredOptions.length === 0) {
      html += '<div style="padding:12px 10px;text-align:center;font-size:11.5px;color:var(--color-text-secondary)">No matches</div>';
    }

    html += '</div></div>';
    return html;
  }

  function toggleOpen(e) {
    e.stopPropagation();
    isOpen = !isOpen;
    highlightIndex = -1;
    filteredOptions = [...options];
    render();
    if (isOpen) {
      const search = container.querySelector('.dd-search');
      if (search) search.focus();
    }
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    highlightIndex = -1;
    filteredOptions = [...options];
    render();
  }

  function bindListEvents() {
    // Option click
    container.querySelectorAll('.dd-option').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const val = el.dataset.value;
        if (multi) {
          if (selected.has(val)) selected.delete(val);
          else selected.add(val);
          render();
          if (isOpen) {
            const search = container.querySelector('.dd-search');
            if (search) search.focus();
          }
        } else {
          selected.clear();
          selected.add(val);
          close();
        }
        if (onChange) onChange(new Set(selected));
      });

      el.addEventListener('mouseenter', () => {
        highlightIndex = parseInt(el.dataset.index, 10);
        container.querySelectorAll('.dd-option').forEach(o => {
          o.style.background = o.dataset.index == highlightIndex
            ? 'var(--color-background-secondary)' : 'transparent';
          o.classList.toggle('dd-highlighted', o.dataset.index == highlightIndex);
        });
      });
    });

    // Search
    const search = container.querySelector('.dd-search');
    if (search) {
      search.addEventListener('input', () => {
        const q = search.value.toLowerCase();
        filteredOptions = options.filter(o =>
          o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
        );
        highlightIndex = filteredOptions.length > 0 ? 0 : -1;
        // Re-render options only
        const optionsEl = container.querySelector('.dd-options');
        if (optionsEl) {
          let currentGroup = null;
          let html = '';
          for (let i = 0; i < filteredOptions.length; i++) {
            const opt = filteredOptions[i];
            if (opt.group && opt.group !== currentGroup) {
              currentGroup = opt.group;
              html += `<div style="padding:4px 10px 2px;font-size:10px;font-weight:500;letter-spacing:0.08em;text-transform:uppercase;color:var(--color-text-tertiary)">${esc(currentGroup)}</div>`;
            }
            const isSelected = selected.has(opt.value);
            const isHighlighted = i === highlightIndex;
            html += `<div class="dd-option${isHighlighted ? ' dd-highlighted' : ''}" data-value="${esc(opt.value)}" data-index="${i}" style="
              display:flex;align-items:center;gap:6px;
              padding:5px 10px;font-size:11.5px;cursor:pointer;
              background:${isHighlighted ? 'var(--color-background-secondary)' : 'transparent'};
              color:var(--color-text-primary);
            ">`;
            if (multi) {
              html += `<span style="
                width:14px;height:14px;border:0.5px solid ${isSelected ? '#1D6B9F' : 'var(--color-border-secondary)'};
                border-radius:3px;display:flex;align-items:center;justify-content:center;flex-shrink:0;
                background:${isSelected ? '#1D6B9F' : 'transparent'};
              ">${isSelected ? '<svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="white" stroke-width="1.5"><polyline points="2,5 4.5,7.5 8,3"/></svg>' : ''}</span>`;
            } else if (isSelected) {
              html += '<span style="color:#1D6B9F;font-size:12px;flex-shrink:0">&#10003;</span>';
            }
            html += `<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(opt.label)}</span>`;
            html += '</div>';
          }
          if (filteredOptions.length === 0) {
            html += '<div style="padding:12px 10px;text-align:center;font-size:11.5px;color:var(--color-text-secondary)">No matches</div>';
          }
          optionsEl.innerHTML = html;
          // Rebind option events
          bindOptionEvents();
        }
      });

      search.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (filteredOptions.length > 0) {
            highlightIndex = Math.min(highlightIndex + 1, filteredOptions.length - 1);
            updateHighlight();
          }
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (filteredOptions.length > 0) {
            highlightIndex = Math.max(highlightIndex - 1, 0);
            updateHighlight();
          }
        } else if (e.key === 'Enter') {
          e.preventDefault();
          if (highlightIndex >= 0 && highlightIndex < filteredOptions.length) {
            const val = filteredOptions[highlightIndex].value;
            if (multi) {
              if (selected.has(val)) selected.delete(val);
              else selected.add(val);
              render();
              if (isOpen) {
                const s = container.querySelector('.dd-search');
                if (s) s.focus();
              }
            } else {
              selected.clear();
              selected.add(val);
              close();
            }
            if (onChange) onChange(new Set(selected));
          }
        } else if (e.key === 'Escape') {
          close();
        }
      });
    }

    // Select All / Clear
    const selectAll = container.querySelector('.dd-select-all');
    if (selectAll) {
      selectAll.addEventListener('click', (e) => {
        e.stopPropagation();
        filteredOptions.forEach(o => selected.add(o.value));
        render();
        if (onChange) onChange(new Set(selected));
        if (isOpen) {
          const s = container.querySelector('.dd-search');
          if (s) s.focus();
        }
      });
    }
    const clearAll = container.querySelector('.dd-clear-all');
    if (clearAll) {
      clearAll.addEventListener('click', (e) => {
        e.stopPropagation();
        selected.clear();
        render();
        if (onChange) onChange(new Set(selected));
        if (isOpen) {
          const s = container.querySelector('.dd-search');
          if (s) s.focus();
        }
      });
    }

    // Close on outside click
    setTimeout(() => {
      document.addEventListener('click', docClickHandler);
    }, 0);
  }

  function bindOptionEvents() {
    container.querySelectorAll('.dd-option').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const val = el.dataset.value;
        if (multi) {
          if (selected.has(val)) selected.delete(val);
          else selected.add(val);
          render();
          if (isOpen) {
            const s = container.querySelector('.dd-search');
            if (s) s.focus();
          }
        } else {
          selected.clear();
          selected.add(val);
          close();
        }
        if (onChange) onChange(new Set(selected));
      });

      el.addEventListener('mouseenter', () => {
        highlightIndex = parseInt(el.dataset.index, 10);
        container.querySelectorAll('.dd-option').forEach(o => {
          o.style.background = o.dataset.index == highlightIndex
            ? 'var(--color-background-secondary)' : 'transparent';
        });
      });
    });
  }

  function updateHighlight() {
    container.querySelectorAll('.dd-option').forEach(el => {
      const idx = parseInt(el.dataset.index, 10);
      el.style.background = idx === highlightIndex
        ? 'var(--color-background-secondary)' : 'transparent';
      el.classList.toggle('dd-highlighted', idx === highlightIndex);
      if (idx === highlightIndex) {
        el.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function docClickHandler(e) {
    if (!container.contains(e.target)) {
      close();
      document.removeEventListener('click', docClickHandler);
    }
  }

  render();

  return {
    getSelected() { return new Set(selected); },
    setSelected(vals) {
      selected = new Set(vals);
      render();
    },
    destroy() {
      document.removeEventListener('click', docClickHandler);
      container.innerHTML = '';
    },
  };
}
