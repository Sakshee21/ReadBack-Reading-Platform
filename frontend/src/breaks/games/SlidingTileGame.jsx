import { useEffect, useRef, useState } from "react";
import { SOLVED, isSolved, move } from "./slidingTile";

const position = (i) => `row ${Math.floor(i / 3) + 1}, column ${(i % 3) + 1}`;

export default function SlidingTileGame({ puzzle, showSolution, locked, onSolved }) {
  const [tiles, setTiles] = useState(puzzle.tiles);
  const shown = showSolution ? SOLVED : tiles;
  const groupRef = useRef(null);
  const focusTileRef = useRef(null);
  const solvedRef = useRef(false);

  // A move swaps the tile's cell with the blank, which unmounts the focused
  // button. Put keyboard focus back on the tile that was just moved.
  useEffect(() => {
    if (focusTileRef.current === null) return;
    groupRef.current?.querySelector(`[data-tile="${focusTileRef.current}"]`)?.focus();
    focusTileRef.current = null;
  }, [tiles]);

  function pick(index) {
    if (locked || showSolution) return;
    const next = move(tiles, index);
    if (next === tiles) return;
    focusTileRef.current = tiles[index];
    setTiles(next);
    if (isSolved(next) && !solvedRef.current) {
      solvedRef.current = true;
      onSolved();
    }
  }

  return (
    <div className="brk-game">
      <p className="brk-instruction">Slide the tiles into order, 1 to 8.</p>
      <div ref={groupRef} className="brk-tiles" role="group" aria-label="Sliding tiles">
        {shown.map((t, i) =>
          t === 0 ? (
            <span
              key={i}
              role="img"
              className="brk-tile brk-tile-blank"
              aria-label={`Empty space, ${position(i)}`}
            />
          ) : (
            <button
              key={i}
              type="button"
              className="brk-tile"
              data-tile={t}
              aria-disabled={locked || showSolution}
              onClick={() => pick(i)}
              aria-label={`Tile ${t}, ${position(i)}`}
            >
              {t}
            </button>
          )
        )}
      </div>
      <p className="brk-feedback" aria-live="polite" />
    </div>
  );
}
