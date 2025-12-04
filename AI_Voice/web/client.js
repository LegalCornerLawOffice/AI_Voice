/**
 * AI Voice Intake System - Web Client
 * Handles WebRTC audio capture and WebSocket communication
 */

let websocket = null;
let mediaStream = null;
let audioContext = null;
let audioWorklet = null;
let isRecording = false;
let currentAudioSource = null;

// UI Elements
const statusDiv = document.getElementById('status');
const statusText = document.getElementById('status-text');
const transcriptDiv = document.getElementById('transcript');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const visualizer = document.getElementById('visualizer');

/**
 * Start the call
 */
async function startCall() {
    try {
        updateStatus('connecting', 'Connecting...');
        startBtn.disabled = true;
        
        // Request microphone access
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });
        
        // Connect WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        
        // Get selected section if any
        const sectionDropdown = document.getElementById('sectionDropdown');
        const selectedSection = sectionDropdown ? sectionDropdown.value : '';
        
        // Add section as query parameter if selected
        let wsUrl = `${protocol}//${window.location.host}/ws/call`;
        if (selectedSection) {
            wsUrl += `?start_section=${encodeURIComponent(selectedSection)}`;
        }
        
        websocket = new WebSocket(wsUrl);
        
        websocket.onopen = () => {
            console.log('WebSocket connected');
            updateStatus('connected', '🎙️ Call in progress');
            startBtn.disabled = true;
            stopBtn.disabled = false;
            visualizer.style.display = 'flex';
            clearTranscript();
            
            // Start audio processing
            startAudioCapture();
        };
        
        websocket.onmessage = (event) => {
            handleServerMessage(JSON.parse(event.data));
        };
        
        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            updateStatus('disconnected', 'Connection error');
            stopCall();
        };
        
        websocket.onclose = () => {
            console.log('WebSocket closed');
            updateStatus('disconnected', 'Call ended');
            stopCall();
        };
        
    } catch (error) {
        console.error('Error starting call:', error);
        alert('Error accessing microphone: ' + error.message);
        updateStatus('disconnected', 'Error');
        startBtn.disabled = false;
    }
}

/**
 * Stop the call
 */
function stopCall() {
    isRecording = false;
    
    // Stop media stream
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    
    // Close audio context
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    
    // Close WebSocket
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({ type: 'stop' }));
        websocket.close();
    }
    websocket = null;
    
    // Update UI
    updateStatus('disconnected', 'Not connected');
    startBtn.disabled = false;
    stopBtn.disabled = true;
    visualizer.style.display = 'none';
}

/**
 * Start capturing and sending audio
 */
async function startAudioCapture() {
    isRecording = true;
    
    // Create audio context
    audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(mediaStream);
    
    // Create script processor (simpler than AudioWorklet for now)
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    
    processor.onaudioprocess = (event) => {
        if (!isRecording || !websocket || websocket.readyState !== WebSocket.OPEN) {
            return;
        }
        
        const inputData = event.inputBuffer.getChannelData(0);
        
        // Convert Float32Array to Int16Array (PCM)
        const pcmData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
            const s = Math.max(-1, Math.min(1, inputData[i]));
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        
        // Convert to base64 and send
        const base64Audio = arrayBufferToBase64(pcmData.buffer);
        
        websocket.send(JSON.stringify({
            type: 'audio',
            data: base64Audio,
            sampleRate: 16000
        }));
    };
    
    source.connect(processor);
    processor.connect(audioContext.destination);
}

/**
 * Handle messages from server
 */
function handleServerMessage(message) {
    console.log('Server message:', message);
    
    switch (message.type) {
        case 'transcript':
            addTranscript(message.speaker || 'ai', message.text);
            break;
            
        case 'audio':
            // Received audio from server (TTS)
            playAudio(message.data);
            break;
            
        case 'interrupt':
            // User interrupted, stop current audio
            console.log('Interrupt signal received');
            stopAudioPlayback();
            break;
            
        case 'error':
            console.error('Server error:', message.error);
            break;
    }
}

/**
 * Play audio from server
 */
async function playAudio(base64Audio) {
    try {
        // Decode base64 to array buffer
        const audioData = base64ToArrayBuffer(base64Audio);
        
        // Create audio context if needed
        if (!audioContext) {
            audioContext = new AudioContext({ sampleRate: 16000 });
        }
        
        // Convert raw PCM (Int16) to Float32 for Web Audio API
        const pcmData = new Int16Array(audioData);
        const audioBuffer = audioContext.createBuffer(1, pcmData.length, 16000);
        const channelData = audioBuffer.getChannelData(0);
        
        // Convert Int16 PCM to Float32 (-1.0 to 1.0)
        for (let i = 0; i < pcmData.length; i++) {
            channelData[i] = pcmData[i] / 32768.0;
        }
        
        // Stop any currently playing audio before starting new audio
        if (currentAudioSource) {
            currentAudioSource.stop();
            currentAudioSource = null;
        }
        
        // Create source and play
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        
        // Track the current audio source so we can interrupt it
        currentAudioSource = source;
        
        // Clear reference when audio finishes naturally
        source.onended = () => {
            if (currentAudioSource === source) {
                currentAudioSource = null;
            }
        };
        
        source.start(0);
        
    } catch (error) {
        console.error('Error playing audio:', error);
    }
}

/**
 * Stop any currently playing audio
 */
function stopAudioPlayback() {
    if (currentAudioSource) {
        try {
            currentAudioSource.stop();
        } catch (e) {
            // Already stopped
        }
        currentAudioSource = null;
    }
}

/**
 * Add message to transcript
 */
function addTranscript(speaker, text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `transcript-message ${speaker}`;
    
    const speakerLabel = speaker === 'user' ? 'You' : 'AI Assistant';
    
    messageDiv.innerHTML = `
        <strong>${speakerLabel}</strong>
        ${text}
    `;
    
    transcriptDiv.appendChild(messageDiv);
    transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
}

/**
 * Clear transcript
 */
function clearTranscript() {
    transcriptDiv.innerHTML = '';
}

/**
 * Update connection status
 */
function updateStatus(state, text) {
    statusDiv.className = `status ${state}`;
    statusText.textContent = text;
}

/**
 * Convert ArrayBuffer to Base64
 */
function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

/**
 * Convert Base64 to ArrayBuffer
 */
function base64ToArrayBuffer(base64) {
    const binaryString = atob(base64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopCall();
});
