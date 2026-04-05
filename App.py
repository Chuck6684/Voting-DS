from flask import Flask, request, jsonify, render_template
import hashlib
import uuid
import time
from functools import wraps

app = Flask(__name__)

# ==========================================
# 1. PAXOS LOGIC (Local Organization Consensus)
# ==========================================
class InternalPaxosServer:
    """Represents a single database server inside an organization."""
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
    """The local network for an organization, running Paxos across multiple servers."""
    def __init__(self, org_name, num_internal_servers=3):
        self.org_name = org_name
        # Each organization has 3 internal servers to prevent local data loss
        self.servers = [InternalPaxosServer(i) for i in range(num_internal_servers)]
        self.proposal_counter = 0

    def replicate(self, vote_data):
        self.proposal_counter += 1
        proposal_id = self.proposal_counter
        
        # Phase 1: PREPARE (Ask internal servers if they are ready)
        promises = sum(1 for s in self.servers if s.prepare(proposal_id))
        majority = (len(self.servers) // 2) + 1
        
        # If a majority of internal servers promise, proceed to Accept
        if promises >= majority:
            # Phase 2: ACCEPT (Tell internal servers to permanently save the vote)
            accepts = sum(1 for s in self.servers if s.accept(proposal_id, vote_data))
            if accepts >= majority:
                return True
        return False

    @property
    def local_ledger(self):
        # For the dashboard, we just read the ledger from the first internal server
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
                
        # Supermajority: 2/3 + 1
        required_majority = (2 * len(self.nodes) // 3) + 1
        
        if approvals >= required_majority:
            for node in self.nodes:
                if not node.is_malicious:
                    # Trigger the Paxos algorithm to save the vote locally
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

# ==========================================
# 3. FLASK WEB ROUTES 
# ==========================================

VALID_VOTER_TOKENS = {
    "secret_charlie_125",
    "secret_pablo_235",
    "secret_ramon_784"
}

def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswitch('Bearer'):
            return jsonify({"status": "error", "message": "Access Denied: Missing Authentication Token" }), 401
        
        token = auth_header.split(' ')[1]
        if token not in VALID_VOTER_TOKENS:
            return jsonify({"status": "error", "message": "Access Denied: Missing Authentication Token" }), 403
        
        return f(*args, **kwargs)
    return decorated
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/vote', methods=['POST'])
@require_token
def cast_vote():
    data = request.json
    voter_id = data.get('voter_id')
    candidate = data.get('candidate')

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
    global_nodes.append(new_node)
    return jsonify({"status": "success", "total_nodes": len(global_nodes)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)