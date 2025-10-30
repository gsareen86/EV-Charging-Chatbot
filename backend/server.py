"""
Flask server for EV Charging Chatbot
Handles token generation and serves the frontend
"""
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from livekit import api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='../frontend')
CORS(app)

# LiveKit configuration
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY', 'devkey')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET', 'secret')
LIVEKIT_URL = os.getenv('LIVEKIT_URL', 'ws://localhost:7880')


@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('../frontend', 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files (CSS, JS, etc.)"""
    return send_from_directory('../frontend', path)


@app.route('/api/token', methods=['POST'])
def generate_token():
    """
    Generate LiveKit access token for a participant

    Request body:
    {
        "roomName": "room-name",
        "participantName": "participant-name"
    }
    """
    try:
        data = request.get_json()

        room_name = data.get('roomName')
        participant_name = data.get('participantName')

        if not room_name or not participant_name:
            return jsonify({
                'error': 'roomName and participantName are required'
            }), 400

        # Create access token
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
            .with_identity(participant_name) \
            .with_name(participant_name) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))

        jwt_token = token.to_jwt()

        return jsonify({
            'token': jwt_token,
            'url': LIVEKIT_URL,
            'roomName': room_name,
            'participantName': participant_name
        })

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'EV Charging Chatbot API',
        'livekit_url': LIVEKIT_URL
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get public configuration"""
    return jsonify({
        'livekit_url': LIVEKIT_URL,
        'supported_languages': ['en', 'hi']
    })


if __name__ == '__main__':
    # Print startup information
    print("=" * 60)
    print("EV Charging Voice Chatbot - Flask Server")
    print("=" * 60)
    print(f"LiveKit URL: {LIVEKIT_URL}")
    print(f"Server running on: http://localhost:5000")
    print("=" * 60)

    # Run the server
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
