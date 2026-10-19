import { useState } from "react";
import { logEvent } from "../api";
import { copyRich } from "../citations/clipboard";
import { STYLES, citation, toHtml, toPlain } from "../citations/format";
import { useSettings } from "../SettingsContext";

const STYLE_NAMES = { apa: "APA 7", mla: "MLA 9", chicago: "Chicago 17" };
const collapse = (text) => String(text).replace(/\s+/g, " ").trim();
const escapeHtml = (text) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/**
 * Copy a highlighted passage with its citation, or the citation alone. The
 * style is the reader's remembered choice. The quote text is never logged.
 */
export default function CiteControl({ book, highlight, bookId }) {
  const { citationStyle, setCitationStyle } = useSettings();
  const [withLink, setWithLink] = useState(false);
  const [message, setMessage] = useState("");

  const link = `${window.location.origin}/read/${bookId}?ms=${highlight.micro_session_id}&h=${highlight.id}`;

  function build(kind) {
    const c = citation(citationStyle, book, highlight);
    const quote = `“${collapse(highlight.quote)}”`;
    let text;
    let html;
    if (kind === "reference") {
      text = toPlain(c.reference);
      html = toHtml(c.reference);
    } else if (kind === "citation") {
      const parts = c.inText || c.footnote;
      text = toPlain(parts);
      html = toHtml(parts);
    } else if (c.inText) {
      text = `${quote} ${toPlain(c.inText)}`;
      html = `<p>${escapeHtml(quote)} ${toHtml(c.inText)}</p>`;
    } else {
      text = `${quote}\n\n${toPlain(c.footnote)}`;
      html = `<p>${escapeHtml(quote)}</p><p>${toHtml(c.footnote)}</p>`;
    }
    if (withLink) {
      text += `\n${link}`;
      html += `<p><a href="${escapeHtml(link)}">${escapeHtml(link)}</a></p>`;
    }
    return { text, html };
  }

  async function copy(kind, done) {
    try {
      const how = await copyRich(build(kind));
      setMessage(how === "plain" ? `${done} (as plain text).` : `${done}.`);
      logEvent("cite_copied", { bookId, style: citationStyle, kind, link: withLink });
    } catch {
      setMessage("Could not copy. Select the text and copy it yourself.");
    }
  }

  return (
    <div className="cite-control" role="group" aria-label="Cite this passage">
      <label className="cite-style">
        <span>Citation style</span>
        <select value={citationStyle} onChange={(e) => setCitationStyle(e.target.value)}>
          {STYLES.map((id) => (
            <option key={id} value={id}>
              {STYLE_NAMES[id]}
            </option>
          ))}
        </select>
      </label>
      <label className="cite-link">
        <input type="checkbox" checked={withLink} onChange={(e) => setWithLink(e.target.checked)} />{" "}
        <span>Include link to this passage</span>
      </label>
      <div className="cite-actions">
        <button type="button" className="btn-secondary" onClick={() => copy("quote", "Copied quote with citation")}>
          Copy quote with citation
        </button>
        <button type="button" className="btn-secondary" onClick={() => copy("citation", "Copied citation")}>
          Copy citation
        </button>
        <button type="button" className="btn-secondary" onClick={() => copy("reference", "Copied reference entry")}>
          Copy reference entry
        </button>
      </div>
      <p role="status" className="cite-status">
        {message}
      </p>
    </div>
  );
}
