from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# In-memory store: list of { player, message, time }
greetings = []


@app.route('/api/greet', methods=['POST'])
def post_greet():
    data = request.get_json(force=True, silent=True) or {}
    player = str(data.get('player', '')).strip()
    message = str(data.get('message', '')).strip()

    if not player or not message:
        return jsonify({'error': 'player and message are required'}), 400

    entry = {
        'player': player,
        'message': message,
        'time': datetime.utcnow().strftime('%H:%M:%S')
    }
    greetings.append(entry)
    return jsonify(entry), 201


@app.route('/api/greets', methods=['GET'])
def get_greets():
    return jsonify(greetings)


@app.route('/api/greets', methods=['DELETE'])
def clear_greets():
    greetings.clear()
    return jsonify({'cleared': True})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
