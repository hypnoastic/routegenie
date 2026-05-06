import { MicIcon, SparkIcon } from './Icons';

export default function SearchBar({ onOpen }) {
  return (
    <button className="ask-bar" onClick={onOpen} aria-label="Open Route Genie search">
      <span className="ask-bar__leading">
        <SparkIcon className="icon icon--sm" />
      </span>
      <span className="ask-bar__label">Ask Route Genie</span>
      <span className="ask-bar__trailing">
        <MicIcon className="icon icon--sm" />
      </span>
    </button>
  );
}
