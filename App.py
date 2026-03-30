from flask import Flask, request, jsonify, render_template
import hashlib
import uuid
import time

app = Flask(__name__)

# ==========================================
# 1. DISTRIBUTED SYSTEM LOGIC
# ==========================================
class PaxosCluster:
    def __init__(self, org_name):
        self.org_name = org_name
        self.local_ledger = []

    def replicate(self, vote_data):
        # Simulating Paxos consensus inside a single organization
        time.sleep(0.1) 
        self.local_ledger.append(vote_data)
        return True

class PBFTNode:
    def __init__(self, name):
        self.name = name
        self.is_malicious = False
        self.paxos_backend = PaxosCluster(name)

    def validate_vote(self, vote):
        if self.is_malicious:
            return False # Simulating a hacked node rejecting a valid vote
        return True

class PBFTNetwork:
    def __init__(self, nodes):
        self.nodes = nodes

    def run_consensus(self, vote):
        approvals = 0
        for node in self.nodes:
            if node.validate_vote(vote):
                approvals += 1
                
        # Supermajority: 2/3 + 1
        required_majority = (2 * len(self.nodes) // 3) + 1
        
        if approvals >= required_majority:
            # Tell honest nodes to save via local Paxos
            for node in self.nodes:
                if not node.is_malicious:
                    node.paxos_backend.replicate(vote)
            return True, approvals
        return False, approvals

# Initialize the Network for the Project
nodes = [
    PBFTNode("Electoral_Commission"),
    PBFTNode("Independent_Auditor"),
    PBFTNode("NGO_Watchdog"),
    PBFTNode("University_Node")
]
network = PBFTNetwork(nodes)

# ==========================================
# 2. FLASK WEB ROUTES (The API & UI Serving)
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/vote', methods=['POST'])
def cast_vote():
    data = request.json
    voter_id = data.get('voter_id')
    candidate = data.get('candidate')

    # Create vote object and hash
    vote_id = str(uuid.uuid4())
    timestamp = time.time()
    record = f"{vote_id}{voter_id}{candidate}{timestamp}"
    vote_hash = hashlib.sha256(record.encode()).hexdigest()
    
    vote_data = {
        "hash": vote_hash,
        "voter_id": voter_id,
        "candidate": candidate,
        "timestamp": timestamp
    }

    # Run Consensus
    success, approvals = network.run_consensus(vote_data)

    if success:
        return jsonify({"status": "success", "receipt": vote_hash, "approvals": approvals, "total_nodes": len(nodes)})
    else:
        return jsonify({"status": "error", "message": "PBFT Consensus Failed!", "approvals": approvals, "total_nodes": len(nodes)}), 400

@app.route('/api/status', methods=['GET'])
def get_status():
    # Return the state of the network for the auditor dashboard
    node_status = [{"name": n.name, "malicious": n.is_malicious, "ledger_count": len(n.paxos_backend.local_ledger)} for n in nodes]
    return jsonify(node_status)

@app.route('/api/toggle_hack', methods=['POST'])
def toggle_hack():
    # Flips the University Node to malicious for demonstration purposes
    nodes[3].is_malicious = not nodes[3].is_malicious
    return jsonify({"status": "success", "university_malicious": nodes[3].is_malicious})

if __name__ == '__main__':
    app.run(debug=True, port=5000)