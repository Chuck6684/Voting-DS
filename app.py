from flask import Flask, request, jsonify, render_template
from functools import wraps
import hashlib
import uuid
import time
import csv
import os

app = Flask(__name__)

# ==========================================
# NEW: CONSTANTS & CSV SETUP
# ==========================================
CSV_FILENAME = 'votes.csv'
VALID_TOKEN = "super-secret-token" # In a real app, this would be validated against a DB/JWT
voted_users = set()

def load_votes_from_csv(nodes):
    """Loads past votes from CSV into memory and the nodes' ledgers."""
    if os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                voted_users.add(row['voter_id'])
                # Populate the local ledger of each honest node so UI reflects history
                for node in nodes:
                    if not node.is_malicious:
                        node.paxos_backend.servers[0].ledger.append(row)

def save_vote_to_csv(vote_data):
    """Appends a successfully committed vote to the CSV."""
    file_exists = os.path.exists(CSV_FILENAME)
    with open(CSV_FILENAME, mode='a', newline='') as file:
        fieldnames = ['hash', 'voter_id', 'candidate', 'timestamp']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(vote_data)

def token_required(f):
    """Decorator to verify the session token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f"Bearer {VALID_TOKEN}":
            return jsonify({'status': 'error', 'message': 'Unauthorized. Invalid or missing session token.'}), 401
        return f(*args, **kwargs)
    return decorated

# ==========================================
# 1. PAXOS LOGIC (Local Organization Consensus)
# ==========================================
class InternalPaxosServer:
    def __init__(self, server_id):
        self.server_id = server_id
        self.highest_proposal = 0
        self.ledger = []

    def prepare(self, proposal_id):
        if proposal_id > self.highest_proposal:
            self.highest_proposal = proposal_id
            return True
        return False

    def accept(self, proposal_id, data):
        if proposal_id >= self.highest_proposal:
            self.highest_proposal = proposal_id
            self.ledger.append(data)
            return True
        return False

class PaxosCluster:
    def __init__(self, org_name, num_internal_servers=3):
        self.org_name = org_name
        self.servers = [InternalPaxosServer(i) for i in range(num_internal_servers)]
        self.proposal_counter = 0

    def replicate(self, vote_data):
        self.proposal_counter += 1
        proposal_id = self.proposal_counter
        
        promises = sum(1 for s in self.servers if s.prepare(proposal_id))
        majority = (len(self.servers) // 2) + 1
        
        if promises >= majority:
            accepts = sum(1 for s in self.servers if s.accept(proposal_id, vote_data))
            if accepts >= majority:
                return True
        return False

    @property
    def local_ledger(self):
        return self.servers[0].ledger


# ==========================================
# 2. PBFT LOGIC (Global Network Consensus)
# ==========================================
class PBFTNode:
    def __init__(self, name):
        self.name = name
        self.is_malicious = False
        self.paxos_backend = PaxosCluster(name)

    def validate_vote(self, vote):
        if self.is_malicious:
            return False 
        return True

class PBFTNetwork:
    def __init__(self, nodes_list):
        self.nodes = nodes_list

    def run_consensus(self, vote):
        approvals = 0
        for node in self.nodes:
            if node.validate_vote(vote):
                approvals += 1
                
        required_majority = (2 * len(self.nodes) // 3) + 1
        
        if approvals >= required_majority:
            for node in self.nodes:
                if not node.is_malicious:
                    node.paxos_backend.replicate(vote)
            return True, approvals, required_majority
        return False, approvals, required_majority


# Initialize with 4 standard nodes
global_nodes = [
    PBFTNode("Electoral_Commission"),
    PBFTNode("Independent_Auditor"),
    PBFTNode("NGO_Watchdog"),
    PBFTNode("University_Node")
]
network = PBFTNetwork(global_nodes)

# Load existing votes from CSV on startup
load_votes_from_csv(global_nodes)

# ==========================================
# 3. FLASK WEB ROUTES 
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

# Add this above your @app.route('/api/vote')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    # In a real app, you would hash the password and check a database.
    # For this example, we'll hardcode a valid user.
    if username == "admin" and password == "password123":
        return jsonify({"status": "success", "token": VALID_TOKEN})
    else:
        return jsonify({"status": "error", "message": "Invalid username or password"}), 401
    
@app.route('/api/vote', methods=['POST'])
@token_required
def cast_vote():
    data = request.json
    voter_id = data.get('voter_id')
    candidate = data.get('candidate')

    # Ensure user hasn't voted already
    if voter_id in voted_users:
        return jsonify({"status": "error", "message": "Duplicate Vote: This Voter ID has already been used."}), 403

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

    success, approvals, required = network.run_consensus(vote_data)

    if success:
        voted_users.add(voter_id) # Mark user as voted
        save_vote_to_csv(vote_data) # Persist to CSV
        return jsonify({"status": "success", "receipt": vote_hash, "approvals": approvals, "required": required, "total_nodes": len(global_nodes)})
    else:
        return jsonify({"status": "error", "message": "Consensus Failed - Too many malicious nodes!", "approvals": approvals, "required": required, "total_nodes": len(global_nodes)}), 400

@app.route('/api/status', methods=['GET'])
def get_status():
    node_status = [{"id": i, "name": n.name, "malicious": n.is_malicious, "ledger_count": len(n.paxos_backend.local_ledger)} for i, n in enumerate(global_nodes)]
    return jsonify(node_status)

@app.route('/api/toggle_hack', methods=['POST'])
def toggle_hack():
    data = request.json
    node_index = data.get('node_index')
    
    if 0 <= node_index < len(global_nodes):
        global_nodes[node_index].is_malicious = not global_nodes[node_index].is_malicious
        return jsonify({"status": "success", "malicious": global_nodes[node_index].is_malicious})
    return jsonify({"status": "error"}), 400

@app.route('/api/add_node', methods=['POST'])
def add_node():
    new_id = len(global_nodes) + 1
    new_node = PBFTNode(f"Observer_Node_{new_id}")
    # Sync new node with existing history
    for _ in range(len(voted_users)): 
        new_node.paxos_backend.servers[0].ledger.append({}) # Dummy data just for ledger count sync
    global_nodes.append(new_node)
    return jsonify({"status": "success", "total_nodes": len(global_nodes)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)