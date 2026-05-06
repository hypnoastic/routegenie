import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, getWsBaseUrl } from '../lib/api';
import AuthModal from './AuthModal';
import Header from './Header';
import MapCanvas from './MapCanvas';
import RouteSummaryCard from './RouteSummaryCard';
import SearchBar from './SearchBar';
import Sidebar from './Sidebar';
import VoiceModal from './VoiceModal';

const DUMMY_TRIP_ROUTE = {
  origin: 'India Gate',
  destination: 'Connaught Place',
  travel_mode: 'DRIVE',
  distance_text: '5.8 km',
  duration_text: '18 min',
  duration_minutes: 18,
  arrival_time: null,
  polyline: null,
  legs: [],
  stops: [
    {
      name: 'Khan Market Coffee',
      formatted_address: 'Khan Market, New Delhi',
      address: 'Khan Market, New Delhi',
      latitude: 28.6009,
      longitude: 77.2266,
      types: ['cafe'],
      source: 'text_search',
    },
  ],
  smart_stop_suggestions: [
    {
      name: 'National Stadium Fuel',
      formatted_address: 'Pragati Maidan, New Delhi',
      address: 'Pragati Maidan, New Delhi',
      latitude: 28.6115,
      longitude: 77.241,
      types: ['gas_station'],
      source: 'text_search',
    },
  ],
  comparison_options: [
    { id: 'route-0', label: 'Fastest', distance_text: '5.8 km', duration_text: '18 min', polyline: null },
    { id: 'route-1', label: 'Scenic', distance_text: '6.4 km', duration_text: '22 min', polyline: null },
  ],
  why_this_route: '',
  route_summary: 'Fastest route',
  confirmed_route_data: {},
  suggestion_notes: [],
  saved_trip_id: null,
};

const DUMMY_CONTEXT = {
  user: {
    id: '00000000-0000-0000-0000-000000000001',
    name: 'Dev Traveler',
    email: 'dev@routegenie.local',
    avatar_url: null,
  },
  preferences: {
    preferred_travel_mode: 'DRIVE',
    avoid_tolls: false,
    avoid_highways: false,
    max_extra_minutes: 20,
    safety_mode: true,
    personalization_enabled: true,
    interests_json: { cafes: 3, scenic: 2 },
  },
  recent_trips: [
    {
      id: '00000000-0000-0000-0000-000000000101',
      title: 'Evening coffee run',
      origin_text: 'India Gate',
      destination_text: 'Connaught Place',
      route_summary: 'Fastest route',
      route_payload_json: DUMMY_TRIP_ROUTE,
      travel_mode: 'DRIVE',
      constraints_json: { avoid_tolls: false, avoid_highways: false, max_extra_minutes: 20, safety_mode: true },
      why_this_route: '',
      share_slug: null,
      created_at: '2026-05-05T08:20:00Z',
      updated_at: '2026-05-05T08:20:00Z',
      stops: [],
    },
    {
      id: '00000000-0000-0000-0000-000000000102',
      title: 'Airport pickup',
      origin_text: 'Vasant Vihar',
      destination_text: 'IGI Airport',
      route_summary: 'Safer route',
      route_payload_json: {
        ...DUMMY_TRIP_ROUTE,
        origin: 'Vasant Vihar',
        destination: 'IGI Airport',
        duration_text: '26 min',
        distance_text: '12.1 km',
        comparison_options: [{ id: 'route-0', label: 'Safer', distance_text: '12.1 km', duration_text: '26 min', polyline: null }],
      },
      travel_mode: 'DRIVE',
      constraints_json: { avoid_tolls: false, avoid_highways: false, max_extra_minutes: 10, safety_mode: true },
      why_this_route: '',
      share_slug: null,
      created_at: '2026-05-04T19:10:00Z',
      updated_at: '2026-05-04T19:10:00Z',
      stops: [],
    },
  ],
  recent_searches: [
    {
      id: '00000000-0000-0000-0000-000000000201',
      query_text: 'Add a cafe on the way',
      transcript: 'Add a cafe on the way',
      gemini_response: null,
      route_payload_json: DUMMY_TRIP_ROUTE,
      created_at: '2026-05-05T08:22:00Z',
    },
    {
      id: '00000000-0000-0000-0000-000000000202',
      query_text: 'Safer airport route',
      transcript: 'Safer airport route',
      gemini_response: null,
      route_payload_json: {
        ...DUMMY_TRIP_ROUTE,
        origin: 'Vasant Vihar',
        destination: 'IGI Airport',
        duration_text: '26 min',
        distance_text: '12.1 km',
        comparison_options: [{ id: 'route-0', label: 'Safer', distance_text: '12.1 km', duration_text: '26 min', polyline: null }],
      },
      created_at: '2026-05-04T19:12:00Z',
    },
  ],
};

function plannerFromTrip(trip) {
  return {
    queryText: trip.title,
    origin: { text: trip.origin_text, place_id: null },
    destination: { text: trip.destination_text, place_id: null },
    travelMode: trip.travel_mode || 'DRIVE',
    constraints: trip.constraints_json || {
      avoid_tolls: false,
      avoid_highways: false,
      max_extra_minutes: 20,
      safety_mode: false,
    },
  };
}

function plannerFromRoute(routeData, queryText = '') {
  return {
    queryText,
    origin: { text: routeData?.origin || '', place_id: null },
    destination: { text: routeData?.destination || '', place_id: null },
    travelMode: routeData?.travel_mode || 'DRIVE',
    constraints: {
      avoid_tolls: false,
      avoid_highways: false,
      max_extra_minutes: 20,
      safety_mode: false,
    },
  };
}

function cloneDummyContext() {
  return JSON.parse(JSON.stringify(DUMMY_CONTEXT));
}

export default function HomePage() {
  const dummyEnabled = import.meta.env.DEV && import.meta.env.VITE_ENABLE_DUMMY_AUTH === 'true';
  const [appState, setAppState] = useState({ user: null, preferences: null, recent_trips: [], recent_searches: [] });
  const [sessionMode, setSessionMode] = useState('guest');
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [authError, setAuthError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [status, setStatus] = useState('Ready');
  const [voicePhase, setVoicePhase] = useState('idle');
  const [voiceConnected, setVoiceConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [plannerError, setPlannerError] = useState('');
  const [routeData, setRouteData] = useState(null);
  const [activeComparisonId, setActiveComparisonId] = useState('route-0');
  const [transcript, setTranscript] = useState([]);
  const [saveLoading, setSaveLoading] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [configIssues, setConfigIssues] = useState([]);
  const [plannerState, setPlannerState] = useState({
    queryText: '',
    origin: { text: '', place_id: null },
    destination: { text: '', place_id: null },
    travelMode: 'DRIVE',
    constraints: {
      avoid_tolls: false,
      avoid_highways: false,
      max_extra_minutes: 20,
      safety_mode: false,
    },
  });

  const wsRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);
  const outputGainRef = useRef(null);
  const liveReadyPromiseRef = useRef(null);
  const liveReadyResolveRef = useRef(null);
  const liveReadyRejectRef = useRef(null);
  const liveReadyRef = useRef(false);
  const liveKeepaliveRef = useRef(null);
  const hadSpeechRef = useRef(false);
  const silenceStartedRef = useRef(null);
  const audioEndSentRef = useRef(false);
  const audioChunksSentRef = useRef(0);
  const audioWatchdogRef = useRef(null);
  const audioEnhancerRef = useRef(null);
  const lastAudioLevelUpdateRef = useRef(0);
  const routeResolvedRef = useRef(false);
  const routeAudioReceivedRef = useRef(false);
  const modalCloseTimerRef = useRef(null);

  const isLoggedIn = Boolean(appState.user);
  const isDummySession = sessionMode === 'dummy';

  const refreshMe = useCallback(async () => {
    if (isDummySession) {
      return;
    }
    const nextIssues = [];
    try {
      const me = await apiFetch('/api/me');
      setAppState(me);
      setSessionMode(me.user ? 'real' : 'guest');
    } catch (error) {
      setAppState((current) => ({ ...current, user: null, preferences: null, recent_trips: [], recent_searches: [] }));
      setSessionMode('guest');
      if (!String(error.message || '').toLowerCase().includes('not authenticated')) {
        nextIssues.push('Backend offline');
      }
    }

    try {
      const health = await apiFetch('/health');
      nextIssues.push(...(health.missing_config || []));
    } catch {
      if (!nextIssues.includes('Backend offline')) {
        nextIssues.push('Backend offline');
      }
    }

    setConfigIssues(nextIssues);
  }, [isDummySession]);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  const openAuth = (mode = 'login') => {
    setAuthMode(mode);
    setAuthError('');
    setAuthOpen(true);
  };

  const handleAuthSubmit = async (mode, form) => {
    setAuthLoading(true);
    setAuthError('');
    try {
      const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/signup';
      await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify(form),
      });
      setAuthOpen(false);
      await refreshMe();
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleGoogleAuth = async (credential) => {
    setAuthLoading(true);
    setAuthError('');
    try {
      await apiFetch('/api/auth/google', {
        method: 'POST',
        body: JSON.stringify({ credential }),
      });
      setAuthOpen(false);
      await refreshMe();
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleDummyLogin = () => {
    const dummyState = cloneDummyContext();
    setAppState(dummyState);
    setSessionMode('dummy');
    setAuthOpen(false);
    setAuthError('');
    setRouteData(dummyState.recent_trips[0].route_payload_json);
    setPlannerState(plannerFromTrip(dummyState.recent_trips[0]));
    setActiveComparisonId(dummyState.recent_trips[0].route_payload_json.comparison_options?.[0]?.id || 'route-0');
  };

  const handleLogout = async () => {
    if (isDummySession) {
      setSessionMode('guest');
      setAppState({ user: null, preferences: null, recent_trips: [], recent_searches: [] });
      setRouteData(null);
      setPlannerState(plannerFromRoute(null));
      return;
    }
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // Keep guest UI even if logout request fails.
    }
    setSessionMode('guest');
    setAppState({ user: null, preferences: null, recent_trips: [], recent_searches: [] });
    setRouteData(null);
    setPlannerState(plannerFromRoute(null));
  };

  const handleUpdatePreferences = async (patch) => {
    if (isDummySession) {
      setAppState((current) => ({
        ...current,
        preferences: {
          ...current.preferences,
          ...patch,
        },
      }));
      return;
    }
    const preferences = await apiFetch('/api/me/preferences', {
      method: 'PUT',
      body: JSON.stringify(patch),
    });
    setAppState((current) => ({ ...current, preferences }));
  };

  const connectVoiceSession = async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN && liveReadyRef.current) {
      return;
    }
    if (liveReadyPromiseRef.current) {
      return liveReadyPromiseRef.current;
    }
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close();
      wsRef.current = null;
    }
    liveReadyRef.current = false;

    liveReadyPromiseRef.current = new Promise((resolve, reject) => {
      liveReadyResolveRef.current = resolve;
      liveReadyRejectRef.current = reject;
    });

    try {
      const sessionInfo = await apiFetch('/api/gemini/live-session', { method: 'POST' });
      if (sessionInfo.missing_config?.length) {
        setPlannerError(sessionInfo.missing_config.join(', '));
      }
      const ws = new WebSocket(`${getWsBaseUrl()}/ws/live`);
      wsRef.current = ws;

      ws.onopen = () => {
        setVoicePhase('connecting');
        setStatus('Connecting');
      };

      ws.onmessage = async (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'session_ready') {
          liveReadyRef.current = true;
          setVoiceConnected(true);
          setVoicePhase('ready');
          setStatus('Live');
          liveReadyResolveRef.current?.(message.data);
          liveReadyPromiseRef.current = null;
        }
        if (message.type === 'audio') {
          if (routeResolvedRef.current) {
            routeAudioReceivedRef.current = true;
          }
          setStatus('Speaking');
          await playAudioChunk(message.data);
        }
        if (message.type === 'assistant_text') {
          setTranscript((current) => [...current, { role: 'assistant', text: message.text, final: true }]);
        }
        if (message.type === 'transcript') {
          setTranscript((current) => [...current, message]);
        }
        if (message.type === 'route') {
          routeResolvedRef.current = true;
          stopAudioCapture();
          setRouteData(message.data);
          setActiveComparisonId(message.data.comparison_options?.[0]?.id || 'route-0');
          setPlannerState((current) => plannerFromRoute(message.data, current.queryText));
          setStatus('Route ready');
          setVoicePhase('ready');
          await refreshMe();
          closeAfterLiveAudio(7000);
        }
        if (message.type === 'route_audio_unavailable') {
          if (routeResolvedRef.current) {
            closeAfterLiveAudio(300);
          }
        }
        if (message.type === 'turn_complete') {
          if (routeResolvedRef.current) {
            closeAfterLiveAudio(routeAudioReceivedRef.current ? 900 : 300);
          } else {
            setVoicePhase('ready');
            setStatus('Live');
          }
        }
        if (message.type === 'error') {
          setPlannerError(message.detail);
          setVoicePhase('error');
          setVoiceConnected(false);
          liveReadyRef.current = false;
          liveReadyRejectRef.current?.(new Error(message.detail));
          liveReadyPromiseRef.current = null;
        }
      };

      ws.onerror = () => {
        stopAudioCapture();
        setPlannerError('Live unavailable');
        setVoicePhase('error');
        setVoiceConnected(false);
        liveReadyRef.current = false;
        liveReadyRejectRef.current?.(new Error('Live unavailable'));
        liveReadyPromiseRef.current = null;
      };

      ws.onclose = () => {
        stopAudioCapture();
        liveReadyRejectRef.current?.(new Error('Live closed'));
        liveReadyPromiseRef.current = null;
        liveReadyRef.current = false;
        setVoiceConnected(false);
        setVoicePhase('idle');
      };
    } catch (error) {
      setPlannerError(error.message);
      liveReadyRef.current = false;
      liveReadyRejectRef.current?.(error);
      liveReadyPromiseRef.current = null;
    }
    return liveReadyPromiseRef.current;
  };

  const stopAudioCapture = () => {
    if (liveKeepaliveRef.current) {
      window.clearInterval(liveKeepaliveRef.current);
      liveKeepaliveRef.current = null;
    }
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (outputGainRef.current) {
      outputGainRef.current.disconnect();
      outputGainRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (audioWatchdogRef.current) {
      window.clearTimeout(audioWatchdogRef.current);
      audioWatchdogRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setIsListening(false);
    setAudioLevel(0);
  };

  const closeLiveSocket = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      wsRef.current.close(1000, 'route_ready');
    }
    wsRef.current = null;
    liveReadyRef.current = false;
  };

  const closeAfterLiveAudio = (delay = 2600) => {
    if (modalCloseTimerRef.current) {
      window.clearTimeout(modalCloseTimerRef.current);
    }
    modalCloseTimerRef.current = window.setTimeout(() => {
      setVoiceOpen(false);
      closeLiveSocket();
    }, delay);
  };

  const sendEndAudio = () => {
    if (audioEndSentRef.current) {
      return;
    }
    audioEndSentRef.current = true;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_audio' }));
    }
    stopAudioCapture();
    setVoicePhase('ready');
    setStatus('Live');
  };

  const startVoice = async () => {
    setPlannerError('');
    setTranscript([]);
    setVoiceConnected(false);
    setVoicePhase('connecting');
    setStatus('Connecting');
    hadSpeechRef.current = false;
    silenceStartedRef.current = null;
    audioEndSentRef.current = false;
    audioChunksSentRef.current = 0;
    audioEnhancerRef.current = null;
    routeResolvedRef.current = false;
    routeAudioReceivedRef.current = false;
    if (modalCloseTimerRef.current) {
      window.clearTimeout(modalCloseTimerRef.current);
      modalCloseTimerRef.current = null;
    }

    try {
      await connectVoiceSession();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: { ideal: 1 },
          sampleRate: { ideal: 48000 },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      await audioContextRef.current.resume();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      const outputGain = audioContextRef.current.createGain();
      outputGain.gain.value = 0.00001;
      sourceRef.current = source;
      outputGainRef.current = outputGain;
      audioEnhancerRef.current = createAudioEnhancerState(audioContextRef.current.sampleRate);
      audioWatchdogRef.current = window.setTimeout(() => {
        if (audioChunksSentRef.current === 0 && voicePhase !== 'error') {
          setPlannerError('Microphone stream started, but no PCM audio chunks were produced. Try Chrome and check microphone permissions.');
          setVoicePhase('error');
          setStatus('Mic blocked');
          stopAudioCapture();
        }
      }, 1800);
      const handlePcmInput = (input) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
          return;
        }
        audioChunksSentRef.current += 1;
        if (audioChunksSentRef.current === 1 && audioWatchdogRef.current) {
          window.clearTimeout(audioWatchdogRef.current);
          audioWatchdogRef.current = null;
        }
        const enhancedInput = enhanceSpeechSamples(input, audioEnhancerRef.current);
        const rms = calculateRms(enhancedInput);
        const now = performance.now();
        if (now - lastAudioLevelUpdateRef.current > 120) {
          setAudioLevel(Math.min(1, rms * 16));
          lastAudioLevelUpdateRef.current = now;
        }
        if (rms > 0.006) {
          hadSpeechRef.current = true;
          silenceStartedRef.current = null;
          setStatus('Hearing');
        } else if (hadSpeechRef.current) {
          if (silenceStartedRef.current === null) {
            silenceStartedRef.current = now;
          }
          if (now - silenceStartedRef.current > 1300) {
            sendEndAudio();
            return;
          }
        }
        wsRef.current.send(
          JSON.stringify({
            type: 'audio',
            data: floatToPcm16Base64(enhancedInput, audioContextRef.current.sampleRate),
          }),
        );
      };
      let processor;
      if (audioContextRef.current.audioWorklet) {
        const workletUrl = URL.createObjectURL(
          new Blob(
            [
              `
                class RouteGenieMicProcessor extends AudioWorkletProcessor {
                  process(inputs) {
                    const input = inputs[0] && inputs[0][0];
                    if (input) {
                      const chunk = new Float32Array(input);
                      this.port.postMessage(chunk, [chunk.buffer]);
                    }
                    return true;
                  }
                }
                registerProcessor('route-genie-mic-processor', RouteGenieMicProcessor);
              `,
            ],
            { type: 'application/javascript' },
          ),
        );
        try {
          await audioContextRef.current.audioWorklet.addModule(workletUrl);
          processor = new AudioWorkletNode(audioContextRef.current, 'route-genie-mic-processor', {
            numberOfInputs: 1,
            numberOfOutputs: 1,
            outputChannelCount: [1],
          });
          processor.port.onmessage = (event) => handlePcmInput(event.data);
        } finally {
          URL.revokeObjectURL(workletUrl);
        }
      } else {
        processor = audioContextRef.current.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (event) => handlePcmInput(event.inputBuffer.getChannelData(0));
      }
      source.connect(processor);
      processor.connect(outputGain);
      outputGain.connect(audioContextRef.current.destination);
      processorRef.current = processor;
      setIsListening(true);
      setVoiceConnected(true);
      setVoicePhase('listening');
      setStatus('Listening');
    } catch (error) {
      setPlannerError(error.message);
      setIsListening(false);
      setVoiceConnected(false);
      setVoicePhase('error');
      setStatus('Ready');
    }
  };

  const stopVoice = () => {
    sendEndAudio();
  };

  const saveTrip = async () => {
    if (!routeData) {
      return null;
    }
    if (!isLoggedIn) {
      openAuth('signup');
      return null;
    }

    if (isDummySession) {
      const tripId = `dev-trip-${Date.now()}`;
      const newTrip = {
        id: tripId,
        title: plannerState.queryText || `${routeData.origin} to ${routeData.destination}`,
        origin_text: routeData.origin,
        destination_text: routeData.destination,
        route_summary: routeData.route_summary,
        route_payload_json: routeData,
        travel_mode: routeData.travel_mode,
        constraints_json: plannerState.constraints,
        why_this_route: routeData.why_this_route,
        share_slug: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        stops: [],
      };
      setAppState((current) => ({ ...current, recent_trips: [newTrip, ...current.recent_trips] }));
      setRouteData((current) => ({ ...current, saved_trip_id: tripId }));
      setStatus('Saved');
      return tripId;
    }

    setSaveLoading(true);
    try {
      const trip = await apiFetch('/api/trips', {
        method: 'POST',
        body: JSON.stringify({
          title: plannerState.queryText || `${routeData.origin} to ${routeData.destination}`,
          origin_text: routeData.origin,
          destination_text: routeData.destination,
          route_summary: routeData.route_summary,
          route_payload_json: routeData,
          travel_mode: routeData.travel_mode,
          constraints_json: plannerState.constraints,
          why_this_route: routeData.why_this_route,
          stops: [],
        }),
      });
      setRouteData((current) => ({ ...current, saved_trip_id: trip.id }));
      await refreshMe();
      return trip.id;
    } catch (error) {
      setPlannerError(error.message);
      return null;
    } finally {
      setSaveLoading(false);
    }
  };

  const shareTrip = async () => {
    if (!routeData) {
      return;
    }
    if (!isLoggedIn) {
      openAuth('login');
      return;
    }

    if (isDummySession) {
      const link = `${window.location.origin}/share/dev-preview`;
      await navigator.clipboard.writeText(link);
      setStatus('Dev link copied');
      return;
    }

    setShareLoading(true);
    try {
      let tripId = routeData.saved_trip_id;
      if (!tripId) {
        tripId = await saveTrip();
      }
      if (!tripId) {
        return;
      }
      const share = await apiFetch(`/api/trips/${tripId}/share`, { method: 'POST' });
      const link = share.share_url || `${window.location.origin}/share/${share.share_slug}`;
      await navigator.clipboard.writeText(link);
      setStatus('Link copied');
    } catch (error) {
      setPlannerError(error.message);
    } finally {
      setShareLoading(false);
    }
  };

  const selectTrip = (trip) => {
    setRouteData(trip.route_payload_json || null);
    setPlannerState(plannerFromTrip(trip));
    setActiveComparisonId(trip.route_payload_json?.comparison_options?.[0]?.id || 'route-0');
  };

  const selectSearch = (search) => {
    if (search.route_payload_json) {
      setRouteData(search.route_payload_json);
      setPlannerState(plannerFromRoute(search.route_payload_json, search.query_text));
      setActiveComparisonId(search.route_payload_json.comparison_options?.[0]?.id || 'route-0');
    } else {
      setPlannerState((current) => ({ ...current, queryText: search.query_text }));
    }
  };

  const comparisonId = useMemo(
    () => activeComparisonId || routeData?.comparison_options?.[0]?.id || 'route-0',
    [activeComparisonId, routeData],
  );

  return (
    <div className="app-shell">
      <MapCanvas routeData={routeData} activeComparisonId={comparisonId} />

      {isLoggedIn ? (
        <Sidebar
          recentSearches={appState.recent_searches || []}
          savedTrips={appState.recent_trips || []}
          onSelectTrip={selectTrip}
          onSelectSearch={selectSearch}
          user={appState.user}
          preferences={appState.preferences}
          isDummySession={isDummySession}
          onLogout={handleLogout}
          onUpdatePreferences={handleUpdatePreferences}
        />
      ) : null}

      <div className="app-overlay">
        <Header
          isLoggedIn={isLoggedIn}
          onOpenAuth={openAuth}
        />

        {configIssues.length > 0 ? (
          <div className="status-rail">
            {configIssues.map((issue) => (
              <span key={issue} className="status-pill">{issue}</span>
            ))}
          </div>
        ) : null}

        <div className="panel-stack">
          <RouteSummaryCard
            routeData={routeData}
            activeComparisonId={comparisonId}
            onSelectComparison={setActiveComparisonId}
            onSaveTrip={saveTrip}
            onShareTrip={shareTrip}
            saving={saveLoading}
            sharing={shareLoading}
          />
        </div>

        <SearchBar onOpen={() => setVoiceOpen(true)} />
      </div>

      <VoiceModal
        open={voiceOpen}
        onClose={() => setVoiceOpen(false)}
        status={status}
        voicePhase={voicePhase}
        isConnected={voiceConnected}
        isListening={isListening}
        audioLevel={audioLevel}
        transcript={transcript}
        routeData={routeData}
        onStartVoice={startVoice}
        onStopVoice={stopVoice}
        error={plannerError}
      />

      <AuthModal
        open={authOpen}
        mode={authMode}
        onClose={() => setAuthOpen(false)}
        onSubmit={handleAuthSubmit}
        onGoogleAuth={handleGoogleAuth}
        onDummyLogin={handleDummyLogin}
        dummyEnabled={dummyEnabled}
        error={authError}
        loading={authLoading}
      />
    </div>
  );
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function calculateRms(samples) {
  if (!samples.length) {
    return 0;
  }
  let sumSquares = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const value = Math.max(-1, Math.min(1, samples[index]));
    sumSquares += value * value;
  }
  return Math.sqrt(sumSquares / samples.length);
}

function createAudioEnhancerState(sampleRate) {
  return {
    calibrationSamples: 0,
    calibrationTarget: Math.floor(sampleRate * 0.6),
    dcLastInput: 0,
    dcLastOutput: 0,
    noiseFloor: 0.004,
  };
}

function enhanceSpeechSamples(samples, state) {
  const highPassed = new Float32Array(samples.length);
  const highPassCoefficient = 0.995;
  let sumSquares = 0;

  for (let index = 0; index < samples.length; index += 1) {
    const input = Math.max(-1, Math.min(1, samples[index] || 0));
    const output = input - state.dcLastInput + highPassCoefficient * state.dcLastOutput;
    state.dcLastInput = input;
    state.dcLastOutput = output;
    const clipped = Math.max(-1, Math.min(1, output));
    highPassed[index] = clipped;
    sumSquares += clipped * clipped;
  }

  const frameRms = Math.sqrt(sumSquares / Math.max(1, samples.length));
  if (state.calibrationSamples < state.calibrationTarget || frameRms < state.noiseFloor * 2.2) {
    const boundedNoise = Math.min(frameRms, 0.025);
    state.noiseFloor = state.noiseFloor * 0.94 + boundedNoise * 0.06;
    state.calibrationSamples += samples.length;
  }

  const gateThreshold = Math.min(0.03, Math.max(0.006, state.noiseFloor * 2.8));
  const speechGain = frameRms > gateThreshold ? Math.min(2.2, Math.max(1, 0.075 / Math.max(frameRms, 0.001))) : 0.22;
  const cleaned = new Float32Array(samples.length);

  for (let index = 0; index < highPassed.length; index += 1) {
    const value = highPassed[index];
    const magnitude = Math.abs(value);
    let gain = speechGain;
    if (magnitude < gateThreshold * 0.45) {
      gain = 0;
    } else if (magnitude < gateThreshold) {
      gain *= 0.35;
    }
    cleaned[index] = Math.max(-1, Math.min(1, value * gain));
  }

  return cleaned;
}

function floatToPcm16Base64(samples, inputSampleRate) {
  const outputSampleRate = 16000;
  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.max(1, Math.floor(samples.length / ratio));
  const pcm16 = new Int16Array(outputLength);
  for (let index = 0; index < outputLength; index += 1) {
    const sourceIndex = Math.min(samples.length - 1, Math.floor(index * ratio));
    const value = Math.max(-1, Math.min(1, samples[sourceIndex] || 0));
    pcm16[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }
  return arrayBufferToBase64(pcm16.buffer);
}

async function playAudioChunk(base64Data) {
  const audioData = base64ToArrayBuffer(base64Data);
  const context = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
  const samples = new Int16Array(audioData);
  const audioBuffer = context.createBuffer(1, samples.length, 24000);
  const channel = audioBuffer.getChannelData(0);
  for (let index = 0; index < samples.length; index += 1) {
    channel[index] = samples[index] / 32768;
  }
  const source = context.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(context.destination);
  source.start();
}

function base64ToArrayBuffer(base64) {
  const binaryString = atob(base64);
  const length = binaryString.length;
  const bytes = new Uint8Array(length);
  for (let index = 0; index < length; index += 1) {
    bytes[index] = binaryString.charCodeAt(index);
  }
  return bytes.buffer;
}
