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
        // Delay display to ensure map is ready
        setTimeout(() => {
          displayRoute(data.data);
        }, 500);
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
      
      console.log('📍 Decoding polyline with', route.polyline.length, 'chars...');
      
      let decodedPath = [];
      try {
        decodedPath = window.google.maps.geometry.encoding.decodePath(route.polyline);
      } catch (error) {
        console.error('❌ Error decoding polyline:', error);
        return;
      }
      
      console.log('✅ Decoded polyline:', decodedPath.length, 'points');
      
      // Validate and filter coordinates
      let validPoints = [];
      for (let i = 0; i < decodedPath.length; i++) {
        const point = decodedPath[i];
        
        // Check if point is valid (should be LatLng object or have lat/lng properties)
        let lat, lng;
        
        if (point.lat && point.lng) {
          lat = point.lat();
          lng = point.lng();
        } else if (point.latitude !== undefined && point.longitude !== undefined) {
          lat = point.latitude;
          lng = point.longitude;
        } else if (Array.isArray(point)) {
          lat = point[0];
          lng = point[1];
        } else {
          console.warn(`⚠️ Invalid coordinate at index ${i}:`, point);
          continue;
        }
        
        // Validate latitude (-90 to 90) and longitude (-180 to 180)
        if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
          validPoints.push(point);
        } else {
          console.warn(`⚠️ Out of bounds coordinate at ${i}:`, lat, lng);
        }
      }
      
      console.log('✅ Valid points after filtering:', validPoints.length);
      
      if (validPoints.length === 0) {
        console.error('❌ No valid coordinates found');
        return;
      }

      // Create bounds
      const bounds = new window.google.maps.LatLngBounds();
      
      console.log('📊 Adding points to bounds...');
      
      // Add all polyline points
      for (const point of validPoints) {
        try {
          bounds.extend(point);
        } catch (error) {
          console.warn('⚠️ Error extending bounds with point:', point, error);
        }
      }
      
      // Add stop if exists
      if (route.stop) {
        try {
          const stopPoint = new window.google.maps.LatLng(route.stop.lat, route.stop.lng);
          
          // Validate stop coordinates
          if (route.stop.lat >= -90 && route.stop.lat <= 90 && 
              route.stop.lng >= -180 && route.stop.lng <= 180) {
            bounds.extend(stopPoint);
            console.log('✅ Stop added to bounds:', route.stop.lat, route.stop.lng);
          } else {
            console.warn('⚠️ Invalid stop coordinates:', route.stop.lat, route.stop.lng);
          }
        } catch (error) {
          console.error('❌ Error adding stop to bounds:', error);
        }
      }
      
      // Check bounds validity
      const boundsCenter = bounds.getCenter();
      const boundsNE = bounds.getNorthEast();
      const boundsSW = bounds.getSouthWest();
      
      console.log('📍 Bounds Center:', boundsCenter.lat(), boundsCenter.lng());
      console.log('📍 Bounds NE:', boundsNE.lat(), boundsNE.lng());
      console.log('📍 Bounds SW:', boundsSW.lat(), boundsSW.lng());

      // Update route data with valid decoded path
      setRouteData(prev => ({
        ...prev,
        ...route,
        decodedPath: validPoints
      }));

      // Set center to first valid point
      if (validPoints.length > 0) {
        const firstPoint = validPoints[0];
        let firstLat, firstLng;
        
        if (firstPoint.lat && firstPoint.lng) {
          firstLat = firstPoint.lat();
          firstLng = firstPoint.lng();
        } else if (Array.isArray(firstPoint)) {
          firstLat = firstPoint[0];
          firstLng = firstPoint[1];
        } else {
          firstLat = firstPoint.latitude;
          firstLng = firstPoint.longitude;
        }
        
        setCenter({ lat: firstLat, lng: firstLng });
        console.log('📍 Center set to first point:', firstLat, firstLng);
      }

      // Fit bounds to map with proper delay
      setTimeout(() => {
        try {
          map.fitBounds(bounds, 40); // padding parameter
          console.log('✅ Map bounds fitted successfully');
        } catch (error) {
          console.error('❌ Error fitting bounds:', error);
          // Fallback: just set center and zoom
          map.setCenter(bounds.getCenter());
          map.setZoom(11);
          console.log('⚠️ Used fallback center/zoom');
        }
      }, 200);
      
    } catch (error) {
      console.error('❌ Error displaying route:', error);
      console.error(error.stack);
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
                strokeOpacity: 0.9,
                strokeWeight: 6,
                zIndex: 2,
                clickable: false
              }}
            />
            
            {/* Start marker */}
            <Marker
              position={routeData.decodedPath[0]}
              title="Start"
              icon={{
                url: 'http://maps.google.com/mapfiles/ms/icons/green-dot.png',
                scaledSize: new window.google.maps.Size(32, 32)
              }}
              options={{
                zIndex: 1
              }}
            />
            
            {/* Single Stop marker */}
            {routeData.stop && (
              <Marker
                position={{ lat: routeData.stop.lat, lng: routeData.stop.lng }}
                title={routeData.stop.name}
                onClick={() => setSelectedStop(routeData.stop)}
                icon={{
                  url: 'http://maps.google.com/mapfiles/ms/icons/yellow-dot.png',
                  scaledSize: new window.google.maps.Size(32, 32)
                }}
                options={{
                  zIndex: 3
                }}
              >
                {selectedStop && (
                  <InfoWindow onCloseClick={() => setSelectedStop(null)}>
                    <div className="info-window">
                      <h4>{selectedStop.name}</h4>
                      <p>{selectedStop.address}</p>
                      {selectedStop.rating && <p>⭐ {selectedStop.rating}</p>}
                    </div>
                  </InfoWindow>
                )}
              </Marker>
            )}
            
            {/* End marker */}
            <Marker
              position={routeData.decodedPath[routeData.decodedPath.length - 1]}
              title="End"
              icon={{
                url: 'http://maps.google.com/mapfiles/ms/icons/red-dot.png',
                scaledSize: new window.google.maps.Size(32, 32)
              }}
              options={{
                zIndex: 1
              }}
            />
          </>
        )}
      </GoogleMap>

      {/* Route info box */}
      {routeData && (
        <div className="route-info-box">
          {/* Source and Destination Section */}
          <div className="route-locations">
            <div className="location-item">
              <span className="location-label">From</span>
              <span className="location-name" title={routeData.origin}>{routeData.origin}</span>
            </div>
            <div className="location-item">
              <span className="location-label">To</span>
              <span className="location-name" title={routeData.destination}>{routeData.destination}</span>
            </div>
          </div>
          
          {/* Distance and Duration Display */}
          <div className="route-metrics">
            <div className="metric-container">
              <span className="metric-label">Distance</span>
              <span className="metric-value">{routeData.distance}</span>
            </div>
            <div className="metric-container">
              <span className="metric-label">Duration</span>
              <span className="metric-value">{routeData.duration}</span>
            </div>
          </div>
          
          {/* Single Stop Display */}
          {routeData.stop && (
            <div className="stop-section">
              <div className="stop-header">
                <span className="stop-icon">🟡</span>
                <span className="stop-label">Stop</span>
              </div>
              <div className="stop-card-single">
                <h5 className="stop-name" title={routeData.stop.name}>{routeData.stop.name}</h5>
                <p className="stop-address" title={routeData.stop.address}>{routeData.stop.address}</p>
                {routeData.stop.rating && (
                  <div className="stop-rating">
                    <span className="rating-star">⭐</span>
                    <span className="rating-value">{routeData.stop.rating}</span>
                  </div>
                )}
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
              <p className="instruction-example">Route from Gurgaon to Delhi with McDonald's</p>
              <p className="instruction-subtitle">or ask for any two locations with a stop</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
