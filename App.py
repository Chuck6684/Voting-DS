from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import json
import time

app = Flask(__name__)
CORS(app) # Allows the HTML file to talk to the Python server

# --- CONSENSUS ENGINE ---
class HybridSystem:
    def __init__(self):
        self.paxos_batch = []
        self.ledger = []

    def process_vote(self, voter, choice, tamper=False):
        # 1. Paxos Simulation (Ordering)
        vote_entry = {"voter": voter, "choice": choice, "timestamp": time.time()}
        
        # Generate a 'Voter Signature' (In real life, this happens on voter's phone)
        original_sig = hashlib.sha256(json.dumps(vote_entry, sort_keys=True).encode()).hexdigest()
        
        # 2. Malicious Tamper (If requested)
        if tamper:
            vote_entry["choice"] = "Bob" if choice == "Alice" else "Alice"
        
        # 3. pBFT Simulation (Audit)
        current_hash = hashlib.sha256(json.dumps(vote_entry, sort_keys=True).encode()).hexdigest()
        
        is_valid = (current_hash == original_sig)
        
        if is_valid:
            self.ledger.append(vote_entry)
            return {"status": "success", "msg": "pBFT Verified: Vote Added to Ledger"}
        else:
            return {"status": "error", "msg": "pBFT ALERT: Signature Mismatch! Vote Rejected"}

engine = HybridSystem()

@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    data = request.json
    result = engine.process_vote(data['voter'], data['choice'], data.get('tamper', False))
    return jsonify(result)

if __name__ == '__main__':
    app.run(port=5000, debug=True)