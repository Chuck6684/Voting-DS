from flask import Flask, render_template, request, jsonify
import csv
import os

app = Flask(__name__)

# Initial node configuration
nodes = [
    {"id": "Electoral_Commission", "status": "HONEST", "votes": 0},
    {"id": "Independent_Auditor", "status": "HONEST", "votes": 0},
    {"id": "NGO_Watchdog", "status": "HONEST", "votes": 0},
    {"id": "University_Node", "status": "HONEST", "votes": 0}
]

CSV_FILE = 'votes.csv'

# Create an empty CSV file if it doesn't exist to prevent errors
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        pass

def get_consensus_threshold():
    # PBFT Rule: Needs more than 2/3 of honest votes
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
    
    # Generate ID based on the username to prevent duplicate users
    if username:
        voter_id = f"VOTER-{username.strip().upper()}"
        return jsonify({"status": "success", "token": "secure_token_123", "voter_id": voter_id})
    return jsonify({"status": "error", "message": "Username required"}), 400

@app.route('/api/vote', methods=['POST'])
def cast_vote():
    data = request.json
    candidate = data.get('candidate')
    voter_id = data.get('voter_id')

    # --- ANTI-DOUBLE VOTING CHECK ---
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                # Si el ID del votante ya existe en el archivo, bloqueamos el voto
                if len(row) >= 1 and row[0] == voter_id:
                    return jsonify({"status": "error", "message": "User has already voted. Double voting is strictly prohibited!"})
    # --------------------------------

    honest_nodes = [n for n in nodes if n['status'] == 'HONEST']
    threshold = get_consensus_threshold()

    if len(honest_nodes) >= threshold:
        # Register vote
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([voter_id, candidate])
        
        # Synchronize honest nodes
        for node in honest_nodes:
            node['votes'] += 1
            
        return jsonify({"status": "success", "message": "Vote registered successfully"})
    else:
        return jsonify({"status": "error", "message": f"Consensus failed. Only {len(honest_nodes)} honest nodes available. {threshold} required."})

@app.route('/api/results')
def get_results():
    counts = {"Pablo": 0, "Ramon": 0, "Charlie": 0}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) == 2:
                    cand = row[1]
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
