import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';

export default function AutocompleteField({ label, value, onChange, placeholder }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!value || value.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    const timeoutId = setTimeout(async () => {
      try {
        const results = await apiFetch('/api/places/autocomplete', {
          method: 'POST',
          body: JSON.stringify({ input: value }),
        });
        setSuggestions(results);
      } catch {
        setSuggestions([]);
      }
    }, 220);
    return () => clearTimeout(timeoutId);
  }, [value]);

  const chooseSuggestion = (suggestion) => {
    onChange({
      text: suggestion.formatted_address ? `${suggestion.name}, ${suggestion.formatted_address}` : suggestion.name,
      place_id: suggestion.place_id || null,
    });
    setOpen(false);
  };

  return (
    <label className="field">
      <span>{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onFocus={() => setOpen(true)}
        onChange={(event) => onChange({ text: event.target.value, place_id: null })}
      />
      {open && suggestions.length > 0 ? (
        <div className="suggestions-popover">
          {suggestions.map((suggestion) => (
            <button
              key={`${suggestion.place_id || suggestion.name}-${suggestion.formatted_address || ''}`}
              className="suggestion-item"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => chooseSuggestion(suggestion)}
            >
              <strong>{suggestion.name}</strong>
              <span>{suggestion.formatted_address || 'Search query'}</span>
            </button>
          ))}
        </div>
      ) : null}
    </label>
  );
}
