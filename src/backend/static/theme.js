(function () {
  const storageKey = 'foodmaster-theme';

  function getTheme() {
    return localStorage.getItem(storageKey) || 'light';
  }

  function updateControls(theme) {
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.textContent = theme === 'light' ? 'Mode gelap' : 'Mode terang';
      button.setAttribute('aria-pressed', String(theme === 'light'));
      button.setAttribute('title', theme === 'light' ? 'Gunakan mode gelap' : 'Gunakan mode terang');
    });
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#F5F7FA' : '#111827');
    updateControls(theme);
  }

  window.toggleTheme = function () {
    const nextTheme = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    localStorage.setItem(storageKey, nextTheme);
    applyTheme(nextTheme);
  };

  applyTheme(getTheme());
  document.addEventListener('DOMContentLoaded', () => updateControls(getTheme()));
})();
