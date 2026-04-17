/**
 * CarYaar HR Extensions — Handbook tile injector for the HRMS PWA.
 *
 * The HRMS PWA at /hrms/* hardcodes its Home Quick Links in the Vue
 * source (apps/hrms/hrms/public/frontend/src/views/Home.vue). We
 * cannot patch that from a custom app without rebuilding HRMS. Instead
 * we watch the DOM for the Quick Links list and append our custom
 * tiles — configurable server-side via caryaar_hr_ext.api.get_custom_tiles.
 *
 * Design constraints:
 *  - Must be idempotent — HRMS SPA navigation re-renders Home; we may
 *    run multiple times per page load without duplicating tiles.
 *  - Must survive HRMS frontend upgrades — we match by heading text
 *    ("Quick Links") + role="list" rather than CSS class, so Tailwind
 *    class renames don't break us.
 *  - Must do nothing on non-HRMS routes.
 */

(function () {
  "use strict";

  // Only run on /hrms/* — bail everywhere else so we don't leak a
  // MutationObserver into the desk or portal.
  if (!/^\/hrms(\/|$)/.test(window.location.pathname)) return;

  const SENTINEL_ATTR = "data-caryaar-handbook-tile";
  let cachedTiles = null;
  let cacheFetchedAt = 0;
  const CACHE_TTL_MS = 5 * 60 * 1000; // 5 min

  /**
   * Fetch the tile list from the server. Cached for 5 minutes so we
   * don't spam the API on every SPA route change.
   */
  async function fetchTiles() {
    const now = Date.now();
    if (cachedTiles && now - cacheFetchedAt < CACHE_TTL_MS) {
      return cachedTiles;
    }
    try {
      const resp = await fetch(
        "/api/method/caryaar_hr_ext.api.get_custom_tiles",
        { credentials: "include", headers: { "X-Frappe-CSRF-Token": "None" } },
      );
      if (!resp.ok) return [];
      const data = await resp.json();
      cachedTiles = Array.isArray(data?.message) ? data.message : [];
      cacheFetchedAt = now;
      return cachedTiles;
    } catch (_err) {
      return [];
    }
  }

  /**
   * Find the Quick Links list in the current DOM. The HRMS PWA renders
   * it as a stack of buttons under a heading that reads "Quick Links".
   * We locate the heading, then walk to its nearest sibling/list.
   */
  function findQuickLinksContainer() {
    // Headings in the Vue rendering use <h2>/<div> with visible text.
    const nodes = document.querySelectorAll("h1, h2, h3, div, p, span");
    for (const el of nodes) {
      const txt = (el.textContent || "").trim();
      if (txt === "Quick Links" && el.children.length === 0) {
        // Walk forward to find the list/container that holds the tiles.
        // HRMS wraps the list as a white rounded card below the heading.
        let sib = el.nextElementSibling;
        while (sib) {
          // Accept any container that has at least one clickable row
          // with an arrow (> chevron) — matches all 6 known tiles.
          if (
            sib.querySelector &&
            sib.querySelector("a, button, [role='button']")
          ) {
            return sib;
          }
          sib = sib.nextElementSibling;
        }
        // Fallback: parent's next card
        const parentNext = el.parentElement?.nextElementSibling;
        if (parentNext && parentNext.querySelector("a, button")) {
          return parentNext;
        }
      }
    }
    return null;
  }

  /**
   * Build a tile element that matches the visual style of the
   * existing HRMS tiles. We copy the markup from the first existing
   * tile so we pick up whatever Tailwind classes HRMS is currently
   * using — future-proof against style changes.
   */
  function buildTile(container, tile) {
    const existingTile = container.querySelector("a, button, [role='button']");
    if (!existingTile) return null;

    // Clone the existing tile to get the right wrapper classes, then
    // replace the content. This is the least brittle way to match the
    // current look without hardcoding HRMS's Tailwind classes.
    const clone = existingTile.cloneNode(true);
    clone.setAttribute(SENTINEL_ATTR, "true");

    // Replace the label text — find the largest text-bearing element
    const labelNode = [...clone.querySelectorAll("*")]
      .filter(
        (n) =>
          n.children.length === 0 && (n.textContent || "").trim().length > 2,
      )
      .sort(
        (a, b) => (b.textContent || "").length - (a.textContent || "").length,
      )[0];
    if (labelNode) labelNode.textContent = tile.label;

    // Replace the icon if present — HRMS uses lucide; we keep the
    // existing svg's shape but swap its data-lucide attribute if we
    // can find it. Most HRMS builds use <svg> children — leave as-is
    // to avoid breaking the layout; a label + chevron is enough.

    // Make it an external link if requested
    if (clone.tagName === "A") {
      clone.setAttribute("href", tile.route);
      if (tile.external) {
        clone.setAttribute("target", "_blank");
        clone.setAttribute("rel", "noopener noreferrer");
      } else {
        clone.removeAttribute("target");
      }
    } else {
      // Button — wire a click handler
      clone.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (tile.external) {
          window.open(tile.route, "_blank", "noopener,noreferrer");
        } else {
          window.location.href = tile.route;
        }
      });
    }

    return clone;
  }

  /**
   * Main injection routine. Idempotent — skips if our tile is already
   * in the container.
   */
  async function tryInject() {
    const container = findQuickLinksContainer();
    if (!container) return false;

    const tiles = await fetchTiles();
    if (!tiles.length) return false;

    for (const tile of tiles) {
      // De-dupe by SENTINEL_ATTR + label
      const existing = container.querySelector(
        `[${SENTINEL_ATTR}="true"][data-tile-label="${CSS.escape(tile.label)}"]`,
      );
      if (existing) continue;

      const node = buildTile(container, tile);
      if (!node) continue;
      node.setAttribute("data-tile-label", tile.label);
      container.appendChild(node);
    }
    return true;
  }

  // ─── Boot ──────────────────────────────────────────────────────────
  // We try once on load, then set up a MutationObserver because the
  // HRMS PWA hydrates async — the Quick Links container appears after
  // the Vue app mounts + fetches user state.
  let injected = false;
  let observer = null;

  async function attempt() {
    const ok = await tryInject();
    if (ok) {
      injected = true;
    }
  }

  function startObserver() {
    if (observer) return;
    observer = new MutationObserver(() => {
      // Re-inject every DOM change — the function is idempotent.
      // Throttle by rescheduling at most once per frame.
      if (attempt._scheduled) return;
      attempt._scheduled = true;
      requestAnimationFrame(() => {
        attempt._scheduled = false;
        attempt();
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  // Bail if document.body isn't ready yet (very rare on /hrms but safe)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      attempt();
      startObserver();
    });
  } else {
    attempt();
    startObserver();
  }

  // Re-attempt on SPA route change (Vue Router pushState)
  const _pushState = history.pushState;
  history.pushState = function (...args) {
    _pushState.apply(this, args);
    setTimeout(attempt, 100);
  };
  window.addEventListener("popstate", () => setTimeout(attempt, 100));
})();
