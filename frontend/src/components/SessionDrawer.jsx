function formatSessionNumber(n) {
  return String(n).padStart(2, "0");
}

export default function SessionDrawer({ open, items, onClose, onSelect }) {
  if (!open) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer-panel" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2>All sessions</h2>
          <button className="icon-btn" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="drawer-list">
          {items.map((item) => (
            <button
              key={item.id}
              className={`drawer-item ${item.completed ? "completed" : ""} ${
                item.is_current ? "current" : ""
              }`}
              onClick={() => onSelect(item.id)}
            >
              <span className="drawer-item-label">Session_{formatSessionNumber(item.session_number)}</span>
              <span className="drawer-item-preview">{item.preview}...</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
