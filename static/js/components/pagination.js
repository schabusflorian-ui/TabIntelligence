// Pagination Component

/**
 * Render pagination controls.
 * @param {HTMLElement} container
 * @param {Object} opts
 * @param {number} opts.total - total items
 * @param {number} opts.limit - items per page
 * @param {number} opts.offset - current offset
 * @param {Function} opts.onChange - (newOffset) => void
 */
export function renderPagination(container, opts) {
  const { total, limit, offset, onChange } = opts;
  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  let html = '<div class="pagination">';
  html += `<button ${currentPage <= 1 ? 'disabled' : ''} data-page="${currentPage - 1}">&laquo; Prev</button>`;

  // Show page numbers (max 7 visible)
  const pages = getPageRange(currentPage, totalPages, 7);
  for (const p of pages) {
    if (p === '...') {
      html += '<span class="page-info">...</span>';
    } else {
      html += `<button class="${p === currentPage ? 'active' : ''}" data-page="${p}">${p}</button>`;
    }
  }

  html += `<button ${currentPage >= totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">Next &raquo;</button>`;
  html += `<span class="page-info">${total} items</span>`;
  html += '</div>';

  container.innerHTML = html;

  container.querySelectorAll('button[data-page]').forEach(btn => {
    btn.addEventListener('click', () => {
      const page = parseInt(btn.dataset.page);
      if (page >= 1 && page <= totalPages) {
        onChange((page - 1) * limit);
      }
    });
  });
}

function getPageRange(current, total, maxVisible) {
  if (total <= maxVisible) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages = [];
  pages.push(1);

  let start = Math.max(2, current - 1);
  let end = Math.min(total - 1, current + 1);

  if (current <= 3) { start = 2; end = Math.min(4, total - 1); }
  if (current >= total - 2) { start = Math.max(total - 3, 2); end = total - 1; }

  if (start > 2) pages.push('...');
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < total - 1) pages.push('...');

  pages.push(total);
  return pages;
}
