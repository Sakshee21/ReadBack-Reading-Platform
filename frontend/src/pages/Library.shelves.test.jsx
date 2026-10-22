// @vitest-environment jsdom
/**
 * Shelves on the library page. The properties worth holding: filtering never
 * loses a book, a book can sit on two shelves at once, and the whole thing is
 * usable without a pointer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Library from "./Library";
import { SettingsProvider } from "../SettingsContext";

const api = {
  listBooks: vi.fn(),
  getProgress: vi.fn(),
  getStreak: vi.fn(),
  getNudge: vi.fn(),
  listShelves: vi.fn(),
  createShelf: vi.fn(),
  renameShelf: vi.fn(),
  deleteShelf: vi.fn(),
  addBookToShelf: vi.fn(),
  removeBookFromShelf: vi.fn(),
  deleteBook: vi.fn(),
};

vi.mock("../api", () => ({
  API_URL: "http://test",
  api: new Proxy({}, { get: (_t, name) => (...args) => api[name](...args) }),
  logEvent: () => {},
  uploadBook: vi.fn(),
}));

vi.mock("../AuthContext", () => ({
  useAuth: () => ({ logout: vi.fn(), user: { id: 1, email: "a@b.c" } }),
}));

const BOOKS = [
  { id: 1, title: "Crime and Punishment", author: "Dostoevsky", status: "ready", chapter_count: 40 },
  { id: 2, title: "Pride and Prejudice", author: "Austen", status: "ready", chapter_count: 61 },
  { id: 3, title: "Frankenstein", author: "Shelley", status: "ready", chapter_count: 24 },
];

const shelf = (id, name, bookIds) => ({
  id,
  name,
  position: id,
  book_ids: bookIds,
  book_count: bookIds.length,
});

const mount = () =>
  render(
    <SettingsProvider>
      <MemoryRouter>
        <Library />
      </MemoryRouter>
    </SettingsProvider>
  );

const titles = () =>
  [...document.querySelectorAll(".book-card h3, .book-card.is-unavailable h3")].map(
    (h) => h.textContent
  );

beforeEach(() => {
  localStorage.clear();
  api.listBooks.mockResolvedValue(BOOKS);
  api.getProgress.mockResolvedValue({ progress_pct: 0 });
  api.getStreak.mockResolvedValue({ current_streak: 0, longest_streak: 0 });
  api.getNudge.mockResolvedValue(null);
  api.listShelves.mockResolvedValue([shelf(10, "Crime", [1]), shelf(11, "To read", [2, 3])]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("the shelf picker", () => {
  it("offers All books, each shelf and Unshelved, with counts", async () => {
    mount();
    expect(await screen.findByRole("button", { name: /All books/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Crime/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^To read/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Unshelved/ })).toBeTruthy();
  });

  it("shows every book under All books", async () => {
    mount();
    await screen.findByRole("button", { name: /All books/ });
    expect(titles()).toEqual([
      "Crime and Punishment",
      "Pride and Prejudice",
      "Frankenstein",
    ]);
  });

  it("filters the grid to the chosen shelf", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /^Crime/ }));
    expect(titles()).toEqual(["Crime and Punishment"]);
  });

  it("shows the books that are on no shelf", async () => {
    api.listShelves.mockResolvedValue([shelf(10, "Crime", [1])]);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Unshelved/ }));
    expect(titles()).toEqual(["Pride and Prejudice", "Frankenstein"]);
  });

  it("says so when a shelf is empty", async () => {
    api.listShelves.mockResolvedValue([shelf(10, "Crime", [])]);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /^Crime/ }));
    expect(screen.getByText(/No books on this shelf yet/)).toBeTruthy();
  });

  it("remembers the last shelf for this reader", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /^Crime/ }));
    await waitFor(() => expect(titles()).toEqual(["Crime and Punishment"]));

    cleanup();
    mount();
    await screen.findByRole("button", { name: /All books/ });
    await waitFor(() => expect(titles()).toEqual(["Crime and Punishment"]));
  });
});

describe("grouping by shelf", () => {
  it("shows a section per shelf, and a book on two shelves appears in both", async () => {
    api.listShelves.mockResolvedValue([shelf(10, "Crime", [1]), shelf(11, "To read", [1, 2])]);
    mount();
    fireEvent.click(await screen.findByLabelText("Group by shelf"));

    // Level 2: the book titles are headings too, and one of them is "Crime
    // and Punishment".
    const crime = screen.getByRole("heading", { level: 2, name: /^Crime/ }).closest("section");
    const toRead = screen.getByRole("heading", { level: 2, name: /^To read/ }).closest("section");
    expect(within(crime).getByText("Crime and Punishment")).toBeTruthy();
    expect(within(toRead).getByText("Crime and Punishment")).toBeTruthy();
    expect(within(toRead).getByText("Pride and Prejudice")).toBeTruthy();
  });

  it("gives the unshelved books a section of their own", async () => {
    api.listShelves.mockResolvedValue([shelf(10, "Crime", [1])]);
    mount();
    fireEvent.click(await screen.findByLabelText("Group by shelf"));
    const unshelved = screen
      .getByRole("heading", { level: 2, name: /^Unshelved/ })
      .closest("section");
    expect(within(unshelved).getByText("Frankenstein")).toBeTruthy();
  });
});

describe("making and changing shelves", () => {
  it("creates a shelf from the inline field", async () => {
    api.createShelf.mockResolvedValue(shelf(12, "Romance", []));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "New shelf" }));
    fireEvent.change(screen.getByLabelText("Name for the new shelf"), {
      target: { value: "  Romance  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(api.createShelf).toHaveBeenCalledWith("Romance"));
  });

  it("renames a shelf", async () => {
    api.renameShelf.mockResolvedValue(shelf(10, "Mystery", [1]));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Rename shelf Crime" }));
    fireEvent.change(screen.getByLabelText("Rename shelf Crime"), {
      target: { value: "Mystery" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.renameShelf).toHaveBeenCalledWith(10, "Mystery"));
  });

  it("asks before deleting, and says the books stay", async () => {
    api.deleteShelf.mockResolvedValue(null);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Delete shelf Crime" }));
    expect(screen.getByText(/stay in your library/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(api.deleteShelf).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete shelf Crime" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete shelf" }));
    await waitFor(() => expect(api.deleteShelf).toHaveBeenCalledWith(10));
  });

  it("reports a failure without taking the library down", async () => {
    api.createShelf.mockRejectedValue(new Error("You already have a shelf with that name."));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "New shelf" }));
    fireEvent.change(screen.getByLabelText("Name for the new shelf"), {
      target: { value: "Crime" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "You already have a shelf with that name."
    );
    expect(titles().length).toBe(3); // the books are still there
  });
});

describe("the per-book shelves menu", () => {
  const openMenuFor = async (title) => {
    const button = await screen.findByRole("button", { name: new RegExp(`Shelves for ${title}`) });
    fireEvent.click(button);
    return button;
  };

  it("says which shelves a book is on, in the button name", async () => {
    mount();
    await screen.findByRole("button", { name: /All books/ });
    expect(screen.getByRole("button", { name: /Shelves for Crime and Punishment: on Crime/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Shelves for Frankenstein: on To read/ })).toBeTruthy();
  });

  it("has a checkbox per shelf, ticked where the book sits", async () => {
    mount();
    await openMenuFor("Crime and Punishment");
    const panel = screen.getByRole("group", { name: "Shelves for Crime and Punishment" });
    const boxes = within(panel).getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    expect(boxes[0].checked).toBe(true); // Crime
    expect(boxes[1].checked).toBe(false); // To read
  });

  it("adds a book to a second shelf without taking it off the first", async () => {
    api.addBookToShelf.mockResolvedValue(shelf(11, "To read", [2, 3, 1]));
    mount();
    await openMenuFor("Crime and Punishment");
    const panel = screen.getByRole("group", { name: "Shelves for Crime and Punishment" });
    fireEvent.click(within(panel).getAllByRole("checkbox")[1]);

    await waitFor(() => expect(api.addBookToShelf).toHaveBeenCalledWith(11, 1));
    expect(api.removeBookFromShelf).not.toHaveBeenCalled();
  });

  it("takes a book off a shelf when the box is cleared", async () => {
    api.removeBookFromShelf.mockResolvedValue(shelf(10, "Crime", []));
    mount();
    await openMenuFor("Crime and Punishment");
    const panel = screen.getByRole("group", { name: "Shelves for Crime and Punishment" });
    fireEvent.click(within(panel).getAllByRole("checkbox")[0]);
    await waitFor(() => expect(api.removeBookFromShelf).toHaveBeenCalledWith(10, 1));
  });

  it("makes a new shelf and puts the book on it", async () => {
    api.createShelf.mockResolvedValue(shelf(12, "Russian", []));
    api.addBookToShelf.mockResolvedValue(shelf(12, "Russian", [1]));
    mount();
    await openMenuFor("Crime and Punishment");
    fireEvent.change(screen.getByLabelText("New shelf for Crime and Punishment"), {
      target: { value: "Russian" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(api.createShelf).toHaveBeenCalledWith("Russian"));
    await waitFor(() => expect(api.addBookToShelf).toHaveBeenCalledWith(12, 1));
  });

  it("closes on Escape and gives focus back to the button", async () => {
    mount();
    const button = await openMenuFor("Crime and Punishment");
    const panel = screen.getByRole("group", { name: "Shelves for Crime and Punishment" });
    fireEvent.keyDown(panel, { key: "Escape" });

    expect(
      screen.queryByRole("group", { name: "Shelves for Crime and Punishment" })
    ).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("works with no shelves at all", async () => {
    api.listShelves.mockResolvedValue([]);
    mount();
    await openMenuFor("Crime and Punishment");
    expect(screen.getByText(/No shelves yet/)).toBeTruthy();
  });
});

describe("shelves never get in the way of reading", () => {
  it("every ready book still links to the reader", async () => {
    mount();
    await screen.findByRole("button", { name: /All books/ });
    const links = [...document.querySelectorAll("a.book-card")].map((a) =>
      a.getAttribute("href")
    );
    expect(links).toEqual(["/read/1", "/read/2", "/read/3"]);
  });

  it("the library still loads when shelves fail entirely", async () => {
    api.listShelves.mockRejectedValue(new Error("down"));
    mount();
    await waitFor(() => expect(titles()).toHaveLength(3));
    expect(screen.getByRole("alert").textContent).toMatch(/could not load your shelves/i);
  });
});
