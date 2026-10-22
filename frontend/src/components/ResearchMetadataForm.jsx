/**
 * The citation metadata of a research document, editable.
 *
 * Every field is optional and nothing is derived. A field the extractor could
 * not read comes through blank with a note saying so, because an invented year
 * in a citation someone pastes into a paper is worse than an obvious gap.
 */

const FIELDS = [
  { name: "title", label: "Title", type: "text", placeholder: "As printed on the document" },
  {
    name: "authors",
    label: "Authors",
    type: "text",
    placeholder: "A. Reader, B. Writer, and C. Editor",
    hint: "As printed. Use semicolons for Surname, Given order.",
  },
  { name: "year", label: "Year", type: "number", placeholder: "2021" },
  { name: "venue", label: "Journal, conference or publisher", type: "text", placeholder: "" },
  { name: "doi", label: "DOI", type: "text", placeholder: "10.1109/..." },
];

export default function ResearchMetadataForm({
  values,
  onChange,
  disabled = false,
  showMissing = true,
  needsReview = [],
}) {
  return (
    <div className="research-metadata-form">
      {FIELDS.map((field) => {
        const value = values[field.name];
        const empty = value === "" || value === null || value === undefined;
        const review = needsReview.includes(field.name);
        return (
          <label key={field.name} className="research-field">
            <span className="research-field-label">
              {field.label}
              {showMissing && review && !empty && (
                <em className="research-field-review"> — needs review</em>
              )}
              {showMissing && empty && (
                <em className="research-field-missing"> — not found in the document</em>
              )}
            </span>
            <input
              type={field.type}
              value={value ?? ""}
              placeholder={field.placeholder}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  ...values,
                  [field.name]:
                    field.type === "number"
                      ? e.target.value === ""
                        ? ""
                        : Number(e.target.value)
                      : e.target.value,
                })
              }
            />
            {field.hint && <span className="research-field-hint">{field.hint}</span>}
          </label>
        );
      })}

      {"no_date" in values && (
        <label className="research-consent">
          <input
            type="checkbox"
            checked={Boolean(values.no_date)}
            disabled={disabled}
            onChange={(e) => onChange({ ...values, no_date: e.target.checked })}
          />
          <span>
            This document has no date. Tick only if you have checked - it is what
            turns a blank year into a citable &ldquo;n.d.&rdquo; rather than a gap.
          </span>
        </label>
      )}
    </div>
  );
}
