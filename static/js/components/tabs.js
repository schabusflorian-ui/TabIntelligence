// Tab Component with lazy loading

/**
 * Create a tabbed interface.
 * @param {HTMLElement} container
 * @param {Array<{id, label, render: async (panel) => void}>} tabDefs
 * @param {string} [activeId] - initially active tab id
 */
export function renderTabs(container, tabDefs, activeId) {
  const loadedTabs = new Set();
  activeId = activeId || tabDefs[0]?.id;

  let html = '<div class="tabs" role="tablist">';
  for (const tab of tabDefs) {
    const isActive = tab.id === activeId;
    const cls = isActive ? 'tab-btn active' : 'tab-btn';
    html += `<button class="${cls}" data-tab="${tab.id}" role="tab" aria-selected="${isActive}" aria-controls="tab-${tab.id}">${escapeHtml(tab.label)}</button>`;
  }
  html += '</div>';

  for (const tab of tabDefs) {
    const isActive = tab.id === activeId;
    const cls = isActive ? 'tab-panel active' : 'tab-panel';
    html += `<div class="${cls}" id="tab-${tab.id}" role="tabpanel" ${isActive ? '' : 'aria-hidden="true"'}></div>`;
  }

  container.innerHTML = html;

  // Tab click handlers
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.dataset.tab;
      activateTab(tabId);
    });
  });

  function activateTab(tabId) {
    container.querySelectorAll('.tab-btn').forEach(b => {
      const isActive = b.dataset.tab === tabId;
      b.classList.toggle('active', isActive);
      b.setAttribute('aria-selected', String(isActive));
    });
    container.querySelectorAll('.tab-panel').forEach(p => {
      const isActive = p.id === 'tab-' + tabId;
      p.classList.toggle('active', isActive);
      if (isActive) {
        p.removeAttribute('aria-hidden');
      } else {
        p.setAttribute('aria-hidden', 'true');
      }
    });

    // Lazy load tab content
    const def = tabDefs.find(t => t.id === tabId);
    const panel = container.querySelector('#tab-' + tabId);
    if (def && panel && !loadedTabs.has(tabId)) {
      loadedTabs.add(tabId);
      def.render(panel);
    }
  }

  // Load initial tab
  const def = tabDefs.find(t => t.id === activeId);
  const panel = container.querySelector('#tab-' + activeId);
  if (def && panel) {
    loadedTabs.add(activeId);
    def.render(panel);
  }

  return {
    activateTab,
    reloadTab(tabId) {
      loadedTabs.delete(tabId);
      const panel = container.querySelector('#tab-' + tabId);
      if (panel) panel.innerHTML = '';
      const def = tabDefs.find(t => t.id === tabId);
      if (def && panel) {
        loadedTabs.add(tabId);
        def.render(panel);
      }
    }
  };
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
