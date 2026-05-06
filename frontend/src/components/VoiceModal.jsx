import { CloseIcon, MicIcon, SparkIcon } from './Icons';

function previewText(routeData) {
  if (routeData) {
    return `${routeData.origin} → ${routeData.destination}`;
  }
  return 'Waiting for route';
}

export default function VoiceModal({
  open,
  onClose,
  status,
  voicePhase,
  isConnected,
  routeData,
  onStartVoice,
  onStopVoice,
  audioLevel = 0,
  error,
}) {
  if (!open) {
    return null;
  }

  const preview = previewText(routeData);
  const canStop = voicePhase === 'connecting' || voicePhase === 'listening';
  const isPlanning = voicePhase === 'processing';
  const connectionTone = error ? 'bad' : isConnected ? 'good' : voicePhase === 'connecting' ? 'pending' : 'bad';
  const connectionLabel = connectionTone === 'good' ? 'Live' : connectionTone === 'pending' ? 'Connecting' : 'Offline';
  const buttonLabel = isPlanning ? 'Thinking' : canStop ? 'Stop' : 'Speak';
  const isHearing = voicePhase === 'listening' && audioLevel > 0.08;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="voice-modal voice-modal--voice-only" onClick={(event) => event.stopPropagation()}>
        <div className="modal-frame__top">
          <div className="modal-label">Ask Route Genie</div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <CloseIcon className="icon icon--sm" />
          </button>
        </div>

        <div className="voice-banner">
          <div className="voice-connection">
            <span className={`voice-connection__dot voice-connection__dot--${connectionTone}`} />
            <span>{connectionLabel}</span>
          </div>
          <div className="voice-banner__copy">
            <strong>{status}</strong>
            <span>Live voice</span>
          </div>
          <button
            className={`button button--primary ${isPlanning ? 'button--loading' : ''}`}
            onClick={canStop ? onStopVoice : onStartVoice}
            disabled={isPlanning}
          >
            {isPlanning ? <span className="button-spinner" aria-hidden="true" /> : null}
            {buttonLabel}
          </button>
        </div>

        <div className="voice-stage">
          <div
            className={`voice-stage__pulse ${voicePhase === 'listening' ? 'voice-stage__pulse--active' : ''}`}
            style={{ transform: voicePhase === 'listening' ? `scale(${1.02 + Math.min(audioLevel, 0.22)})` : undefined }}
          >
            <MicIcon className="icon" />
          </div>
          <strong>{voicePhase === 'listening' ? (isHearing ? 'Hearing you' : 'Listening now') : voicePhase === 'processing' ? 'Thinking' : 'Tap speak'}</strong>
          <span>{voicePhase === 'listening' ? 'Pause when done' : voicePhase === 'processing' ? 'Waiting for Genie' : 'Use natural voice prompts'}</span>
        </div>

        {routeData ? (
          <div className="voice-side">
            <div className="voice-preview__card">
              <div className="voice-preview__icon">
                <SparkIcon className="icon icon--sm" />
              </div>
              <div>
                <strong>{preview}</strong>
                <small>{`${routeData.duration_text} • ${routeData.distance_text}`}</small>
              </div>
            </div>
          </div>
        ) : null}

        {error ? <div className="inline-error">{error}</div> : null}
      </div>
    </div>
  );
}
