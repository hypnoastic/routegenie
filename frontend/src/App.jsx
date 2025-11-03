// App.js
import React, { useState, useRef, useEffect } from 'react';
import './App.css';

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState('Click microphone to start');
  
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);

  useEffect(() => {
    connectWebSocket();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  const connectWebSocket = () => {
    const userId = Math.floor(Math.random() * 10000);
    wsRef.current = new WebSocket(`ws://localhost:8000/ws/${userId}?is_audio=true`);
    
    wsRef.current.onopen = () => {
      console.log('✅ Connected to Gemini ADK backend');
      setIsConnected(true);
      setStatus('Connected - Ready to talk');
    };
    
    wsRef.current.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      
      // Handle audio data only
      if (data.mime_type === 'audio/pcm') {
        const audioData = base64ToArrayBuffer(data.data);
        await playAudioChunk(audioData);
        setStatus('🔊 Playing AI response...');
      }
      // Handle turn completion
      else if (data.turn_complete) {
        setStatus('Response complete - Ready for next input');
      }
      // Handle interruption
      else if (data.interrupted) {
        setStatus('Interrupted - Ready to talk');
      }
    };
    
    wsRef.current.onerror = (error) => {
      console.error('WebSocket error:', error);
      setStatus('Connection error');
      setIsConnected(false);
    };
    
    wsRef.current.onclose = () => {
      console.log('Disconnected');
      setIsConnected(false);
      setStatus('Disconnected');
    };
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
            mime_type: 'audio/pcm',
            data: base64Audio
          }));
        }
      };
      
      source.connect(processor);
      processor.connect(audioContextRef.current.destination);
      
      processorRef.current = processor;
      mediaRecorderRef.current = stream;
      setIsRecording(true);
      setStatus('🎤 Recording... Speak now');
      
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
      setStatus('⏳ Waiting for AI response...');
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

  return (
    <div className="App">
      <div className="container">
        <h1>🎙️ Gemini Live Voice Assistant</h1>
        <p className="subtitle">Audio-Only Mode (No Transcription)</p>
        
        <div className="status-container">
          <div className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? '🟢' : '🔴'}
          </div>
          <p className="status-text">{status}</p>
        </div>
        
        <div className="controls">
          <button 
            className={`mic-button ${isRecording ? 'recording' : ''}`}
            onClick={toggleRecording}
            disabled={!isConnected}
          >
            <span className="mic-icon">{isRecording ? '⏹️' : '🎤'}</span>
            <span className="mic-text">
              {isRecording ? 'Stop Talking' : 'Start Talking'}
            </span>
          </button>
        </div>
        
        <div className="info">
          <p>💡 Click microphone and speak naturally</p>
          <p>🔊 Gemini responds with audio only</p>
        </div>
      </div>
    </div>
  );
}

export default App;
