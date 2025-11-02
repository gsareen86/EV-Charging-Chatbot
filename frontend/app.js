/**
 * EV Charging Voice Assistant - FIXED & DEBUGGED VERSION
 * Issues Fixed:
 * 1. Live transcriptions now display correctly
 * 2. Speaking indicators work properly
 * 3. Auto-disconnect fixed with better keyword detection
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
        
        // Auto-disconnect keywords (more comprehensive)
        this.goodbyeKeywords = [
            'goodbye', 'good bye', 'bye', 'by', 'thank you', 'thanks', 'thankyou',
            'thats all', 'that\'s all', 'nothing else', 'no more', 'all done',
            'im done', 'i\'m done', 'done', 'ok bye', 'okay bye',
            'धन्यवाद', 'शुक्रिया', 'अलविदा', 'धन्यवाद'
        ];

        this.initializeElements();
        this.attachEventListeners();
        this.loadThemePreference();
        
        console.log('🚀 EV Charging App initialized - DEBUG MODE');
        console.log('📋 Auto-disconnect keywords:', this.goodbyeKeywords);
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
            console.log('🎤 Speak into your microphone to test...');

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
       ROOM EVENT LISTENERS - FIXED!
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
                
                // Show speaking indicator when agent audio plays
                this.showSpeakingIndicator('assistant', 2000); // Show for 2 seconds
            }
        });

        // Track unsubscribed
        this.room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track) => {
            console.log('🔇 Track unsubscribed');
            track.detach().forEach(element => element.remove());
        });

        // DATA RECEIVED - This is critical for transcriptions!
        this.room.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {
            try {
                const decoder = new TextDecoder();
                const dataString = decoder.decode(payload);
                const data = JSON.parse(dataString);
                
                console.log('📦 DATA RECEIVED:', {
                    type: data.type,
                    role: data.role,
                    text: data.text?.substring(0, 50) + '...',
                    isFinal: data.isFinal,
                    fullData: data
                });

                if (data.type === 'transcription') {
                    this.handleTranscription(data);
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
       TRANSCRIPTION HANDLING - FIXED!
       ==================================== */

    handleTranscription(data) {
        const { role, text, isFinal, language } = data;
        
        // DEBUG: Log everything
        console.log(`\n${'='.repeat(60)}`);
        console.log(`📝 TRANSCRIPTION RECEIVED:`);
        console.log(`   Role: ${role}`);
        console.log(`   Text: "${text}"`);
        console.log(`   Final: ${isFinal}`);
        console.log(`   Language: ${language}`);
        console.log(`${'='.repeat(60)}\n`);
        
        if (!text || text.trim() === '') {
            console.log('⚠️ Empty text, skipping...');
            return;
        }

        // Update language indicator
        this.updateLanguageIndicator(language || 'en');

        // Remove empty state if present
        const emptyState = this.transcriptionContent.querySelector('.empty-state');
        if (emptyState) {
            console.log('🗑️ Removing empty state');
            emptyState.remove();
        }

        // Show speaking indicator based on role and finality
        if (role === 'user') {
            if (!isFinal) {
                this.showSpeakingIndicator('user', null); // Show until final
            } else {
                this.hideSpeakingIndicator(); // Hide when user done
            }
        } else if (role === 'assistant' && isFinal) {
            this.showSpeakingIndicator('assistant', 3000); // Show for 3 seconds
        }

        // Handle transcripts
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
            // Handle partial transcript
            if (this.currentUserPartial) {
                // Update existing partial message
                const messageText = this.currentUserPartial.querySelector('.message-text');
                messageText.textContent = text;
                console.log('   ↻ Updated partial message');
            } else {
                // Create new partial message
                this.currentUserPartial = this.createTranscriptMessage('user', text, language, false);
                this.transcriptionContent.appendChild(this.currentUserPartial);
                console.log('   + Created new partial message');
            }
        } else {
            // Final transcript
            if (this.currentUserPartial) {
                // Finalize existing partial
                const messageText = this.currentUserPartial.querySelector('.message-text');
                messageText.textContent = text;
                messageText.classList.remove('partial');
                
                const messageTime = this.currentUserPartial.querySelector('.message-time');
                messageTime.textContent = this.getCurrentTimeString();
                
                this.currentUserPartial.dataset.final = 'true';
                console.log('   ✓ Finalized partial message');
                this.currentUserPartial = null;
            } else {
                // Create new final message
                const message = this.createTranscriptMessage('user', text, language, true);
                this.transcriptionContent.appendChild(message);
                console.log('   + Created new final message');
            }
            
            // Check for goodbye intent
            console.log('🔍 Checking for goodbye intent...');
            this.checkGoodbyeIntent(text);
        }
    }

    handleAssistantTranscript(text, isFinal, language) {
        console.log(`🤖 ASSISTANT TRANSCRIPT: isFinal=${isFinal}`);
        
        if (isFinal) {
            // Create new final message
            const message = this.createTranscriptMessage('assistant', text, language, true);
            this.transcriptionContent.appendChild(message);
            console.log('   + Created assistant message');
            
            this.currentAssistantPartial = null;
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
       SPEAKING INDICATOR - FIXED!
       ==================================== */

    showSpeakingIndicator(speaker, duration) {
        console.log(`🌊 Showing speaking indicator for: ${speaker}, duration: ${duration}ms`);
        
        this.currentSpeaker = speaker;
        this.speakingIndicator.classList.add('active');
        
        if (speaker === 'user') {
            this.speakerAvatar.textContent = '👤';
            this.speakerName.textContent = 'You';
        } else {
            this.speakerAvatar.textContent = '🤖';
            this.speakerName.textContent = 'AI Assistant';
        }

        // Clear any existing timeout
        if (this.speakingTimeout) {
            clearTimeout(this.speakingTimeout);
        }

        // Auto-hide after duration (if specified)
        if (duration) {
            this.speakingTimeout = setTimeout(() => {
                this.hideSpeakingIndicator();
            }, duration);
        }
    }

    hideSpeakingIndicator() {
        console.log('🔇 Hiding speaking indicator');
        this.speakingIndicator.classList.remove('active');
        this.currentSpeaker = null;
        
        if (this.speakingTimeout) {
            clearTimeout(this.speakingTimeout);
            this.speakingTimeout = null;
        }
    }

    /* ====================================
       AUTO-DISCONNECT - FIXED!
       ==================================== */

    checkGoodbyeIntent(text) {
        const lowerText = text.toLowerCase().trim();
        
        console.log(`\n${'='.repeat(60)}`);
        console.log(`🔍 CHECKING GOODBYE INTENT`);
        console.log(`   User said: "${text}"`);
        console.log(`   Normalized: "${lowerText}"`);
        
        // Check each keyword
        let matchedKeyword = null;
        for (const keyword of this.goodbyeKeywords) {
            if (lowerText.includes(keyword.toLowerCase())) {
                matchedKeyword = keyword;
                break;
            }
        }
        
        if (matchedKeyword) {
            console.log(`   ✅ MATCH FOUND: "${matchedKeyword}"`);
            console.log(`   👋 Initiating auto-disconnect...`);
            console.log(`${'='.repeat(60)}\n`);
            
            // Show farewell message
            this.showFarewellMessage();
            
            // Disconnect after delay
            setTimeout(() => {
                console.log('📞 Auto-disconnecting now...');
                this.disconnect(true);
            }, 3000);
        } else {
            console.log(`   ❌ No goodbye keywords detected`);
            console.log(`${'='.repeat(60)}\n`);
        }
    }

    showFarewellMessage() {
        console.log('👋 Showing farewell message');
        
        // Show toast notification
        const toastText = this.autoDisconnectToast.querySelector('.toast-text p');
        toastText.textContent = 'You were talking to "AI Assistant". Have a great day!';
        
        this.autoDisconnectToast.classList.add('show');
        
        // Hide after 5 seconds
        setTimeout(() => {
            this.autoDisconnectToast.classList.remove('show');
        }, 5000);

        // Add to transcription
        const farewellDiv = document.createElement('div');
        farewellDiv.className = 'transfer-notification';
        farewellDiv.innerHTML = `
            <div class="transfer-icon">👋</div>
            <div class="transfer-text">
                <strong>Call Ending</strong>
                <p>Thank you for using our service! The call will disconnect shortly.</p>
            </div>
        `;
        
        this.transcriptionContent.appendChild(farewellDiv);
        this.transcriptionContent.scrollTop = this.transcriptionContent.scrollHeight;
    }

    /* ====================================
       TRANSFER REQUEST
       ==================================== */

    handleTransferRequest(data) {
        console.log('📞 Transfer request:', data.reason);
        
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
    console.log('EV CHARGING VOICE ASSISTANT - FIXED & DEBUGGED VERSION');
    console.log('='.repeat(80));
    console.log('');
    console.log('🐛 DEBUG MODE ENABLED');
    console.log('   - Detailed logging for transcriptions');
    console.log('   - Speaking indicator debugging');
    console.log('   - Auto-disconnect keyword matching');
    console.log('');
    
    if (typeof LivekitClient === 'undefined') {
        console.error('❌ LivekitClient not loaded!');
        alert('Error: LiveKit client library failed to load. Please refresh the page.');
        return;
    }

    console.log('✓ LivekitClient loaded successfully');
    console.log('  Available:', Object.keys(LivekitClient).slice(0, 5).join(', '), '...');
    console.log('');
    
    window.app = new EVChargingApp();
    
    console.log('✓ App initialized and ready');
    console.log('');
    console.log('📝 TROUBLESHOOTING TIPS:');
    console.log('   1. Connect to the room');
    console.log('   2. Speak into your microphone');
    console.log('   3. Watch console for "📦 DATA RECEIVED" messages');
    console.log('   4. If no data received, check backend is running');
    console.log('   5. Say "goodbye" or "thank you" to test auto-disconnect');
    console.log('');
    console.log('='.repeat(80));
});