import { useState } from 'react';

function reorder(items, fromIndex, toIndex) {
  const clone = [...items];
  const [item] = clone.splice(fromIndex, 1);
  clone.splice(toIndex, 0, item);
  return clone.map((stop, index) => ({ ...stop, stop_order: index }));
}

export default function SmartStopsCard({
  routeData,
  editableStops,
  setEditableStops,
  onApplySuggestions,
  onRecomputeStops,
}) {
  const [dragIndex, setDragIndex] = useState(null);

  if (!routeData) {
    return (
      <div className="overlay-card smart-stops-card">
        <p className="eyebrow">Smart stops</p>
        <h3>Suggestions ready when you are</h3>
        <p>Food, fuel, EV charging, scenic breaks, and practical detours appear after a route is planned.</p>
      </div>
    );
  }

  const handleDrop = (dropIndex) => {
    if (dragIndex === null || dragIndex === dropIndex) {
      return;
    }
    setEditableStops((current) => reorder(current, dragIndex, dropIndex));
    setDragIndex(null);
  };

  return (
    <div className="overlay-card smart-stops-card">
      <div className="card-header">
        <div>
          <p className="eyebrow">Smart stops</p>
          <h3>Editable route stops</h3>
        </div>
        <button className="button button--ghost button--small" onClick={onRecomputeStops}>
          Recompute
        </button>
      </div>

      <div className="stops-editor">
        {editableStops.length === 0 ? (
          <div className="empty-mini">No confirmed stops yet. Add a suggested stop below.</div>
        ) : (
          editableStops.map((stop, index) => (
            <div
              key={`${stop.place_id || stop.name}-${index}`}
              className="stop-row"
              draggable
              onDragStart={() => setDragIndex(index)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => handleDrop(index)}
            >
              <span className="stop-handle">⋮⋮</span>
              <div>
                <strong>{stop.name}</strong>
                <span>{stop.formatted_address || stop.address}</span>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="suggested-stop-list">
        <h4>Suggested additions</h4>
        {(routeData.smart_stop_suggestions || []).map((stop) => (
          <button
            key={`suggestion-${stop.place_id || stop.name}`}
            className="suggestion-row"
            onClick={() => onApplySuggestions(stop)}
          >
            <div>
              <strong>{stop.name}</strong>
              <span>{stop.formatted_address}</span>
            </div>
            <small>{stop.types?.[0] || 'Suggestion'}</small>
          </button>
        ))}
      </div>

      <ul className="suggestion-notes">
        {(routeData.suggestion_notes || []).map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}
