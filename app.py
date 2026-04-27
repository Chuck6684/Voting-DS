from flask import Flask, render_template, request, jsonify
import csv
import os
import uuid
import hashlib
from datetime import datetime

app = Flask(__name__)

# Initial node configuration
nodes = [
    {"id": "Electoral_Commission", "status": "HONEST", "votes": 0},
    {"id": "Independent_Auditor", "status": "HONEST", "votes": 0},
    {"id": "NGO_Watchdog", "status": "HONEST", "votes": 0},
    {"id": "University_Node", "status": "HONEST", "votes": 0}
]

CSV_FILE = 'votes.csv'
USERS_CSV = 'users.csv'

# Create an empty votes CSV file if it doesn't exist to prevent errors
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        pass

# Create an empty users CSV file with headers if it doesn't exist
if not os.path.exists(USERS_CSV):
    with open(USERS_CSV, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['username', 'password', 'voter_id'])

# --- HYBRID CONSENSUS THRESHOLDS ---

def get_paxos_threshold():
    # Paxos Rule: Needs a simple majority (n/2 + 1) for liveness/quorum
    return (len(nodes) // 2) + 1

def get_pbft_threshold():
    # PBFT Rule: Needs > 2/3 of honest nodes to tolerate Byzantine faults
    n = len(nodes)
    return (2 * n // 3) + 1

# --- HTML PAGE ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/results')
def results():
    return render_template('results.html')

# --- API ROUTES ---

@app.route('/api/status')
def status():
    return jsonify(nodes)

@app.route('/api/add_node', methods=['POST'])
def add_node():
    new_id = f"Extra_Node_{len(nodes) + 1}"
    nodes.append({"id": new_id, "status": "HONEST", "votes": 0})
    return jsonify({"success": True})

@app.route('/api/remove_node', methods=['POST'])
def remove_node():
    if len(nodes) > 1:
        nodes.pop()
    return jsonify({"success": True})

@app.route('/api/hack', methods=['POST'])
def hack_node():
    node_id = request.json.get('id')
    for node in nodes:
        if node['id'] == node_id:
            node['status'] = 'MALICIOUS'
    return jsonify({"success": True})

@app.route('/api/restore', methods=['POST'])
def restore_node():
    node_id = request.json.get('id')
    for node in nodes:
        if node['id'] == node_id:
            node['status'] = 'HONEST'
    return jsonify({"success": True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required"}), 400

    username = username.strip().lower()

    # 1. CHECK IF USER ALREADY EXISTS
    if os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'r') as f:
            reader = csv.reader(f)
            next(reader, None) # Skip headers
            
            for row in reader:
                if len(row) >= 3:
                    saved_user = row[0].strip().lower()
                    saved_pass = row[1]
                    saved_voter_id = row[2]
                    
                    if saved_user == username:
                        if saved_pass == password:
                            
                            # --- CHECK IF THEY ALREADY VOTED ---
                            if os.path.exists(CSV_FILE):
                                with open(CSV_FILE, 'r') as vf:
                                    v_reader = csv.reader(vf)
                                    for v_row in v_reader:
                                        if len(v_row) >= 1 and v_row[0] == saved_voter_id:
                                            return jsonify({"status": "error", "message": "You have already cast your vote!"}), 403
                            # ----------------------------------------
                            
                            # If they haven't voted, let them in
                            return jsonify({
                                "status": "success", 
                                "token": "secure_token_123", 
                                "voter_id": saved_voter_id
                            })
                        else:
                            return jsonify({"status": "error", "message": "Incorrect password"}), 401

    # 2. IF USER DOES NOT EXIST, REGISTER THEM AS NEW
    voter_id = f"usr-{uuid.uuid4()}"
    
    with open(USERS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([username, password, voter_id])
        
    return jsonify({"status": "success", "token": "secure_token_123", "voter_id": voter_id})

@app.route('/api/vote', methods=['POST'])
def cast_vote():
    data = request.json
    candidate = data.get('candidate')
    voter_id = data.get('voter_id')

    # --- HYBRID CONSENSUS CHECK ---
    paxos_threshold = get_paxos_threshold()
    pbft_threshold = get_pbft_threshold()

    # PHASE 1: Paxos (Check Network Liveness / Simple Majority)
    # Simulating total active nodes communicating in the network
    total_active_nodes = len(nodes) 
    if total_active_nodes < paxos_threshold:
        return jsonify({"status": "error", "message": f"Paxos Prepare Phase Failed: Network partition. Only {total_active_nodes} nodes available. Quorum requires {paxos_threshold}."})

    # PHASE 2: PBFT (Check Integrity / Byzantine Supermajority)
    honest_nodes = [n for n in nodes if n['status'] == 'HONEST']

    if len(honest_nodes) >= pbft_threshold:
        # Consensus Reached: Both Paxos quorum and PBFT integrity validated
        timestamp = datetime.now().isoformat()
        vote_data = f"{voter_id}-{candidate}-{timestamp}"
        vote_hash = hashlib.sha256(vote_data.encode()).hexdigest()

        # Register vote
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([vote_hash, voter_id, candidate, timestamp])
        
        # Synchronize honest nodes
        for node in honest_nodes:
            node['votes'] += 1
            
        return jsonify({"status": "success", "message": "Hybrid Consensus Reached: Vote registered securely."})
    else:
        # Fails Phase 2: Too many malicious nodes
        return jsonify({"status": "error", "message": f"PBFT Commit Phase Failed. {pbft_threshold} honest nodes required to prevent tampering, but only {len(honest_nodes)} are honest."})

@app.route('/api/results')
def get_results():
    counts = {"Pablo": 0, "Ramon": 0, "Charlie": 0}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 3:
                    cand = row[2] 
                    if cand in counts:
                        counts[cand] += 1

    stats = []
    for cand, votes in counts.items():
        percentage = min((votes / 10) * 100, 100)
        remaining = max(10 - votes, 0)
        stats.append({
            "candidate": cand,
            "votes": votes,
            "percentage": percentage,
            "remaining": remaining
        })
    return jsonify(stats)

if __name__ == '__main__':
    app.run(debug=True, port=5000)