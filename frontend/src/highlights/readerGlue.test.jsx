// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act, cleanup } from "@testing-library/react";
import { highlightingEnabled, parseDeepLink, loadInitialPosition, partsOf } from "./readerGlue";
import { useBookHighlights } from "./useBookHighlights";

const listHighlights = vi.fn();
// A plain rejecting function: a rejecting vi.fn leaks an unhandled rejection
// from vitest's own result tracking.
let failing = false;
vi.mock("../api", () => ({
  api: { listHighlights: (...a) => (failing ? Promise.reject(new Error("down")) : listHighlights(...a)) },
}));

afterEach(cleanup);

describe("highlightingEnabled", () => {
  const quiet = {
    rsvpActive: false,
    celebrationActive: false,
    drawerOpen: false,
    settingsOpen: false,
    quizDue: false,
    unstuckPrompt: false,
    burstActive: false,
    countdownActive: false,
    breakPhase: "idle",
  };
  it("on_when_nothing_else_is_going_on", () => {
    expect(highlightingEnabled(quiet)).toBe(true);
  });
  it("off_for_each_overlay_mode_or_break", () => {
    for (const key of [
      "rsvpActive",
      "celebrationActive",
      "drawerOpen",
      "settingsOpen",
      "quizDue",
      "unstuckPrompt",
      "burstActive",
      "countdownActive",
    ]) {
      expect(highlightingEnabled({ ...quiet, [key]: true }), key).toBe(false);
    }
    for (const phase of ["due", "offered", "playing", "ended"])
      expect(highlightingEnabled({ ...quiet, breakPhase: phase }), phase).toBe(false);
  });
});

describe("parseDeepLink", () => {
  it("reads_ms_and_h", () => {
    expect(parseDeepLink("?ms=12&h=5")).toEqual({ ms: 12, h: 5 });
    expect(parseDeepLink("?ms=12")).toEqual({ ms: 12, h: null });
    expect(parseDeepLink("")).toEqual({ ms: null, h: null });
  });
  it("ignores_junk", () => {
    expect(parseDeepLink("?ms=abc&h=-3")).toEqual({ ms: null, h: null });
    expect(parseDeepLink("?ms=0&h=1.5")).toEqual({ ms: null, h: null });
  });
});

describe("loadInitialPosition", () => {
  const apiLike = () => ({
    getReaderPosition: vi.fn().mockResolvedValue({ from: "reader" }),
    jumpToMicroSession: vi.fn(),
  });
  it("peeks_at_the_passage_without_jumping", async () => {
    const a = apiLike();
    expect(await loadInitialPosition(a, "2", 40)).toEqual({ from: "reader" });
    expect(a.getReaderPosition).toHaveBeenCalledWith("2", 40);
    expect(a.jumpToMicroSession).not.toHaveBeenCalled();
  });
  it("falls_back_to_the_saved_position_when_the_peek_fails", async () => {
    const a = apiLike();
    a.getReaderPosition.mockRejectedValueOnce(new Error("404"));
    expect(await loadInitialPosition(a, "2", 40)).toEqual({ from: "reader" });
    expect(a.getReaderPosition).toHaveBeenLastCalledWith("2");
  });
  it("uses_the_saved_position_without_a_micro_session", async () => {
    const a = apiLike();
    expect(await loadInitialPosition(a, "2", null)).toEqual({ from: "reader" });
    expect(a.getReaderPosition).toHaveBeenCalledWith("2");
  });
});

describe("partsOf", () => {
  it("uses_the_parts_the_server_sent", () => {
    const ms = { id: 1, text: "a\n\nb", parts: [{ id: 1, text: "a" }, { id: 2, text: "b" }] };
    expect(partsOf(ms)).toEqual(ms.parts);
  });
  it("falls_back_to_the_whole_text_as_one_part", () => {
    expect(partsOf({ id: 5, text: "hello" })).toEqual([{ id: 5, text: "hello" }]);
    expect(partsOf({ id: 5, text: "hello", parts: [] })).toEqual([{ id: 5, text: "hello" }]);
  });
});

describe("useBookHighlights", () => {
  beforeEach(() => {
    listHighlights.mockReset();
    failing = false;
  });

  it("loads_the_books_highlights_and_reloads_when_the_key_changes", async () => {
    listHighlights.mockResolvedValueOnce([{ id: 1 }]).mockResolvedValueOnce([{ id: 2 }]);
    const { result, rerender } = renderHook(({ k }) => useBookHighlights("2", k), { initialProps: { k: 10 } });
    await waitFor(() => expect(result.current.highlights).toEqual([{ id: 1 }]));
    rerender({ k: 11 });
    await waitFor(() => expect(result.current.highlights).toEqual([{ id: 2 }]));
    expect(listHighlights).toHaveBeenCalledWith("2");
  });

  it("a_failed_load_gives_an_empty_list_and_does_not_throw", async () => {
    failing = true;
    const { result } = renderHook(() => useBookHighlights("2", 10));
    await act(async () => {});
    expect(result.current.highlights).toEqual([]);
  });

  it("does_nothing_until_there_is_a_key", () => {
    renderHook(() => useBookHighlights("2", null));
    expect(listHighlights).not.toHaveBeenCalled();
  });

  it("replacing_one_parts_highlights_keeps_the_others", async () => {
    listHighlights.mockResolvedValue([
      { id: 1, micro_session_id: 10, start: 0 },
      { id: 2, micro_session_id: 11, start: 0 },
    ]);
    const { result } = renderHook(() => useBookHighlights("2", 10));
    await waitFor(() => expect(result.current.highlights).toHaveLength(2));
    act(() => result.current.replaceForPart(10, [{ id: 3, micro_session_id: 10, start: 0 }]));
    expect(result.current.highlights.map((h) => h.id).sort()).toEqual([2, 3]);
  });

  it("a_late_response_for_an_old_key_is_ignored", async () => {
    let resolveFirst;
    listHighlights
      .mockImplementationOnce(() => new Promise((r) => (resolveFirst = r)))
      .mockResolvedValueOnce([{ id: 2 }]);
    const { result, rerender } = renderHook(({ k }) => useBookHighlights("2", k), { initialProps: { k: 10 } });
    rerender({ k: 11 });
    await waitFor(() => expect(result.current.highlights).toEqual([{ id: 2 }]));
    await act(async () => resolveFirst([{ id: 1 }]));
    expect(result.current.highlights).toEqual([{ id: 2 }]);
  });

  it("a_highlight_made_while_the_list_is_loading_is_not_lost", async () => {
    let resolveFirst;
    listHighlights
      .mockImplementationOnce(() => new Promise((r) => (resolveFirst = r)))
      .mockResolvedValueOnce([{ id: 1, micro_session_id: 10, start: 0 }, { id: 9, micro_session_id: 10, start: 20 }]);
    const { result } = renderHook(() => useBookHighlights("2", 10));
    // the reader highlights something before the first response arrives
    act(() => result.current.replaceForPart(10, [{ id: 9, micro_session_id: 10, start: 20 }]));
    await act(async () => resolveFirst([{ id: 1, micro_session_id: 10, start: 0 }])); // older, misses id 9
    await waitFor(() => expect(result.current.highlights.map((h) => h.id).sort()).toEqual([1, 9]));
    expect(listHighlights).toHaveBeenCalledTimes(2);
  });
});
