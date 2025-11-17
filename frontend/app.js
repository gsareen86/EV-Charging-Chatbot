/**
 * EV Charging Voice Assistant - STREAMING OPTIMIZED VERSION
 * Features:
 * 1. Real-time streaming transcriptions (partial + final) for both user and assistant
 * 2. Speaking indicators
 * 3. Inline status messages
 * 4. Auto-disconnect functionality
 * 5. Proper turn attribution for AI assistant messages
 */

class EVChargingApp {
    constructor() {
        this.room = null;
        this.isConnected = false;
        this.isMuted = false;
        this.localAudioTrack = null;
        this.transcripts = [];
        
        // Track current partial transcriptions
        this.currentUserPartial = null;
        this.currentAssistantPartial = null;
        
        // Track speaking state
        this.currentSpeaker = null;
        this.speakingTimeout = null;
        
        // Track current status for inline display
        this.currentStatusElement = null;
        
        // Auto-disconnect keywords
        this.goodbyeKeywords = [
            'goodbye', 'good bye', 'bye', 'by', 'thank you', 'thanks', 'thankyou',
            'thats all', 'that\'s all', 'nothing else', 'no more', 'all done',
            'im done', 'i\'m done', 'done', 'ok bye', 'okay bye',
            'धन्यवाद', 'शुक्रिया', 'अलविदा'
        ];

        this.initializeElements();
        this.attachEventListeners();
        this.loadThemePreference();
        
        console.log('🚀 EV Charging App initialized - STREAMING OPTIMIZED MODE');
        console.log('✨ New features: Real-time streaming for user & assistant');
    }

    initializeElements() {
        // Buttons
        this.connectBtn = document.getElementById('connectBtn');
        this.disconnectBtn = document.getElementById('disconnectBtn');
        this.muteBtn = document.getElementById('muteBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.cancelBtn = document.getElementById('cancelBtn');
        this.themeToggle = document.getElementById('themeToggle');

        // Status elements
        this.connectionStatus = document.getElementById('connectionStatus');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.connectionInfo = document.getElementById('connectionInfo');

        // Transcription elements
        this.transcriptionContent = document.getElementById('transcriptionContent');
        this.languageIndicator = document.getElementById('languageIndicator');
        this.speakingIndicator = document.getElementById('speakingIndicator');
        this.speakerAvatar = document.getElementById('speakerAvatar');
        this.speakerName = document.getElementById('speakerName');

        // Modal elements
        this.connectionModal = document.getElementById('connectionModal');
        this.connectionForm = document.getElementById('connectionForm');
        this.roomNameInput = document.getElementById('roomName');
        this.participantNameInput = document.getElementById('participantName');
        
        // Toast notification
        this.autoDisconnectToast = document.getElementById('autoDisconnectToast');
    }

    attachEventListeners() {
        this.connectBtn.addEventListener('click', () => this.showConnectionModal());
        this.disconnectBtn.addEventListener('click', () => this.disconnect());
        this.muteBtn.addEventListener('click', () => this.toggleMute());
        this.clearBtn.addEventListener('click', () => this.clearTranscripts());
        this.cancelBtn.addEventListener('click', () => this.hideConnectionModal());
        this.connectionForm.addEventListener('submit', (e) => this.handleConnectionSubmit(e));
        this.themeToggle.addEventListener('click', () => this.toggleTheme());
    }

    /* ====================================
       THEME TOGGLE
       ==================================== */

    loadThemePreference() {
        const savedTheme = localStorage.getItem('ev-assistant-theme') || 'light';
        this.setTheme(savedTheme);
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
    }

    setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('ev-assistant-theme', theme);
        
        const themeIcon = this.themeToggle.querySelector('.theme-icon');
        themeIcon.textContent = theme === 'light' ? '🌙' : '☀️';
    }

    /* ====================================
       CONNECTION MANAGEMENT
       ==================================== */

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
            this.connectionInfo.innerHTML = '<p>🔄 Connecting to voice assistant...</p>';

            // Get access token
            const connectionConfig = await this.getAccessToken(roomName, participantName);
            const { token, url: livekitUrl } = connectionConfig;
            console.log(`✓ Token received for room: ${roomName}`);

            // Initialize LiveKit room
            this.room = new LivekitClient.Room({
                adaptiveStream: true,
                dynacast: true,
            });

            // Set up event listeners BEFORE connecting
            this.setupRoomEventListeners();

            // Connect to the room
            await this.room.connect(livekitUrl, token);
            console.log('✓ Connected to room:', this.room.name);

            // Set up local audio
            await this.setupLocalAudio();

            this.isConnected = true;
            this.updateStatus('connected', 'Connected');
            this.connectionInfo.innerHTML = `
                <p>✅ Connected! Start speaking to interact with the assistant.</p>
                <p class="info-detail"><strong>Room:</strong> ${this.room.name}</p>
            `;

            // Enable/disable buttons
            this.connectBtn.disabled = true;
            this.disconnectBtn.disabled = false;
            this.muteBtn.disabled = false;

            console.log('✅ Ready to interact!');

        } catch (error) {
            console.error('❌ Connection error:', error);
            this.updateStatus('disconnected', 'Connection Failed');
            this.connectionInfo.innerHTML = `<p style="color: var(--danger-color);">⚠️ Connection failed: ${error.message}</p>`;
            alert('Connection failed. Please check that backend and LiveKit servers are running.');
        }
    }

    async getAccessToken(roomName, participantName) {
        let apiBaseUrl = window.location.origin;
        if (!apiBaseUrl.startsWith('http')) {
            apiBaseUrl = 'http://localhost:5000';
        }

        console.log('🔑 Requesting token from:', `${apiBaseUrl}/api/token`);

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

    /* ====================================
       ROOM EVENT LISTENERS
       ==================================== */

    setupRoomEventListeners() {
        console.log('📡 Setting up event listeners...');

        // Track subscribed - play agent audio
        this.room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            console.log(`🎧 Track subscribed from ${participant.identity}, kind: ${track.kind}`);
            
            if (track.kind === LivekitClient.Track.Kind.Audio) {
                const audioElement = track.attach();
                audioElement.autoplay = true;
                document.body.appendChild(audioElement);
                console.log('✓ Agent audio element attached and playing');
                
                this.showSpeakingIndicator('assistant', 2000);
            }
        });

        // Track unsubscribed
        this.room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track) => {
            console.log('🔇 Track unsubscribed');
            track.detach().forEach(element => element.remove());
        });

        // DATA RECEIVED - Handle transcriptions and status updates
        this.room.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {
            try {
                const decoder = new TextDecoder();
                const dataString = decoder.decode(payload);
                const data = JSON.parse(dataString);
                
                console.log('📦 DATA RECEIVED:', {
                    type: data.type,
                    role: data.role || data.status_type,
                    isFinal: data.isFinal,
                    preview: (data.text || data.status || '').substring(0, 50),
                });

                if (data.type === 'transcription') {
                    this.handleTranscription(data);
                } else if (data.type === 'status_update') {
                    this.handleStatusUpdate(data);
                } else if (data.type === 'transfer_request') {
                    this.handleTransferRequest(data);
                } else {
                    console.log('⚠️ Unknown data type:', data.type);
                }
            } catch (error) {
                console.error('❌ Error processing data:', error);
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

        console.log('✓ Event listeners configured successfully');
    }

    /* ====================================
       STATUS MESSAGE HANDLING (IMPROVED - INLINE STYLE)
       ==================================== */

    handleStatusUpdate(data) {
        const { status, status_type } = data;
        
        console.log(`📢 STATUS UPDATE: "${status}" (type: ${status_type})`);
        
        // Show status message inline with assistant messages
        this.showInlineStatus(status, status_type);
    }

    showInlineStatus(message, type = 'searching') {
        // Remove existing status if any
        if (this.currentStatusElement) {
            this.currentStatusElement.remove();
            this.currentStatusElement = null;
        }

        // Don't show "Search complete" messages
        if (type === 'complete') {
            return;
        }

        // Create inline status element (simple glowing text)
        const statusSpan = document.createElement('span');
        statusSpan.className = `inline-status inline-status-${type}`;
        
        // Set icon based on type
        let icon = '🔍';
        if (type === 'searching') {
            icon = '🔍';
        } else if (type === 'synthesizing') {
            icon = '🎤';
        } else if (type === 'error') {
            icon = '⚠️';
        }

        statusSpan.textContent = `${icon} ${message}`;
        
        // Store reference
        this.currentStatusElement = statusSpan;

        // Append to transcription content (will be moved to assistant message later)
        this.transcriptionContent.appendChild(statusSpan);
        this.transcriptionContent.scrollTop = this.transcriptionContent.scrollHeight;

        console.log(`✨ Inline status displayed: "${message}"`);
    }

    hideInlineStatus() {
        if (this.currentStatusElement) {
            this.currentStatusElement.classList.add('fade-out');
            setTimeout(() => {
                if (this.currentStatusElement && this.currentStatusElement.parentNode) {
                    this.currentStatusElement.remove();
                }
                this.currentStatusElement = null;
            }, 300);
        }
    }

    /* ====================================
       TRANSCRIPTION HANDLING - WITH STREAMING SUPPORT
       ==================================== */

    handleTranscription(data) {
        const { role, text, isFinal, language } = data;
        
        console.log(`\n${'='.repeat(60)}`);
        console.log(`📝 TRANSCRIPTION RECEIVED:`);
        console.log(`   Role: ${role}`);
        console.log(`   Text: "${text}"`);
        console.log(`   Final: ${isFinal}`);
        console.log(`${'='.repeat(60)}\n`);
        
        if (!text || text.trim() === '') {
            return;
        }

        // Update language indicator
        this.updateLanguageIndicator(language || 'en');

        // Remove empty state if present
        const emptyState = this.transcriptionContent.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        // Show speaking indicator
        if (role === 'user') {
            if (!isFinal) {
                this.showSpeakingIndicator('user', null);
            } else {
                this.hideSpeakingIndicator();
            }
        } else if (role === 'assistant') {
            if (!isFinal) {
                this.showSpeakingIndicator('assistant', null);
            } else {
                // Hide status when assistant final response arrives
                this.hideInlineStatus();
                // Keep speaking indicator for a bit longer
                this.showSpeakingIndicator('assistant', 2000);
            }
        }

        // Handle transcripts with streaming support
        if (role === 'user') {
            this.handleUserTranscript(text, isFinal, language);
        } else if (role === 'assistant') {
            this.handleAssistantTranscript(text, isFinal, language);
        }

        // Auto-scroll to bottom
        this.transcriptionContent.scrollTop = this.transcriptionContent.scrollHeight;
    }

    handleUserTranscript(text, isFinal, language) {
        console.log(`👤 USER TRANSCRIPT: isFinal=${isFinal}`);
        
        if (!isFinal) {
            // Handle partial transcriptions - UPDATE EXISTING OR CREATE NEW
            if (this.currentUserPartial) {
                const messageText = this.currentUserPartial.querySelector('.message-text');
                messageText.textContent = text;
            } else {
                this.currentUserPartial = this.createTranscriptMessage('user', text, language, false);
                this.transcriptionContent.appendChild(this.currentUserPartial);
            }
        } else {
            // Handle final transcription
            if (this.currentUserPartial) {
                // Update existing partial to final
                const messageText = this.currentUserPartial.querySelector('.message-text');
                messageText.textContent = text;
                messageText.classList.remove('partial');
                
                const messageTime = this.currentUserPartial.querySelector('.message-time');
                messageTime.textContent = this.getCurrentTimeString();
                
                this.currentUserPartial.dataset.final = 'true';
                this.currentUserPartial = null;
            } else {
                // Create new final message
                const message = this.createTranscriptMessage('user', text, language, true);
                this.transcriptionContent.appendChild(message);
            }
            
            this.checkGoodbyeIntent(text);
        }
    }

    handleAssistantTranscript(text, isFinal, language) {
        console.log(`🤖 ASSISTANT TRANSCRIPT: isFinal=${isFinal}, partialExists=${!!this.currentAssistantPartial}`);
        
        if (!isFinal) {
            // Handle STREAMING partial transcriptions from agent_speech event
            if (this.currentAssistantPartial) {
                // Update existing partial message
                const messageText = this.currentAssistantPartial.querySelector('.message-text');
                messageText.textContent = text;
                console.log(`   ↻ Updated partial assistant message: "${text.substring(0, 50)}..."`);
            } else {
                // Create new partial message
                this.currentAssistantPartial = this.createTranscriptMessage('assistant', text, language, false);
                
                // If there's a status element, move it into this message
                if (this.currentStatusElement && this.currentStatusElement.parentNode) {
                    const messageContent = this.currentAssistantPartial.querySelector('.message-content');
                    // Insert status before the message text
                    messageContent.insertBefore(this.currentStatusElement, messageContent.querySelector('.message-text'));
                }
                
                this.transcriptionContent.appendChild(this.currentAssistantPartial);
                console.log(`   ✚ Created new partial assistant message: "${text.substring(0, 50)}..."`);
            }
        } else {
            // Handle final transcription
            if (this.currentAssistantPartial) {
                // Update existing partial to final
                const messageText = this.currentAssistantPartial.querySelector('.message-text');
                messageText.textContent = text;
                messageText.classList.remove('partial');
                
                const messageTime = this.currentAssistantPartial.querySelector('.message-time');
                messageTime.textContent = this.getCurrentTimeString();
                
                this.currentAssistantPartial.dataset.final = 'true';
                this.currentAssistantPartial = null;
                console.log(`   ✓ Finalized assistant message: "${text.substring(0, 50)}..."`);
            } else {
                // Create new final message (fallback)
                const message = this.createTranscriptMessage('assistant', text, language, true);
                
                // If there's a status element, move it into this message
                if (this.currentStatusElement && this.currentStatusElement.parentNode) {
                    const messageContent = message.querySelector('.message-content');
                    messageContent.insertBefore(this.currentStatusElement, messageContent.querySelector('.message-text'));
                    this.currentStatusElement = null;
                }
                
                this.transcriptionContent.appendChild(message);
                console.log(`   ✚ Created new final assistant message: "${text.substring(0, 50)}..."`);
            }
        }
    }

    createTranscriptMessage(role, text, language, isFinal) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `transcript-message ${role}`;
        messageDiv.dataset.role = role;
        messageDiv.dataset.final = isFinal ? 'true' : 'false';
        messageDiv.dataset.language = language || 'en';

        const timeString = isFinal ? this.getCurrentTimeString() : '';
        const partialClass = !isFinal ? 'partial' : '';
        const icon = role === 'user' ? '👤' : '🤖';
        const label = role === 'user' ? 'You' : 'AI Assistant';

        messageDiv.innerHTML = `
            <div class="message-avatar">${icon}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-label">${label}</span>
                    <span class="message-time">${timeString}</span>
                </div>
                <div class="message-text ${partialClass}">${this.escapeHtml(text)}</div>
            </div>
        `;

        return messageDiv;
    }

    /* ====================================
       SPEAKING INDICATOR
       ==================================== */

    showSpeakingIndicator(speaker, duration) {
        console.log(`🗣️  Showing speaking indicator for: ${speaker}`);
        
        this.currentSpeaker = speaker;
        
        if (speaker === 'user') {
            this.speakerAvatar.textContent = '👤';
            this.speakerName.textContent = 'You';
        } else {
            this.speakerAvatar.textContent = '🤖';
            this.speakerName.textContent = 'AI Assistant';
        }
        
        this.speakingIndicator.classList.add('active');
        
        if (this.speakingTimeout) {
            clearTimeout(this.speakingTimeout);
        }
        
        if (duration) {
            this.speakingTimeout = setTimeout(() => {
                this.hideSpeakingIndicator();
            }, duration);
        }
    }

    hideSpeakingIndicator() {
        console.log('🛑 Hiding speaking indicator');
        this.speakingIndicator.classList.remove('active');
        this.currentSpeaker = null;
        
        if (this.speakingTimeout) {
            clearTimeout(this.speakingTimeout);
            this.speakingTimeout = null;
        }
    }

    /* ====================================
       AUTO-DISCONNECT
       ==================================== */

    checkGoodbyeIntent(text) {
        const normalizedText = text.toLowerCase().trim();
        console.log(`🔍 Checking for goodbye in: "${normalizedText}"`);
        
        const hasGoodbye = this.goodbyeKeywords.some(keyword => {
            const hasMatch = normalizedText.includes(keyword);
            if (hasMatch) {
                console.log(`   ✓ Match found: "${keyword}"`);
            }
            return hasMatch;
        });
        
        if (hasGoodbye) {
            console.log('👋 GOODBYE DETECTED! Auto-disconnecting in 3 seconds...');
            this.showAutoDisconnectToast();
            
            setTimeout(() => {
                this.disconnect(true);
            }, 3000);
        }
    }

    showAutoDisconnectToast() {
        this.autoDisconnectToast.classList.add('show');
        
        setTimeout(() => {
            this.autoDisconnectToast.classList.remove('show');
        }, 3500);
    }

    /* ====================================
       TRANSFER REQUEST
       ==================================== */

    handleTransferRequest(data) {
        console.log('📞 Transfer request received:', data.reason);
        
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
    }

    /* ====================================
       AUDIO SETUP
       ==================================== */

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

    /* ====================================
       DISCONNECT
       ==================================== */

    async disconnect(isAutoDisconnect = false) {
        console.log(isAutoDisconnect ? '👋 Auto-disconnecting...' : '🔌 Manual disconnect...');
        
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
        this.connectionInfo.innerHTML = '<p>👆 Click "Connect" to start your voice conversation</p>';

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
        this.currentSpeaker = null;
        
        this.hideSpeakingIndicator();
        this.hideInlineStatus();
        
        console.log('✓ Disconnected and cleaned up');
    }

    /* ====================================
       MUTE TOGGLE
       ==================================== */

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

    /* ====================================
       UTILITY FUNCTIONS
       ==================================== */

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

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    clearTranscripts() {
        if (this.transcripts.length === 0 && 
            !this.transcriptionContent.querySelector('.transcript-message')) {
            return;
        }

        if (confirm('Are you sure you want to clear the conversation history?')) {
            this.transcripts = [];
            this.currentUserPartial = null;
            this.currentAssistantPartial = null;
            this.hideInlineStatus();
            
            this.transcriptionContent.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">💬</div>
                    <p>Your conversation will appear here</p>
                    <p class="empty-subtitle">Connect to start talking with our AI assistant</p>
                </div>
            `;
            console.log('🗑️ Conversation cleared');
        }
    }
}

/* ====================================
   INITIALIZE APP
   ==================================== */

document.addEventListener('DOMContentLoaded', () => {
    console.log('='.repeat(80));
    console.log('EV CHARGING VOICE ASSISTANT - STREAMING OPTIMIZED');
    console.log('='.repeat(80));
    console.log('');
    console.log('✨ IMPROVEMENTS:');
    console.log('   - Real-time streaming transcriptions (partial + final)');
    console.log('   - Both user and assistant messages stream');
    console.log('   - Inline status messages');
    console.log('   - Fixed turn attribution');
    console.log('');
    
    if (typeof LivekitClient === 'undefined') {
        console.error('❌ LivekitClient not loaded!');
        alert('Error: LiveKit client library failed to load. Please refresh the page.');
        return;
    }

    console.log('✓ LivekitClient loaded successfully');
    console.log('');
    
    window.app = new EVChargingApp();
    
    console.log('✓ App initialized and ready');
    console.log('='.repeat(80));
});