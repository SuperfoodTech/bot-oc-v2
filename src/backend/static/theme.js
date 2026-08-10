(function () {
  const storageKey = 'foodmaster-theme';

  function applyTheme() {
    document.documentElement.dataset.theme = 'light';
    document.documentElement.style.colorScheme = 'light';
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', '#BE1A1A');
  }

  window.toggleTheme = function () {
    localStorage.removeItem(storageKey);
    applyTheme();
  };

  try {
    localStorage.removeItem(storageKey);
  } catch (e) {}

  applyTheme();
  document.addEventListener('DOMContentLoaded', applyTheme);
})();
