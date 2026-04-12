from flask import Flask, render_template, request, jsonify
import csv
import os

app = Flask(__name__)

# Configuración inicial de nodos (Variable global para que persista en la sesión)
if 'nodes' not in globals():
    nodes = [
        {"id": "Electoral_Commission", "status": "HONEST", "votes": 0},
        {"id": "Independent_Auditor", "status": "HONEST", "votes": 0},
        {"id": "NGO_Watchdog", "status": "HONEST", "votes": 0},
        {"id": "University_Node", "status": "HONEST", "votes": 0}
    ]

CSV_FILE = 'votes.csv'

# Asegurar que el archivo de votos existe
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['voter_name', 'candidate'])

def get_consensus_threshold():
    # Regla PBFT: Se necesita más de 2/3 de los nodos totales
    n = len(nodes)
    return (2 * n // 3) + 1

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

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

@app.route('/vote', methods=['POST'])
def vote():
    candidate = request.form.get('candidate')
    voter_name = request.form.get('voter_name')
    
    honest_nodes = [n for n in nodes if n['status'] == 'HONEST']
    threshold = get_consensus_threshold()
    
    # Verificamos si hay suficientes nodos honestos para el consenso
    if len(honest_nodes) >= threshold:
        # Registrar el voto en el CSV
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([voter_name, candidate])
        
        # Sincronizar los registros de los nodos que están funcionando bien
        for node in honest_nodes:
            node['votes'] += 1
            
        return f"Voto registrado exitosamente. Consenso alcanzado ({len(honest_nodes)}/{len(nodes)} nodos)."
    else:
        # Aquí es donde lanzamos el error 403 si la red está comprometida
        return f"ERROR DE CONSENSO: Solo {len(honest_nodes)} nodos honestos. Se requieren {threshold} para validar la seguridad de la red.", 403

if __name__ == '__main__':
    # Usamos debug=True para que se reinicie solo si haces cambios
    app.run(debug=True, port=5000)
