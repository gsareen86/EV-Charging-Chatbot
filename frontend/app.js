/**
 * EV Charging Voice Assistant - PRODUCTION Frontend
 * Features:
 * - Real-time streaming transcriptions (partial + final)
 * - Chat-like interface with proper message bubbles
 * - Proper sentence completion handling
 * - Transfer request notifications
 */

class EVChargingApp {
    constructor() {
        this.room = null;
        this.isConnected = false;
        this.isMuted = false;
        this.localAudioTrack = null;
        this.transcripts = [];
        
        // Track current partial transcriptions to update them
        this.currentUserPartial = null;
        this.currentAssistantPartial = null;

        this.initializeElements();
        this.attachEventListeners();
        
        console.log('🚀 EV Charging App initialized');
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
            console.log('🔌 Starting connection...');
            this.updateStatus('connecting', 'Connecting...');
            this.connectionInfo.innerHTML = '<p>Connecting to voice assistant...</p>';

            // Get access token
            const connectionConfig = await this.getAccessToken(roomName, participantName);
            const { token, url: livekitUrl, deployment } = connectionConfig;
            console.log(`✓ Token received`);

            // Initialize LiveKit room
            this.room = new LivekitClient.Room({
                adaptiveStream: true,
                dynacast: true,
            });

            // Set up event listeners
            this.setupRoomEventListeners();

            // Connect to the room
            await this.room.connect(livekitUrl, token);
            console.log('✓ Connected to room');

            // Set up local audio
            await this.setupLocalAudio();

            this.isConnected = true;
            this.updateStatus('connected', 'Connected');
            this.connectionInfo.innerHTML = `
                <p>✓ Connected! Start speaking to interact with the assistant.</p>
                <p class="info-detail"><strong>Room:</strong> ${this.room.name}</p>
            `;
            this.waveContainer.classList.add('active');

            // Enable/disable buttons
            this.connectBtn.disabled = true;
            this.disconnectBtn.disabled = false;
            this.muteBtn.disabled = false;

            console.log('✅ Ready to interact!');

        } catch (error) {
            console.error('❌ Connection error:', error);
            this.updateStatus('disconnected', 'Connection Failed');
            this.connectionInfo.innerHTML = `<p style="color: var(--danger-color);">Connection failed: ${error.message}</p>`;
            alert('Connection failed. Please check that backend and LiveKit servers are running.');
        }
    }

    async getAccessToken(roomName, participantName) {
        let apiBaseUrl = window.location.origin;
        if (!apiBaseUrl.startsWith('http')) {
            apiBaseUrl = 'http://localhost:5000';
        }

        const response = await fetch(`${apiBaseUrl}/api/token`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ roomName, participantName }),
        });

        if (!response.ok) {
            throw new Error('Failed to get access token');
        }

        return await response.json();
    }

    setupRoomEventListeners() {
        console.log('📡 Setting up event listeners...');

        // Track subscribed - play agent audio
        this.room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            console.log(`🎧 Track subscribed from ${participant.identity}`);
            
            if (track.kind === LivekitClient.Track.Kind.Audio) {
                const audioElement = track.attach();
                audioElement.autoplay = true;
                document.body.appendChild(audioElement);
                console.log('✓ Agent audio element attached');
            }
        });

        // Track unsubscribed
        this.room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track) => {
            track.detach().forEach(element => element.remove());
        });

        // Data received - Handle transcriptions and transfer requests
        this.room.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {
            const decoder = new TextDecoder();
            const data = JSON.parse(decoder.decode(payload));
            
            console.log('📦 Data received:', data.type, data);

            if (data.type === 'transcription') {
                this.handleTranscription(data);
            } else if (data.type === 'transfer_request') {
                this.handleTransferRequest(data);
            }
        });

        // Participant events
        this.room.on(LivekitClient.RoomEvent.ParticipantConnected, (participant) => {
            console.log(`👤 Participant connected: ${participant.identity}`);
        });

        this.room.on(LivekitClient.RoomEvent.Disconnected, (reason) => {
            console.log('🔌 Disconnected:', reason);
            this.handleDisconnection();
        });

        console.log('✓ Event listeners configured');
    }

    handleTranscription(data) {
        /**
         * Handle real-time transcription data
         * - Updates partial transcripts in-place
         * - Finalizes complete sentences
         */
        const { role, text, isFinal, language } = data;
        
        if (!text || text.trim() === '') return;

        // Update language indicator
        this.updateLanguageIndicator(language || 'en');

        // Remove empty state if present
        const emptyState = this.transcriptionContent.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        if (role === 'user') {
            this.handleUserTranscript(text, isFinal, language);
        } else if (role === 'assistant') {
            this.handleAssistantTranscript(text, isFinal, language);
        }

        // Auto-scroll to bottom
        this.transcriptionContent.scrollTop = this.transcriptionContent.scrollHeight;
    }

    handleUserTranscript(text, isFinal, language) {
        /**
         * Handle user transcriptions with partial updates
         */
        if (!isFinal) {
            // Update or create partial transcript
            if (this.currentUserPartial) {
                // Update existing partial
                const messageText = this.currentUserPartial.querySelector('.message-text');
                messageText.textContent = text;
                messageText.classList.add('partial');
            } else {
                // Create new partial message
                const messageDiv = this.createTranscriptMessage('user', text, language, false);
                this.transcriptionContent.appendChild(messageDiv);
                this.currentUserPartial = messageDiv;
            }
        } else {
            // Final transcript - update or create
            if (this.currentUserPartial) {
                // Update the partial to final
                const messageText = this.currentUserPartial.querySelector('.message-text');
                messageText.textContent = text;
                messageText.classList.remove('partial');
                
                const timeEl = this.currentUserPartial.querySelector('.message-time');
                timeEl.textContent = this.getCurrentTimeString();
                
                this.currentUserPartial.dataset.final = 'true';
                this.currentUserPartial = null;
            } else {
                // Create new final message
                const messageDiv = this.createTranscriptMessage('user', text, language, true);
                this.transcriptionContent.appendChild(messageDiv);
            }
            
            // Save to history
            this.transcripts.push({
                role: 'user',
                text: text,
                timestamp: new Date(),
                language: language
            });

            console.log('💬 User (final):', text);
        }
    }

    handleAssistantTranscript(text, isFinal, language) {
        /**
         * Handle assistant transcriptions (usually only final)
         */
        if (isFinal) {
            // Create or update final assistant message
            const messageDiv = this.createTranscriptMessage('assistant', text, language, true);
            this.transcriptionContent.appendChild(messageDiv);
            
            // Save to history
            this.transcripts.push({
                role: 'assistant',
                text: text,
                timestamp: new Date(),
                language: language
            });

            console.log('🤖 Assistant:', text);
        }
    }

    handleTransferRequest(data) {
        /**
         * Handle transfer to human agent requests
         */
        console.log('📞 Transfer request:', data.reason);
        
        // Show notification
        const notification = document.createElement('div');
        notification.className = 'transfer-notification';
        notification.innerHTML = `
            <div class="transfer-icon">📞</div>
            <div class="transfer-text">
                <strong>Transfer Requested</strong>
                <p>${data.reason}</p>
            </div>
        `;
        
        this.transcriptionContent.appendChild(notification);
        this.transcriptionContent.scrollTop = this.transcriptionContent.scrollHeight;
        
        // You could add actual transfer logic here
        // e.g., open a modal, initiate SIP transfer, etc.
    }

    createTranscriptMessage(role, text, language, isFinal) {
        /**
         * Create a chat-like message bubble
         */
        const messageDiv = document.createElement('div');
        messageDiv.className = `transcript-message ${role}`;
        messageDiv.dataset.role = role;
        messageDiv.dataset.final = isFinal ? 'true' : 'false';
        messageDiv.dataset.language = language || 'en';

        const timeString = isFinal ? this.getCurrentTimeString() : '';
        const partialClass = !isFinal ? 'partial' : '';

        // Icon for role
        const icon = role === 'user' ? '👤' : '🤖';

        messageDiv.innerHTML = `
            <div class="message-avatar">${icon}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-label">${role === 'user' ? 'You' : 'Assistant'}</span>
                    <span class="message-time">${timeString}</span>
                </div>
                <div class="message-text ${partialClass}">${this.escapeHtml(text)}</div>
            </div>
        `;

        return messageDiv;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async setupLocalAudio() {
        try {
            console.log('🎤 Setting up microphone...');
            
            this.localAudioTrack = await LivekitClient.createLocalAudioTrack({
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            });
            console.log('✓ Audio track created');

            await this.room.localParticipant.publishTrack(this.localAudioTrack);
            console.log('✓ Audio track published');

        } catch (error) {
            console.error('❌ Microphone setup failed:', error);
            alert(`Failed to access microphone: ${error.message}\n\nPlease grant microphone permissions and try again.`);
            throw error;
        }
    }

    async disconnect() {
        console.log('🔌 Disconnecting...');
        
        if (this.localAudioTrack) {
            try {
                await this.room.localParticipant.unpublishTrack(this.localAudioTrack);
            } catch (error) {
                console.warn('Error unpublishing track:', error);
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

        this.connectBtn.disabled = false;
        this.disconnectBtn.disabled = true;
        this.muteBtn.disabled = true;

        this.isMuted = false;
        this.updateMuteButton();

        if (this.localAudioTrack) {
            this.localAudioTrack.stop();
            this.localAudioTrack = null;
        }

        this.room = null;
        this.currentUserPartial = null;
        this.currentAssistantPartial = null;
        
        console.log('✓ Disconnected');
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

    getCurrentTimeString() {
        const now = new Date();
        return now.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    detectLanguage(text) {
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
            this.currentUserPartial = null;
            this.currentAssistantPartial = null;
            this.transcriptionContent.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">💬</div>
                    <p>Conversation transcription will appear here</p>
                </div>
            `;
            console.log('🗑️ Transcripts cleared');
        }
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('='.repeat(80));
    console.log('EV CHARGING VOICE ASSISTANT - PRODUCTION MODE');
    console.log('='.repeat(80));
    
    if (typeof LivekitClient === 'undefined') {
        console.error('❌ LivekitClient not loaded!');
        alert('Error: LiveKit client library failed to load. Please refresh the page.');
        return;
    }

    console.log('✓ LivekitClient loaded');
    window.app = new EVChargingApp();
    console.log('✓ App ready');
    console.log('='.repeat(80));
});