// Global main scripts
// switchTab(tabId): fetches the same URL with ?tab=tabId and replaces the main page content
function switchTab(tabId) {
  const url = new URL(window.location.href);
  url.searchParams.set('tab', tabId);
  fetch(url.toString(), { credentials: 'same-origin' })
    .then(r => r.text())
    .then(html => {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const newMain = doc.querySelector('.main-layout-global > main.page');
      const wrapper = document.querySelector('.main-layout-global > main.page');
      if (newMain && wrapper) {
        wrapper.innerHTML = newMain.innerHTML;
        // update URL and history
        window.history.pushState({}, '', url);
        // re-run any page-specific scripts if needed
        // If this is the salary tab, dynamically load salary_calc.js
        try {
          if (document.querySelector('#salaryForm')) {
            if (!window.__salary_calc_loaded) {
              var s = document.createElement('script');
              s.src = '/static/js/salary_calc.js';
              s.onload = function() { window.__salary_calc_loaded = true; };
              document.body.appendChild(s);
            }
          }
        } catch (e) { console.error(e); }
      }
      // update active tab classes
      document.querySelectorAll('.tabs a').forEach(a => {
        const href = a.getAttribute('href') || '';
        const matches = href.match(/tab=([^&]*)/);
        const t = matches ? matches[1] : null;
        if (t === tabId) a.classList.add('active'); else a.classList.remove('active');
      });
    })
    .catch(err => console.error('Failed to switch tab', err));
}

// Allow back/forward navigation to re-fetch content
window.addEventListener('popstate', function() {
  const url = new URL(window.location.href);
  const tab = url.searchParams.get('tab');
  if (tab) switchTab(tab);
});

// Attach click handlers to tab links to enable AJAX switching
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.tabs a').forEach(a => {
    a.addEventListener('click', function(e) {
      const href = a.getAttribute('href');
      if (!href) return;
      const m = href.match(/tab=([^&]*)/);
      const tab = m ? m[1] : null;
      if (tab) {
        e.preventDefault();
        switchTab(tab);
      }
    });
  });
});
// switchTab is available globally
