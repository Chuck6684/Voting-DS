from flask import Flask, render_template, request, jsonify
import csv
import os
import uuid
import hashlib
from datetime import datetime

app = Flask(__name__)

# --- Initial configuration ---
nodes = [
    {"id": "Electoral_Commission", "status": "HONEST", "votes": 0},
    {"id": "Independent_Auditor", "status": "HONEST", "votes": 0},
    {"id": "NGO_Watchdog", "status": "HONEST", "votes": 0},
    {"id": "University_Node", "status": "HONEST", "votes": 0}
]

# NEW: Lock in the original size (4) so thresholds don't shift down
ORIGINAL_SIZE = len(nodes) 
deleted_nodes = []

# --- Updated Threshold Functions ---

def get_paxos_threshold():
    # Now uses ORIGINAL_SIZE (4) instead of current len(nodes)
    # Result will always be 3
    return (ORIGINAL_SIZE // 2) + 1

def get_pbft_threshold():
    # Now uses ORIGINAL_SIZE (4)
    # Result will always be 3
    return (2 * ORIGINAL_SIZE // 3) + 1

CSV_FILE = 'votes.csv'
USERS_CSV = 'users.csv'

# Setup files
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f: pass

if not os.path.exists(USERS_CSV):
    with open(USERS_CSV, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['username', 'password', 'voter_id'])


# --- ROUTES ---

@app.route('/')
def index(): return render_template('index.html')

@app.route('/results')
def results_page():
    return render_template('results.html')

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/status')
def status(): return jsonify(nodes)

@app.route('/api/add_node', methods=['POST'])
def add_node():
    global nodes, deleted_nodes
    # If we have a node in the graveyard, bring it back first
    if deleted_nodes:
        restored_node = deleted_nodes.pop() # Gets the most recently removed node
        nodes.insert(0, restored_node)      # Puts it back at the start
        return jsonify({"success": True, "message": "Restored node"})
    else:
        # Otherwise, create a brand new extra node
        new_id = f"Extra_Node_{len(nodes) + 1}"
        nodes.append({"id": new_id, "status": "HONEST", "votes": 0})
        return jsonify({"success": True, "message": "Added new node"})

@app.route('/api/remove_node', methods=['POST'])
def remove_node():
    global nodes, deleted_nodes
    if len(nodes) > 1:
        # Target the node that was initialized first (Index 0)
        removed_node = nodes.pop(0)
        deleted_nodes.append(removed_node) # Store it to add it back later
        return jsonify({"success": True, "removed": removed_node['id']})
    return jsonify({"success": False, "message": "Cannot remove the last node"})

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