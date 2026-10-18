import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/global.css";
import "./styles/themes.css";
import "./styles/motion.css";
import "./styles/breaks.css";
import "./styles/appearance.css";
import "./styles/highlights.css";
import App from "./App.jsx";
import { applyStoredTheme } from "./theme/appearance";

// Before the first render, so a reload never flashes the default colours.
applyStoredTheme();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
