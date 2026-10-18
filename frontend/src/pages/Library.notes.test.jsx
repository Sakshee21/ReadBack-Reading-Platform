// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SettingsProvider } from "../SettingsContext";
import Library from "./Library";

vi.mock("../AuthContext", () => ({ useAuth: () => ({ logout: () => {} }) }));
vi.mock("../api", () => ({
  logEvent: () => {},
  api: {
    getStreak: () => Promise.resolve({ current_streak: 0, longest_streak: 0 }),
    getNudge: () => Promise.resolve(null),
    listBooks: () =>
      Promise.resolve([
        { id: 2, title: "Alice", author: "Carroll", status: "ready", chapter_count: 12, is_user_uploaded: false },
        { id: 9, title: "Converting", author: "Me", status: "processing", chapter_count: 0, is_user_uploaded: true },
      ]),
    getProgress: () => Promise.resolve({ progress_pct: 0 }),
  },
}));

afterEach(cleanup);

describe("Library notes link", () => {
  it("library_card_has_a_notes_link_for_ready_books_only", async () => {
    render(
      <MemoryRouter>
        <SettingsProvider>
          <Library />
        </SettingsProvider>
      </MemoryRouter>
    );
    const link = await screen.findByRole("link", { name: "Notes for Alice" });
    expect(link.getAttribute("href")).toBe("/books/2/notes");
    expect(screen.queryByRole("link", { name: "Notes for Converting" })).toBeNull();
  });
});
