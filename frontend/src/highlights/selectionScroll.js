/**
 * Keeping a text selection alive when the highlight bar is in the way.
 *
 * The bar is fixed to the bottom of the window, so dragging a selection
 * downwards runs the pointer into it. Two things then go wrong: the bar
 * swallows the pointer so the selection stops extending, and because the
 * pointer never reaches the bottom of the window the browser never starts its
 * own auto-scroll. The reader is left unable to select past whatever the bar
 * is covering.
 *
 * The fix has two halves. The bar stops taking pointer events while a drag is
 * in progress (CSS), and this module says how fast to scroll as the pointer
 * approaches the edge of the part of the window that is still visible - which
 * is the top of the bar, not the bottom of the window.
 *
 * Pure so it can be tested without a browser.
 */

// How close to the edge the pointer has to get before the page starts moving.
export const EDGE_MARGIN = 56;
// Pixels per frame at the very edge. ~60fps, so this is about 900px a second:
// fast enough not to feel stuck, slow enough to stop where you meant to.
export const MAX_STEP = 15;

/**
 * Pixels to scroll this frame. Positive scrolls down, negative up, 0 holds.
 *
 * `bottom` is where the usable area ends - the top of the bar when it is open,
 * the bottom of the window when it is not. A pointer past that point (over the
 * bar) scrolls at full speed rather than stopping, because that is exactly the
 * gesture someone makes when they want to keep going.
 */
export function edgeScrollStep(pointerY, { top = 0, bottom } = {}) {
  if (!Number.isFinite(pointerY) || !Number.isFinite(bottom)) return 0;
  // A usable area too small to have two distinct edges cannot steer a scroll.
  if (bottom - top < EDGE_MARGIN) return 0;

  const intoBottom = pointerY - (bottom - EDGE_MARGIN);
  if (intoBottom > 0) return ramp(intoBottom);

  const intoTop = top + EDGE_MARGIN - pointerY;
  if (intoTop > 0) return -ramp(intoTop);

  return 0;
}

function ramp(depth) {
  const share = Math.min(1, depth / EDGE_MARGIN);
  return Math.max(1, Math.ceil(share * MAX_STEP));
}

/**
 * Where the usable area ends: the top of the bar, or the bottom of the window.
 * Takes the measurements rather than reading the DOM, so it is testable too.
 */
export function usableBottom(windowHeight, barHeight = 0) {
  if (!Number.isFinite(windowHeight)) return 0;
  const bar = Number.isFinite(barHeight) ? Math.max(0, barHeight) : 0;
  return Math.max(0, windowHeight - bar);
}
