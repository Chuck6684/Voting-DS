from flask import Flask, request, jsonify, render_template
from functools import wraps
import hashlib
import uuid
import time
import csv
import os

app = Flask(__name__)

# ==========================================
# CONSTANTS & CSV SETUP
# ==========================================
VOTES_CSV_FILENAME = 'votes.csv'
USERS_CSV_FILENAME = 'users.csv'
VALID_TOKEN = "super-secret-token" 

voted_users = set()
registered_users = {}

# --- NEW: User Database Persistence ---
def load_users_from_csv():
    """Loads registered users and their assigned Voter IDs into memory."""
    if os.path.exists(USERS_CSV_FILENAME):
        with open(USERS_CSV_FILENAME, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                registered_users[row['username']] = {
                    "password": row['password'],
                    "voter_id": row['voter_id']
                }

def save_user_to_csv(username, password, voter_id):
    """Saves a newly registered user to the CSV."""
    file_exists = os.path.exists(USERS_CSV_FILENAME)
    with open(USERS_CSV_FILENAME, mode='a', newline='') as file:
        fieldnames = ['username', 'password', 'voter_id']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({"username": username, "password": password, "voter_id": voter_id})

# --- Existing Vote Database Persistence ---
def load_votes_from_csv(nodes):
    if os.path.exists(VOTES_CSV_FILENAME):
        with open(VOTES_CSV_FILENAME, mode='r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                voted_users.add(row['voter_id'])
                for node in nodes:
                    if not node.is_malicious:
                        node.paxos_backend.servers[0].ledger.append(row)

def save_vote_to_csv(vote_data):
    file_exists = os.path.exists(VOTES_CSV_FILENAME)
    with open(VOTES_CSV_FILENAME, mode='a', newline='') as file:
        fieldnames = ['hash', 'voter_id', 'candidate', 'timestamp']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(vote_data)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or auth_header != f"Bearer {VALID_TOKEN}":
            return jsonify({'status': 'error', 'message': 'Unauthorized. Invalid or missing session token.'}), 401
        return f(*args, **kwargs)
    return decorated

# ==========================================
# 1. PAXOS LOGIC 
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
# 2. PBFT LOGIC
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

# Initialize network
global_nodes = [
    PBFTNode("Electoral_Commission"),
    PBFTNode("Independent_Auditor"),
    PBFTNode("NGO_Watchdog"),
    PBFTNode("University_Node")
]
network = PBFTNetwork(global_nodes)

# Load databases on startup
load_users_from_csv()
load_votes_from_csv(global_nodes)

# ==========================================
# 3. FLASK WEB ROUTES 
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

# UPDATED: Dynamic Registration & Login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required"}), 400

    # 1. Check if user already exists
    if username in registered_users:
        if registered_users[username]['password'] == password:
            return jsonify({
                "status": "success", 
                "token": VALID_TOKEN,
                "voter_id": registered_users[username]['voter_id']
            })
        else:
            return jsonify({"status": "error", "message": "Invalid password"}), 401
    
    # 2. If user doesn't exist, auto-register them and assign an unchangeable ID
    else:
        new_voter_id = f"usr-{str(uuid.uuid4())}"
        registered_users[username] = {
            "password": password,
            "voter_id": new_voter_id
        }
        save_user_to_csv(username, password, new_voter_id)
        
        return jsonify({
            "status": "success", 
            "token": VALID_TOKEN,
            "voter_id": new_voter_id
        })

@app.route('/api/vote', methods=['POST'])
@token_required
def cast_vote():
    data = request.json
    voter_id = data.get('voter_id')
    candidate = data.get('candidate')

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
        voted_users.add(voter_id) 
        save_vote_to_csv(vote_data) 
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
    for _ in range(len(voted_users)): 
        new_node.paxos_backend.servers[0].ledger.append({}) 
    global_nodes.append(new_node)
    return jsonify({"status": "success", "total_nodes": len(global_nodes)})

import csv # Make sure this is at the very top of your app.py!
import os

@app.route('/results')
def results_page():
    return render_template('results.html')

@app.route('/api/results', methods=['GET'])
def get_results():
    # The goal threshold
    WINNING_THRESHOLD = 10 
    
    # Initialize our score board
    vote_counts = {"Pablo": 0, "Ramon": 0, "Charlie": 0}
    
    # Read the CSV (if it exists)
    if os.path.exists('votes.csv'):
        with open('votes.csv', mode='r') as file:
            reader = csv.reader(file)
            for row in reader:
                # Assuming your CSV format is: Hash, VoterID, Candidate, Timestamp
                # So the candidate name is in the 3rd column (index 2)
                if len(row) >= 3:
                    candidate = row[2]
                    if candidate in vote_counts:
                        vote_counts[candidate] += 1
                        
    # Package the results with the math done for the frontend
    results_data = []
    for candidate, votes in vote_counts.items():
        remaining = WINNING_THRESHOLD - votes
        if remaining < 0:
            remaining = 0 # Don't show negative numbers if they pass 10
            
        percentage = (votes / WINNING_THRESHOLD) * 100
        if percentage > 100:
            percentage = 100
            
        results_data.append({
            "candidate": candidate,
            "votes": votes,
            "remaining": remaining,
            "percentage": percentage
        })
        
    return jsonify(results_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)