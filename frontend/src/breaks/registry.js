import ConnectDotsGame from "./games/ConnectDotsGame.jsx";
import MatchingCardsGame from "./games/MatchingCardsGame.jsx";
import MiniSudokuGame from "./games/MiniSudokuGame.jsx";
import OddOneOut from "./games/OddOneOutGame.jsx";
import SlidingTileGame from "./games/SlidingTileGame.jsx";
import WordPlayGame from "./games/WordPlayGame.jsx";
import * as connectDots from "./games/connectDots";
import * as matchingCards from "./games/matchingCards";
import * as miniSudoku from "./games/miniSudoku";
import * as pattern from "./games/pattern";
import * as slidingTile from "./games/slidingTile";
import * as wordPlay from "./games/wordPlay";

// Every game in the break rotation. A game supplies a puzzle generator and a
// component; the shell owns every rule about how long and how it may be played.
// `multiRound` games serve 3-4 short puzzles per break (see rounds.js).
export const GAMES = [
  {
    id: "odd_one_out",
    multiRound: true,
    title: "Odd one out",
    skill: "pattern recognition",
    generate: pattern.generate,
    solve: pattern.solve,
    Component: OddOneOut,
  },
  {
    id: "matching_cards",
    title: "Matching cards",
    skill: "working memory",
    generate: matchingCards.generate,
    solve: matchingCards.solve,
    Component: MatchingCardsGame,
  },
  {
    id: "sliding_tile",
    title: "Sliding tile",
    skill: "spatial planning",
    generate: slidingTile.generate,
    solve: slidingTile.solve,
    Component: SlidingTileGame,
  },
  {
    id: "connect_dots",
    multiRound: true,
    title: "Connect the dots",
    skill: "spatial planning",
    generate: connectDots.generate,
    solve: connectDots.solve,
    Component: ConnectDotsGame,
  },
  {
    id: "mini_sudoku",
    title: "Mini sudoku",
    skill: "logic",
    generate: miniSudoku.generate,
    solve: miniSudoku.solve,
    Component: MiniSudokuGame,
  },
  {
    id: "word_play",
    multiRound: true,
    title: "Word ladder / anagram",
    skill: "verbal",
    generate: wordPlay.generate,
    solve: wordPlay.solve,
    Component: WordPlayGame,
  },
];

export function gameIds() {
  return GAMES.map((g) => g.id);
}

export function getGame(id) {
  return GAMES.find((g) => g.id === id);
}
