/**
 * EV Charging Voice Assistant - Frontend Application
 * Handles LivekitClient connection, audio streaming, and transcription display
 */

class EVChargingApp {
    constructor() {
        this.room = null;
        this.isConnected = false;
        this.isMuted = false;
        this.localAudioTrack = null;
        this.transcripts = [];

        this.initializeElements();
        this.attachEventListeners();
    }

    initializeElements() {
        // Buttons
        this.connectBtn = document.getElementById('connectBtn');
        this.disconnectBtn = document.getElementById('disconnectBtn');
        this.muteBtn = document.getElementById('muteBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.cancelBtn = document.getElementById('cancelBtn');

        // Status elements
        this.connectionStatus = document.getElementById('connectionStatus');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.connectionInfo = document.getElementById('connectionInfo');
        this.waveContainer = document.getElementById('waveContainer');

        // Transcription elements
        this.transcriptionContent = document.getElementById('transcriptionContent');
        this.languageIndicator = document.getElementById('languageIndicator');

        // Modal elements
        this.connectionModal = document.getElementById('connectionModal');
        this.connectionForm = document.getElementById('connectionForm');
        this.roomNameInput = document.getElementById('roomName');
        this.participantNameInput = document.getElementById('participantName');
    }

    attachEventListeners() {
        this.connectBtn.addEventListener('click', () => this.showConnectionModal());
        this.disconnectBtn.addEventListener('click', () => this.disconnect());
        this.muteBtn.addEventListener('click', () => this.toggleMute());
        this.clearBtn.addEventListener('click', () => this.clearTranscripts());
        this.cancelBtn.addEventListener('click', () => this.hideConnectionModal());
        this.connectionForm.addEventListener('submit', (e) => this.handleConnectionSubmit(e));
    }

    showConnectionModal() {
        this.connectionModal.classList.add('active');
    }

    hideConnectionModal() {
        this.connectionModal.classList.remove('active');
    }

    async handleConnectionSubmit(e) {
        e.preventDefault();

        const roomName = this.roomNameInput.value.trim();
        const participantName = this.participantNameInput.value.trim();

        if (!roomName || !participantName) {
            alert('Please fill in all fields');
            return;
        }

        this.hideConnectionModal();
        await this.connect(roomName, participantName);
    }

    async connect(roomName, participantName) {
        try {
            this.updateStatus('connecting', 'Connecting...');
            this.connectionInfo.innerHTML = '<p>Connecting to voice assistant...</p>';

            // Get access token from backend
            const connectionConfig = await this.getAccessToken(roomName, participantName);
            const { token, url: livekitUrl, deployment } = connectionConfig;

            // Initialize LivekitClient room
            this.room = new LivekitClient.Room({
                adaptiveStream: true,
                dynacast: true,
            });

            // Set up event listeners
            this.setupRoomEventListeners();

            // Connect to the room
            await this.room.connect(livekitUrl, token);

            // Set up local audio track
            await this.setupLocalAudio();

            this.isConnected = true;
            this.updateStatus('connected', 'Connected');
            this.connectionInfo.innerHTML = `
                <p>✓ Connected! Start speaking to interact with the assistant.</p>
                <p><strong>Deployment:</strong> ${deployment === 'cloud' ? 'LiveKit Cloud' : 'Local LiveKit Server'}</p>
                <p><strong>Server:</strong> ${livekitUrl}</p>
            `;
            this.waveContainer.classList.add('active');

            // Enable/disable buttons
            this.connectBtn.disabled = true;
            this.disconnectBtn.disabled = false;
            this.muteBtn.disabled = false;

        } catch (error) {
            console.error('Connection error:', error);
            this.updateStatus('disconnected', 'Connection Failed');
            this.connectionInfo.innerHTML = `<p style="color: var(--danger-color);">Connection failed: ${error.message}</p>`;

            // Show helpful error message
            if (error.message.includes('token')) {
                alert('Failed to get access token. Please make sure the backend server is running.');
            } else if (error.message.includes('connect')) {
                alert('Failed to connect to the LiveKit server. Please ensure the configured LiveKit deployment is reachable.');
            }
        }
    }

    async getAccessToken(roomName, participantName) {
        try {
            // In production, this should call your backend API
            // For now, we'll need to use a token generated from the backend
            let apiBaseUrl = window.location.origin;
            if (!apiBaseUrl.startsWith('http')) {
                apiBaseUrl = 'http://localhost:5000';
            }

            const response = await fetch(`${apiBaseUrl}/api/token`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    roomName: roomName,
                    participantName: participantName,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to get access token');
            }

            const data = await response.json();
            return data;

        } catch (error) {
            console.error('Token fetch error:', error);

            // Fallback: Show instructions to user
            throw new Error('Cannot fetch token. Please ensure the FastAPI server is running.');
        }
    }

    setupRoomEventListeners() {
        // Track subscribed
        this.room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            console.log('Track subscribed:', track.kind);

            if (track.kind === LivekitClient.Track.Kind.Audio) {
                const audioElement = track.attach();
                document.body.appendChild(audioElement);
            }
        });

        // Track unsubscribed
        this.room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track) => {
            track.detach().forEach(element => element.remove());
        });

        // Data received (for transcriptions)
        this.room.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {
            const decoder = new TextDecoder();
            const data = JSON.parse(decoder.decode(payload));

            if (data.type === 'transcription') {
                this.addTranscript(data.text, data.isFinal, participant);
            }
        });

        // Participant connected
        this.room.on(LivekitClient.RoomEvent.ParticipantConnected, (participant) => {
            console.log('Participant connected:', participant.identity);
        });

        // Disconnected
        this.room.on(LivekitClient.RoomEvent.Disconnected, () => {
            console.log('Disconnected from room');
            this.handleDisconnection();
        });
    }

    async setupLocalAudio() {
        try {
            // Ask LiveKit SDK to create and manage the microphone track.
            // Passing capture options instead of a MediaStream avoids structuredClone errors
            // thrown by browsers when cloning stream objects.
            this.localAudioTrack = await LivekitClient.createLocalAudioTrack();

            // Publish the track to the connected room
            await this.room.localParticipant.publishTrack(this.localAudioTrack);

            console.log('Local audio track published');

        } catch (error) {
            console.error('Microphone access error:', error);
            alert('Failed to access microphone. Please grant microphone permissions and try again.');
            throw error;
        }
    }

    async disconnect() {
        if (this.room && this.localAudioTrack) {
            try {
                await this.room.localParticipant.unpublishTrack(this.localAudioTrack);
            } catch (error) {
                console.warn('Unable to unpublish local audio track cleanly:', error);
            }
        }

        if (this.room) {
            await this.room.disconnect();
        }
        this.handleDisconnection();
    }

    handleDisconnection() {
        this.isConnected = false;
        this.updateStatus('disconnected', 'Disconnected');
        this.connectionInfo.innerHTML = '<p>Click "Connect" to start talking with the voice assistant</p>';
        this.waveContainer.classList.remove('active');

        // Enable/disable buttons
        this.connectBtn.disabled = false;
        this.disconnectBtn.disabled = true;
        this.muteBtn.disabled = true;

        // Reset mute state
        this.isMuted = false;
        this.updateMuteButton();

        // Clean up
        if (this.localAudioTrack) {
            this.localAudioTrack.stop();
            this.localAudioTrack = null;
        }

        this.room = null;
    }

    async toggleMute() {
        if (!this.localAudioTrack) return;

        this.isMuted = !this.isMuted;

        if (this.isMuted) {
            await this.localAudioTrack.mute();
        } else {
            await this.localAudioTrack.unmute();
        }

        this.updateMuteButton();
    }

    updateMuteButton() {
        if (this.isMuted) {
            this.muteBtn.innerHTML = '<span class="btn-icon">🔇</span><span class="btn-text">Unmute</span>';
            this.muteBtn.style.background = 'var(--danger-color)';
            this.muteBtn.style.color = 'white';
        } else {
            this.muteBtn.innerHTML = '<span class="btn-icon">🔊</span><span class="btn-text">Mute</span>';
            this.muteBtn.style.background = '';
            this.muteBtn.style.color = '';
        }
    }

    updateStatus(status, text) {
        this.statusText.textContent = text;
        this.statusDot.className = 'status-dot';

        if (status === 'connected') {
            this.statusDot.classList.add('connected');
        } else if (status === 'connecting') {
            this.statusDot.classList.add('connecting');
        }
    }

    addTranscript(text, isFinal, participant) {
        const isUser = participant === this.room?.localParticipant;
        const role = isUser ? 'user' : 'assistant';

        // Detect language (simple heuristic)
        const language = this.detectLanguage(text);
        this.updateLanguageIndicator(language);

        // Remove empty state if exists
        const emptyState = this.transcriptionContent.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        // Check if we should update the last message or create a new one
        const lastMessage = this.transcriptionContent.lastElementChild;
        if (!isFinal && lastMessage && lastMessage.dataset.role === role) {
            // Update existing partial transcript
            const messageText = lastMessage.querySelector('.message-text');
            messageText.textContent = text;
        } else if (isFinal) {
            // Create new message
            const messageDiv = document.createElement('div');
            messageDiv.className = `transcript-message ${role}`;
            messageDiv.dataset.role = role;

            const now = new Date();
            const timeString = now.toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit'
            });

            messageDiv.innerHTML = `
                <div class="message-label">${role === 'user' ? 'You' : 'Assistant'}</div>
                <div class="message-text">${text}</div>
                <div class="message-time">${timeString}</div>
            `;

            this.transcriptionContent.appendChild(messageDiv);

            // Store transcript
            this.transcripts.push({
                role,
                text,
                timestamp: now,
                language
            });

            // Auto-scroll to bottom
            this.transcriptionContent.scrollTop = this.transcriptionContent.scrollHeight;
        }
    }

    detectLanguage(text) {
        // Check for Hindi characters (Devanagari script)
        const hindiRegex = /[\u0900-\u097F]/;
        return hindiRegex.test(text) ? 'hi' : 'en';
    }

    updateLanguageIndicator(language) {
        const badge = this.languageIndicator.querySelector('.lang-badge');
        if (language === 'hi') {
            badge.textContent = 'HI';
            badge.classList.add('hindi');
        } else {
            badge.textContent = 'EN';
            badge.classList.remove('hindi');
        }
    }

    clearTranscripts() {
        if (this.transcripts.length === 0) return;

        if (confirm('Are you sure you want to clear all transcripts?')) {
            this.transcripts = [];
            this.transcriptionContent.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">💬</div>
                    <p>Conversation transcription will appear here</p>
                </div>
            `;
        }
    }

    // Simulate receiving transcripts (for testing without backend)
    simulateTranscript(text, role = 'assistant', language = 'en') {
        const mockParticipant = role === 'user' ? this.room?.localParticipant : null;
        this.addTranscript(text, true, mockParticipant);
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Check if LivekitClient is loaded
    if (typeof LivekitClient === 'undefined') {
        console.error('LivekitClient client library failed to load!');
        console.error('Please check your internet connection and try refreshing the page.');
        alert('Error: LivekitClient client library failed to load. Please check your internet connection and refresh the page.');
        return;
    }

    console.log('LivekitClient client library loaded successfully:', LivekitClient);
    window.app = new EVChargingApp();

    // For debugging: expose simulate function
    window.simulateConversation = () => {
        setTimeout(() => {
            app.simulateTranscript("Hello! Welcome to EV Charging Support. How can I help you today?", "assistant", "en");
        }, 1000);

        setTimeout(() => {
            app.simulateTranscript("Where is the nearest charging station?", "user", "en");
        }, 3000);

        setTimeout(() => {
            app.simulateTranscript("You can find the nearest charging station by sharing your location. Our stations are available in Delhi NCR, Mumbai, Bangalore, Hyderabad, and Pune. Which city are you in?", "assistant", "en");
        }, 5000);
    };
});
