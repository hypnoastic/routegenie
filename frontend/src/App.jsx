import React, { useState, useRef, useEffect } from 'react';
import { GoogleMap, useJsApiLoader, Polyline, Marker, InfoWindow } from '@react-google-maps/api';
import './App.css';

const libraries = ['places', 'geometry'];

const mapContainerStyle = {
  width: '100%',
  height: '100vh'
};

const defaultCenter = {
  lat: 37.7749,
  lng: -122.4194
};

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isOverlayOpen, setIsOverlayOpen] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState('');
  const [routeData, setRouteData] = useState(null);
  const [map, setMap] = useState(null);
  const [center, setCenter] = useState(defaultCenter);
  const [selectedStop, setSelectedStop] = useState(null);
  
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const overlayRef = useRef(null);

  const googleMapsApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

  console.log('Google Maps API Key loaded:', googleMapsApiKey ? '✅' : '❌');

  const { isLoaded } = useJsApiLoader({
    googleMapsApiKey: googleMapsApiKey,
    libraries
  });

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (overlayRef.current && !overlayRef.current.contains(event.target) && isOverlayOpen) {
        closeOverlay();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOverlayOpen]);

  const openOverlay = () => {
    setIsOverlayOpen(true);
    connectWebSocket();
    setTimeout(() => {
      startRecording();
    }, 300);
  };

  const closeOverlay = () => {
    setIsOverlayOpen(false);
    stopRecording();
    if (wsRef.current) {
      wsRef.current.close();
    }
    setIsConnected(false);
    setStatus('');
  };

  const connectWebSocket = () => {
    const userId = Math.floor(Math.random() * 10000);
    wsRef.current = new WebSocket(`ws://localhost:8000/ws/${userId}?is_audio=true`);
    
    wsRef.current.onopen = () => {
      console.log('✅ Connected to backend');
      setIsConnected(true);
      setStatus('Listening...');
    };
    
    wsRef.current.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      console.log('📨 Message type:', data.type);
      
      if (data.type === 'audio') {
        console.log('🔊 Playing audio chunk');
        const audioData = base64ToArrayBuffer(data.data);
        await playAudioChunk(audioData);
        setStatus('Playing response...');
      }
      else if (data.type === 'route') {
        console.log('✅ ROUTE DATA RECEIVED:', data.data);
        setRouteData(data.data);
        setStatus('Route displayed');
        displayRoute(data.data);
        setTimeout(() => closeOverlay(), 3000);
      }
      else if (data.type === 'turn_complete') {
        console.log('✅ Turn complete');
        setStatus('Ready');
      }
    };
    
    wsRef.current.onerror = (error) => {
      console.error('WebSocket error:', error);
      setStatus('Connection error');
      setIsConnected(false);
    };
    
    wsRef.current.onclose = () => {
      console.log('❌ Disconnected');
      setIsConnected(false);
    };
  };

  const displayRoute = (route) => {
    console.log('🗺️ displayRoute called');
    console.log('Route data:', route);
    
    if (!route) {
      console.error('❌ Route is null');
      return;
    }
    
    if (!window.google) {
      console.error('❌ Google not loaded');
      return;
    }
    
    if (!map) {
      console.error('❌ Map not initialized');
      return;
    }

    try {
      if (!route.polyline) {
        console.error('❌ No polyline in route');
        return;
      }
      
      const decodedPath = window.google.maps.geometry.encoding.decodePath(route.polyline);
      console.log('✅ Decoded polyline:', decodedPath.length, 'points');
      
      if (decodedPath.length === 0) {
        console.error('❌ Decoded path is empty');
        return;
      }

      setRouteData(prev => ({
        ...prev,
        ...route,
        decodedPath: decodedPath
      }));

      const bounds = new window.google.maps.LatLngBounds();
      decodedPath.forEach(point => bounds.extend(point));

      if (decodedPath.length > 0) {
        setCenter(decodedPath[0]);
      }

      setTimeout(() => {
        map.fitBounds(bounds, {
          top: 50,
          right: 50,
          bottom: 200,
          left: 50
        });
        console.log('✅ Map bounds fitted');
      }, 100);
      
    } catch (error) {
      console.error('❌ Error displaying route:', error);
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });
      
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000
      });
      
      const source = audioContextRef.current.createMediaStreamSource(stream);
      const processor = audioContextRef.current.createScriptProcessor(2048, 1, 1);
      
      processor.onaudioprocess = (e) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          const inputData = e.inputBuffer.getChannelData(0);
          
          const pcm16 = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            const s = Math.max(-1, Math.min(1, inputData[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          
          const base64Audio = arrayBufferToBase64(pcm16.buffer);
          
          wsRef.current.send(JSON.stringify({
            type: 'audio',
            data: base64Audio
          }));
        }
      };
      
      source.connect(processor);
      processor.connect(audioContextRef.current.destination);
      
      processorRef.current = processor;
      mediaRecorderRef.current = stream;
      setIsRecording(true);
      
    } catch (error) {
      console.error('Error accessing microphone:', error);
      setStatus('Microphone access denied');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.getTracks().forEach(track => track.stop());
      
      if (processorRef.current) {
        processorRef.current.disconnect();
      }
      
      mediaRecorderRef.current = null;
      processorRef.current = null;
      setIsRecording(false);
    }
  };

  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  const playAudioChunk = async (audioData) => {
    audioQueueRef.current.push(audioData);
    if (!isPlayingRef.current) {
      playNextChunk();
    }
  };

  const playNextChunk = async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }
    
    isPlayingRef.current = true;
    const audioData = audioQueueRef.current.shift();
    
    try {
      if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: 24000
        });
      }
      
      const pcm16Array = new Int16Array(audioData);
      const audioBuffer = audioContextRef.current.createBuffer(1, pcm16Array.length, 24000);
      const channelData = audioBuffer.getChannelData(0);
      
      for (let i = 0; i < pcm16Array.length; i++) {
        channelData[i] = pcm16Array[i] / 32768.0;
      }
      
      const source = audioContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContextRef.current.destination);
      
      source.onended = () => {
        playNextChunk();
      };
      
      source.start();
    } catch (error) {
      console.error('Error playing audio:', error);
      playNextChunk();
    }
  };

  const arrayBufferToBase64 = (buffer) => {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  };

  const base64ToArrayBuffer = (base64) => {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  };

  if (!isLoaded) {
    return <div className="loading">Loading...</div>;
  }

  return (
    <div className="app-container">
      {/* Full-screen Google Map */}
      <GoogleMap
        mapContainerStyle={mapContainerStyle}
        center={center}
        zoom={13}
        onLoad={setMap}
        options={{
          zoomControl: true,
          streetViewControl: false,
          mapTypeControl: false,
          fullscreenControl: false,
          gestureHandling: 'greedy'
        }}
      >
        {routeData && routeData.decodedPath && (
          <>
            {/* Blue polyline for the route */}
            <Polyline
              path={routeData.decodedPath}
              geodesic={true}
              options={{
                strokeColor: '#1f88e5',
                strokeOpacity: 0.8,
                strokeWeight: 5,
                zIndex: 2
              }}
            />
            
            {/* Start marker */}
            <Marker
              position={routeData.decodedPath[0]}
              title="Start"
              options={{
                icon: 'http://maps.google.com/mapfiles/ms/icons/green-dot.png'
              }}
            />
            
            {/* Stop markers */}
            {routeData.stops && routeData.stops.map((stop, idx) => (
              <Marker
                key={`stop-${idx}`}
                position={{ lat: stop.lat, lng: stop.lng }}
                title={stop.name}
                onClick={() => setSelectedStop(stop)}
                options={{
                  icon: 'http://maps.google.com/mapfiles/ms/icons/yellow-dot.png'
                }}
              >
                {selectedStop && selectedStop.name === stop.name && (
                  <InfoWindow onCloseClick={() => setSelectedStop(null)}>
                    <div className="info-window">
                      <h4>{stop.name}</h4>
                      <p>{stop.address}</p>
                      {stop.rating && <p>⭐ {stop.rating}</p>}
                    </div>
                  </InfoWindow>
                )}
              </Marker>
            ))}
            
            {/* End marker */}
            <Marker
              position={routeData.decodedPath[routeData.decodedPath.length - 1]}
              title="End"
              options={{
                icon: 'http://maps.google.com/mapfiles/ms/icons/red-dot.png'
              }}
            />
          </>
        )}
      </GoogleMap>

      {/* Route info box */}
      {routeData && (
        <div className="route-info-box">
          <h3>{routeData.origin} → {routeData.destination}</h3>
          <div className="route-details">
            <div className="detail-item">
              <span className="detail-label">Distance</span>
              <span className="detail-value">{routeData.distance}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Duration</span>
              <span className="detail-value">{routeData.duration}</span>
            </div>
          </div>
          
          {/* Stops section */}
          {routeData.stops && routeData.stops.length > 0 && (
            <div className="stops-section">
              <h4>Stops ({routeData.stops.length})</h4>
              <div className="stops-list">
                {routeData.stops.map((stop, idx) => (
                  <div key={idx} className="stop-item">
                    <div className="stop-marker">🟡</div>
                    <div className="stop-info">
                      <p className="stop-name">{stop.name}</p>
                      <p className="stop-address">{stop.address}</p>
                      {stop.rating && (
                        <p className="stop-rating">⭐ {stop.rating}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Floating Input Bar */}
      <div className="floating-input-bar" onClick={openOverlay}>
        <div className="input-bar-content">
          <div className="search-icon-container">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2"/>
              <path d="M12 12L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="input-placeholder">Find your route</span>
        </div>
      </div>

      {/* AI Overlay */}
      {isOverlayOpen && (
        <div className="overlay-backdrop">
          <div className="ai-overlay" ref={overlayRef}>
            <button className="close-button" onClick={closeOverlay}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </button>
            
            <div className="overlay-header">
              <h2>RouteGenie</h2>
              <p className="subtitle">Voice-powered navigation</p>
            </div>
            
            <div className="connection-status">
              <div className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></div>
              <p className="status-text">{status || 'Connecting...'}</p>
            </div>

            {/* Animated Voice Bars */}
            <div className="voice-bars-container">
              {Array.from({ length: 5 }, (_, index) => (
                <div 
                  key={index}
                  className={`voice-bar ${isConnected && isRecording ? 'active' : 'dot'}`}
                ></div>
              ))}
            </div>

            <div className="instructions">
              <p className="instruction-title">Try saying:</p>
              <p className="instruction-example">Route from Gurgaon to Delhi with McDonald's stop</p>
              <p className="instruction-subtitle">or ask for any two locations with stops</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
