// SPA served by FastAPI's StaticFiles at /ui. StaticFiles has no SPA fallback, so every route is
// prerendered as an empty client-rendered shell (ssr = false) at <route>/index.html. That makes deep
// links and reloads such as /ui/crawl/ resolve to a real file. Data still loads in the browser.
export const ssr = false;
export const prerender = true;
export const trailingSlash = "always";
