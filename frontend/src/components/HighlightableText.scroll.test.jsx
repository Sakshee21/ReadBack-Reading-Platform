// @vitest-environment jsdom
/**
 * The bar is fixed to the bottom of the window, so a selection dragged
 * downwards runs into it. These cover the two halves of getting past it: the
 * bar leaves the pointer path for the duration of the drag, and the page
 * scrolls as the pointer approaches it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import HighlightableText from "./HighlightableText";

vi.mock("../api", () => ({
  api: {
    createHighlight: vi.fn(),
    updateHighlight: vi.fn(),
    deleteHighlight: vi.fn(),
  },
  logEvent: () => {},
}));

const TEXT = "Hello world.\n\nSecond paragraph here.";

function setup() {
  return render(
    <HighlightableText
      text={TEXT}
      bookId={2}
      microSessionId={11}
      enabled
      highlights={[]}
      onChanged={() => {}}
    />
  );
}

function select(node, a, b) {
  const range = document.createRange();
  range.setStart(node, a);
  range.setEnd(node, b);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

const firstText = (container) => container.querySelector("p").firstChild;
const bar = () => screen.getByRole("group", { name: "Highlight" });
const dragging = () => "hlSelecting" in document.body.dataset;

// jsdom has no PointerEvent; a MouseEvent carries the fields the handler reads.
function pointer(type, target, clientY = 0, button = 0) {
  const event = new MouseEvent(type, { bubbles: true, clientY, button });
  act(() => {
    target.dispatchEvent(event);
  });
}

let scrolled;
let frames;

beforeEach(() => {
  scrolled = [];
  frames = [];
  window.scrollBy = (_x, y) => scrolled.push(y);
  // Hold the frames so a test can step the loop deliberately instead of
  // racing it.
  vi.stubGlobal("requestAnimationFrame", (cb) => {
    frames.push(cb);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {});
  window.innerHeight = 800;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete document.body.dataset.hlSelecting;
  window.getSelection().removeAllRanges();
});

const runFrame = () => {
  const next = frames.shift();
  if (next) act(() => next());
};

describe("dragging a selection past the bar", () => {
  it("takes the bar out of the pointer path while the button is down", () => {
    const { container } = setup();
    select(firstText(container), 6, 11);
    expect(dragging()).toBe(false);

    pointer("pointerdown", container.querySelector(".hl-text"), 400);
    expect(dragging()).toBe(true);

    pointer("pointerup", window, 400);
    expect(dragging()).toBe(false);
  });

  it("stays out of the way when the bar opens part-way through a drag", () => {
    // Pressing down clears the old selection, so the bar closes and then
    // reopens as soon as the new selection is non-empty - while the button is
    // still down. From that moment on it is over the text being selected, so
    // it has to still be pass-through.
    const { container } = setup();
    pointer("pointerdown", container.querySelector(".hl-text"), 400);
    expect(dragging()).toBe(true);

    select(firstText(container), 6, 11); // the drag reaches some words
    expect(bar()).toBeTruthy();
    expect(dragging()).toBe(true);

    pointer("pointerup", window, 400);
    expect(dragging()).toBe(false);
  });

  it("puts the bar back after a cancelled drag, not just a finished one", () => {
    const { container } = setup();
    select(firstText(container), 6, 11);
    pointer("pointerdown", container.querySelector(".hl-text"), 400);
    expect(dragging()).toBe(true);

    pointer("pointercancel", window, 400);
    expect(dragging()).toBe(false);
  });

  it("ignores a right-click, which is not a selection drag", () => {
    const { container } = setup();
    select(firstText(container), 6, 11);
    pointer("pointerdown", container.querySelector(".hl-text"), 400, 2);
    expect(dragging()).toBe(false);
  });

  it("clears the attribute when the passage unmounts mid-drag", () => {
    const { container, unmount } = setup();
    select(firstText(container), 6, 11);
    pointer("pointerdown", container.querySelector(".hl-text"), 400);
    expect(dragging()).toBe(true);

    unmount();
    expect(dragging()).toBe(false);
  });

  it("scrolls the page as the pointer nears the bar", () => {
    const { container } = setup();
    select(firstText(container), 6, 11);

    pointer("pointerdown", container.querySelector(".hl-text"), 100);
    runFrame(); // well clear of the edge
    expect(scrolled).toEqual([]);

    pointer("pointermove", window, 795); // down by the bar
    runFrame();
    expect(scrolled.length).toBe(1);
    expect(scrolled[0]).toBeGreaterThan(0);
  });

  it("stops scrolling when the drag ends", () => {
    const { container } = setup();
    select(firstText(container), 6, 11);
    pointer("pointerdown", container.querySelector(".hl-text"), 795);
    runFrame();
    const during = scrolled.length;
    expect(during).toBeGreaterThan(0);

    pointer("pointerup", window, 795);
    runFrame();
    expect(scrolled.length).toBe(during);
  });

  it("does not scroll when there is no bar and no drag", () => {
    const { container } = setup();
    pointer("pointermove", window, 795);
    runFrame();
    expect(scrolled).toEqual([]);
  });

  it("gives up quietly where scrollBy is not implemented", () => {
    window.scrollBy = () => {
      throw new Error("Not implemented");
    };
    const { container } = setup();
    select(firstText(container), 6, 11);
    pointer("pointerdown", container.querySelector(".hl-text"), 795);
    expect(() => runFrame()).not.toThrow();
  });
});

describe("room under the passage", () => {
  it("publishes the measured bar height while the bar is open", () => {
    const { container } = setup();
    expect(document.documentElement.style.getPropertyValue("--hl-bar-height")).toBe("");

    select(firstText(container), 6, 11);
    // jsdom reports 0 for every box, so the value is "0px" here. What matters
    // is that it is published at all, and from a measurement rather than a
    // constant - the CSS falls back until it lands.
    expect(document.documentElement.style.getPropertyValue("--hl-bar-height")).toBe("0px");
  });

  it("takes the height back down when the bar closes", () => {
    const { container, rerender } = setup();
    select(firstText(container), 6, 11);
    expect(document.documentElement.style.getPropertyValue("--hl-bar-height")).toBe("0px");

    rerender(
      <HighlightableText
        text={TEXT}
        bookId={2}
        microSessionId={11}
        enabled={false}
        highlights={[]}
        onChanged={() => {}}
      />
    );
    expect(document.documentElement.style.getPropertyValue("--hl-bar-height")).toBe("");
  });
});

describe("two passages on one page", () => {
  it("only the one with the open bar publishes its height", () => {
    // The research reader renders a passage per chunk. An instance with no
    // bar must not clear the measurement the open one published.
    const props = {
      text: TEXT,
      bookId: 2,
      microSessionId: 11,
      enabled: true,
      highlights: [],
      onChanged: () => {},
    };
    const first = render(<HighlightableText {...props} />);
    render(<HighlightableText {...props} microSessionId={12} />);

    select(first.container.querySelector("p").firstChild, 6, 11);
    expect(document.documentElement.style.getPropertyValue("--hl-bar-height")).toBe("0px");
  });
});

describe("the page height stays put while the selection changes", () => {
  /**
   * The bouncing bug. The padding under the passage is part of the document
   * height, so clearing it shrinks the page and the browser clamps the scroll
   * position upward; putting it back does not restore it. A drag changes the
   * selection many times a second, so doing that per change made the page
   * jump up and down under the pointer.
   */
  it("writes the bar height once, not on every selection change", () => {
    const { container } = setup();
    const style = document.documentElement.style;

    select(firstText(container), 6, 11); // bar opens, height published
    expect(style.getPropertyValue("--hl-bar-height")).toBe("0px");

    const setProperty = vi.spyOn(style, "setProperty");
    const removeProperty = vi.spyOn(style, "removeProperty");

    // What a drag looks like: the same bar, a selection that keeps growing.
    select(firstText(container), 6, 12);
    select(firstText(container), 0, 12);
    select(firstText(container), 0, 5);

    expect(removeProperty).not.toHaveBeenCalledWith("--hl-bar-height");
    expect(setProperty).not.toHaveBeenCalledWith("--hl-bar-height", expect.anything());
    expect(style.getPropertyValue("--hl-bar-height")).toBe("0px");

    setProperty.mockRestore();
    removeProperty.mockRestore();
  });

  it("still gives the room back when the bar closes", () => {
    const { container } = setup();
    select(firstText(container), 6, 11);
    expect(document.documentElement.style.getPropertyValue("--hl-bar-height")).toBe("0px");

    act(() => {
      window.getSelection().removeAllRanges();
      document.dispatchEvent(new Event("selectionchange"));
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.documentElement.style.getPropertyValue("--hl-bar-height")).toBe("");
  });
});

describe("not fighting the browser", () => {
  it("leaves scrolling to the browser once the pointer is below the window", () => {
    const { container } = setup();
    select(firstText(container), 6, 11);

    pointer("pointerdown", container.querySelector(".hl-text"), 795);
    runFrame();
    expect(scrolled.length).toBe(1); // ours, inside the window

    pointer("pointermove", window, 900); // dragged off the bottom edge
    runFrame();
    expect(scrolled.length).toBe(1); // still ours alone - we added nothing

    pointer("pointermove", window, 795); // back inside
    runFrame();
    expect(scrolled.length).toBe(2);
  });
});
