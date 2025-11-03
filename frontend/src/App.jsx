import React, { useState, useRef, useEffect } from 'react';
import { GoogleMap, useJsApiLoader, Polyline, Marker } from '@react-google-maps/api';
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
      setStatus('Connected - Tap to speak');
    };
    
    wsRef.current.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      console.log('📨 Message type:', data.type);
      
      if (data.type === 'audio') {
        console.log('🔊 Playing audio chunk');
        const audioData = base64ToArrayBuffer(data.data);
        await playAudioChunk(audioData);
        setStatus('🔊 AI responding...');
      }
      else if (data.type === 'route') {
        console.log('✅ ROUTE DATA RECEIVED:', data.data);
        setRouteData(data.data);
        setStatus('Displaying route...');
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
      setStatus('🎤 Listening... Ask for directions');
      
    } catch (error) {
      console.error('Error accessing microphone:', error);
      setStatus('❌ Microphone access denied');
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
      setStatus('Processing...');
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
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
    return <div className="loading">🗺️ Loading Maps...</div>;
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
        {/* Draw route polyline */}
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
          <p>📍 {routeData.distance}</p>
          <p>⏱️ {routeData.duration}</p>
        </div>
      )}

      {/* Floating Input Bar */}
      <div className="floating-input-bar" onClick={openOverlay}>
        <div className="input-bar-content">
          <span className="mic-icon-small">🎤</span>
          <span className="input-placeholder">Ask for directions...</span>
        </div>
      </div>

      {/* AI Overlay */}
      {isOverlayOpen && (
        <div className="overlay-backdrop">
          <div className="ai-overlay" ref={overlayRef}>
            <button className="close-button" onClick={closeOverlay}>×</button>
            
            <h2>🗺️ Navigation Assistant</h2>
            
            <div className="status-display">
              <div className={`connection-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
                {isConnected ? '🟢' : '🔴'}
              </div>
              <p>{status || 'Connecting...'}</p>
            </div>

            <button 
              className={`voice-button ${isRecording ? 'recording' : ''}`}
              onClick={toggleRecording}
              disabled={!isConnected}
            >
              <span className="mic-icon-large">{isRecording ? '⏹️' : '🎤'}</span>
              <span className="button-text">
                {isRecording ? 'Stop' : 'Tap to Speak'}
              </span>
            </button>

            <div className="instructions">
              <p>💡 Try: "Show me directions from Gurgaon to Rewari"</p>
              <p>🚗 Or: "Route from here to airport"</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
