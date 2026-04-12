from flask import Flask, request, jsonify, render_template
from functools import wraps
import hashlib
import uuid
import time
import csv
import os

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
VOTES_CSV_FILENAME = 'votes.csv'
USERS_CSV_FILENAME = 'users.csv'
VALID_TOKEN = "super-secret-token" 

voted_users = set()
registered_users = {}

# --- Persistance Helpers ---
def load_users_from_csv():
    """Loads registered users from CSV into memory on startup."""
    if os.path.exists(USERS_CSV_FILENAME):
        with open(USERS_CSV_FILENAME, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                registered_users[row['username']] = {
                    "password": row['password'],
                    "voter_id": row['voter_id']
                }

def save_user_to_csv(username, password, voter_id):
    file_exists = os.path.exists(USERS_CSV_FILENAME)
    with open(USERS_CSV_FILENAME, mode='a', newline='') as file:
        fieldnames = ['username', 'password', 'voter_id']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({"username": username, "password": password, "voter_id": voter_id})

def save_vote_to_csv(vote_data):
    file_exists = os.path.exists(VOTES_CSV_FILENAME)
    with open(VOTES_CSV_FILENAME, mode='a', newline='') as file:
        fieldnames = ['hash', 'voter_id', 'candidate', 'timestamp']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(vote_data)

# Auth Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f"Bearer {VALID_TOKEN}":
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# ==========================================
# DISTRIBUTED LOGIC (Paxos & PBFT)
# ==========================================
# (Note: Kept the logic from your colleague intact to ensure stability)

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
            return accepts >= majority
        return False

class PBFTNode:
    def __init__(self, name):
        self.name = name
        self.is_malicious = False
        self.paxos_backend = PaxosCluster(name)

    def validate_vote(self, vote):
        return not self.is_malicious

class PBFTNetwork:
    def __init__(self, nodes_list):
        self.nodes = nodes_list

    def run_consensus(self, vote):
        approvals = sum(1 for n in self.nodes if n.validate_vote(vote))
        required_majority = (2 * len(self.nodes) // 3) + 1
        if approvals >= required_majority:
            for node in self.nodes:
                if not node.is_malicious:
                    node.paxos_backend.replicate(vote)
            return True, approvals, required_majority
        return False, approvals, required_majority

# Initialize network
global_nodes = [PBFTNode("Electoral_Commission"), PBFTNode("Independent_Auditor"), 
                PBFTNode("NGO_Watchdog"), PBFTNode("University_Node")]
network = PBFTNetwork(global_nodes)
load_users_from_csv()

# ==========================================
# NEW ROUTES FOR VERSION PAU-RAMON
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/results')
def results_page():
    return render_template('results.html')

@app.route('/admin')
def admin_page():
    """Restricted page to manage node status and network hacks."""
    return render_template('admin.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username, password = data.get('username'), data.get('password')
    if username in registered_users:
        if registered_users[username]['password'] == password:
            return jsonify({"status": "success", "token": VALID_TOKEN, "voter_id": registered_users[username]['voter_id']})
        return jsonify({"status": "error", "message": "Invalid password"}), 401
    
    new_voter_id = f"usr-{str(uuid.uuid4())[:8]}"
    registered_users[username] = {"password": password, "voter_id": new_voter_id}
    save_user_to_csv(username, password, new_voter_id)
    return jsonify({"status": "success", "token": VALID_TOKEN, "voter_id": new_voter_id})

@app.route('/api/vote', methods=['POST'])
@token_required
def cast_vote():
    data = request.json
    voter_id, candidate = data.get('voter_id'), data.get('candidate')
    if voter_id in voted_users:
        return jsonify({"status": "error", "message": "Already voted"}), 403

    vote_data = {"hash": hashlib.sha256(str(time.time()).encode()).hexdigest()[:16],
                 "voter_id": voter_id, "candidate": candidate, "timestamp": time.time()}

    success, approvals, required = network.run_consensus(vote_data)
    if success:
        voted_users.add(voter_id)
        save_vote_to_csv(vote_data)
        return jsonify({"status": "success", "receipt": vote_data['hash'], "approvals": approvals, "total_nodes": len(global_nodes)})
    return jsonify({"status": "error", "message": "Consensus failed"}), 400

@app.route('/api/results')
def get_results():
    counts = {"Pablo": 0, "Ramon": 0, "Charlie": 0}
    if os.path.exists(VOTES_CSV_FILENAME):
        with open(VOTES_CSV_FILENAME, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['candidate'] in counts: counts[row['candidate']] += 1
    
    return jsonify([{ "candidate": c, "votes": v, "percentage": min((v/10)*100, 100), "remaining": max(10-v, 0)} for c,v in counts.items()])

@app.route('/api/status')
def get_status():
    return jsonify([{"id": i, "name": n.name, "malicious": n.is_malicious, "ledger_count": len(n.paxos_backend.servers[0].ledger)} for i, n in enumerate(global_nodes)])

@app.route('/api/toggle_hack', methods=['POST'])
def toggle_hack():
    idx = request.json.get('node_index')
    global_nodes[idx].is_malicious = not global_nodes[idx].is_malicious
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
