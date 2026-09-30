// Applies the stored theme before first paint (no flash). External file so the backend's
// CSP (script-src 'self') is satisfied. Storage may throw (private mode), hence try/catch.
try { var t = localStorage.getItem("tms.theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) {}
