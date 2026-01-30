from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime
import os
import csv
from io import StringIO

app = Flask(__name__, static_folder='.')
CORS(app)  # Enable CORS for all routes

# Database initialization
def init_db():
    conn = sqlite3.connect('survey.db')
    c = conn.cursor()
    
    # Create survey_responses table
    c.execute('''
        CREATE TABLE IF NOT EXISTS survey_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            q1 TEXT NOT NULL,
            q2 TEXT NOT NULL,
            portal_rating TEXT,
            llm_rating TEXT,
            q4 TEXT NOT NULL,
            q5 TEXT NOT NULL,
            has_improvements INTEGER DEFAULT 0,
            improvements TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create index for faster queries
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON survey_responses(timestamp)')
    
    conn.commit()
    conn.close()
    print("✓ Database initialized successfully")

# Initialize database on startup
init_db()

# Serve the main HTML file
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# Serve static files (images, CSS, JS)
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# API endpoint to submit survey
@app.route('/api/submit', methods=['POST', 'OPTIONS'])
def submit_survey():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        print(f"Received survey data: {data}")
        
        # Validate required fields
        required_fields = ['q1', 'q2', 'q4', 'q5']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'status': 'error', 'message': f'Missing required field: {field}'}), 400
        
        # Convert q2 list to string
        if isinstance(data['q2'], list):
            q2_string = ','.join(data['q2'])
        else:
            q2_string = str(data['q2'])
        
        # Connect to database
        conn = sqlite3.connect('survey.db')
        c = conn.cursor()
        
        # Insert response
        c.execute('''
            INSERT INTO survey_responses 
            (q1, q2, portal_rating, llm_rating, q4, q5, has_improvements, improvements)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(data['q1']),
            q2_string,
            str(data.get('portal_rating', '')),
            str(data.get('llm_rating', '')),
            str(data['q4']),
            str(data['q5']),
            1 if data.get('has_improvements') else 0,
            str(data.get('improvements', ''))
        ))
        
        conn.commit()
        response_id = c.lastrowid
        conn.close()
        
        print(f"✓ Survey response saved with ID: {response_id}")
        
        return jsonify({
            'status': 'success',
            'message': 'Survey response saved successfully',
            'id': response_id
        }), 200
        
    except Exception as e:
        print(f"✗ Error saving survey: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

# API endpoint to get all responses
@app.route('/api/responses', methods=['GET'])
def get_responses():
    try:
        conn = sqlite3.connect('survey.db')
        conn.row_factory = sqlite3.Row  # This enables column access by name
        c = conn.cursor()
        
        c.execute('SELECT * FROM survey_responses ORDER BY timestamp DESC')
        rows = c.fetchall()
        
        # Convert rows to list of dictionaries
        responses = []
        for row in rows:
            response_dict = dict(row)
            # Convert q2 string back to list
            if response_dict['q2']:
                response_dict['q2'] = response_dict['q2'].split(',')
            else:
                response_dict['q2'] = []
            responses.append(response_dict)
        
        conn.close()
        
        return jsonify(responses), 200
        
    except Exception as e:
        print(f"Error fetching responses: {e}")
        return jsonify({'error': str(e)}), 500

# API endpoint to get statistics
@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        conn = sqlite3.connect('survey.db')
        c = conn.cursor()
        
        # Get total count
        c.execute('SELECT COUNT(*) as total FROM survey_responses')
        total = c.fetchone()[0]
        
        # Get Q1 distribution
        c.execute('SELECT q1, COUNT(*) as count FROM survey_responses GROUP BY q1')
        q1_stats = dict(c.fetchall())
        
        # Get average ratings
        c.execute('SELECT AVG(CAST(portal_rating as REAL)) FROM survey_responses WHERE portal_rating != "" AND portal_rating IS NOT NULL')
        avg_portal = c.fetchone()[0] or 0
        
        c.execute('SELECT AVG(CAST(llm_rating as REAL)) FROM survey_responses WHERE llm_rating != "" AND llm_rating IS NOT NULL')
        avg_llm = c.fetchone()[0] or 0
        
        # Get Q4 distribution
        c.execute('SELECT q4, COUNT(*) as count FROM survey_responses GROUP BY q4 ORDER BY count DESC')
        q4_stats = dict(c.fetchall())
        
        # Get Q5 distribution
        c.execute('SELECT q5, COUNT(*) as count FROM survey_responses GROUP BY q5 ORDER BY count DESC')
        q5_stats = dict(c.fetchall())
        
        conn.close()
        
        return jsonify({
            'total_responses': total,
            'q1_distribution': q1_stats,
            'average_ratings': {
                'portal': round(float(avg_portal), 1),
                'llm': round(float(avg_llm), 1)
            },
            'q4_distribution': q4_stats,
            'q5_distribution': q5_stats,
            'has_improvements': {
                'yes': sum(1 for _ in q4_stats if 'improvements' in str(_).lower()),
                'no': total - sum(1 for _ in q4_stats if 'improvements' in str(_).lower())
            }
        }), 200
        
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

# API endpoint to export responses as CSV
@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    try:
        conn = sqlite3.connect('survey.db')
        c = conn.cursor()
        
        c.execute('SELECT * FROM survey_responses ORDER BY timestamp DESC')
        rows = c.fetchall()
        columns = [description[0] for description in c.description]
        
        conn.close()
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(rows)
        
        # Prepare response
        csv_data = output.getvalue()
        output.close()
        
        return csv_data, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=survey_responses_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        }
        
    except Exception as e:
        print(f"Error exporting CSV: {e}")
        return jsonify({'error': str(e)}), 500

# Admin page to view responses
@app.route('/admin')
def admin():
    return '''
    <!DOCTYPE html>
<html>
<head>
    <title>Survey Responses Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }
        body {
            background: #f5f7fa;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            margin-bottom: 20px;
            text-align: center;
        }
        .controls {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
        }
        .btn-refresh { background: #3498db; color: white; }
        .btn-export { background: #27ae60; color: white; }
        .btn-clear { background: #e74c3c; color: white; }
        .stats {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .stat-card {
            text-align: center;
            padding: 15px;
            background: white;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #3498db;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
            font-size: 14px;
        }
        th {
            background: #3498db;
            color: white;
            position: sticky;
            top: 0;
        }
        tr:hover {
            background: #f5f5f5;
        }
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
        }
        .badge-portal { background: #3498db; color: white; }
        .badge-llm { background: #9b59b6; color: white; }
        .loading {
            text-align: center;
            padding: 40px;
            color: #3498db;
            font-size: 1.2rem;
        }
        @media (max-width: 768px) {
            .container { padding: 15px; }
            table { display: block; overflow-x: auto; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Survey Responses Admin</h1>
        
        <div class="controls">
            <button class="btn-refresh" onclick="loadData()">🔄 Refresh</button>
            <button class="btn-export" onclick="exportCSV()">📥 Export CSV</button>
            <button class="btn-clear" onclick="clearData()">🗑️ Clear All</button>
        </div>
        
        <div class="stats" id="stats">
            <div class="loading" id="loadingStats">
                <i>Loading statistics...</i>
            </div>
        </div>
        
        <div id="table-container">
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Preferred</th>
                        <th>Strengths</th>
                        <th>Portal</th>
                        <th>LLM</th>
                        <th>Use Case</th>
                        <th>Future Use</th>
                        <th>Improvements</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody id="responsesTable">
                    <tr><td colspan="9" class="loading">Loading responses...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Load data on page load
        document.addEventListener('DOMContentLoaded', loadData);
        
        async function loadData() {
            try {
                // Show loading
                document.getElementById('responsesTable').innerHTML = 
                    '<tr><td colspan="9" class="loading">Loading...</td></tr>';
                
                // Fetch responses
                const response = await fetch('/api/responses');
                if (!response.ok) throw new Error('Failed to fetch data');
                
                const data = await response.json();
                console.log('Loaded data:', data);
                
                // Update table
                updateTable(data);
                
                // Update statistics
                updateStats(data);
                
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('responsesTable').innerHTML = 
                    '<tr><td colspan="9" style="color: #e74c3c; text-align: center; padding: 20px;">Error loading data: ' + error.message + '</td></tr>';
            }
        }
        
        function updateTable(data) {
            const tbody = document.getElementById('responsesTable');
            
            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; padding: 20px; color: #95a5a6;">No responses yet</td></tr>';
                return;
            }
            
            tbody.innerHTML = '';
            
            data.forEach(item => {
                const row = document.createElement('tr');
                
                // Format strengths
                const strengths = Array.isArray(item.q2) 
                    ? item.q2.map(s => `<div style="margin: 2px 0; font-size: 12px;">• ${s}</div>`).join('')
                    : item.q2;
                
                // Format improvements
                const improvements = item.has_improvements && item.improvements 
                    ? `<div style="max-width: 200px; word-wrap: break-word;">${item.improvements}</div>`
                    : 'None';
                
                // Format timestamp
                const time = new Date(item.timestamp).toLocaleString();
                
                row.innerHTML = `
                    <td>${item.id}</td>
                    <td>
                        <span class="badge ${item.q1 === 'portal' ? 'badge-portal' : 'badge-llm'}">
                            ${item.q1 === 'portal' ? 'Portal' : 'LLM'}
                        </span>
                    </td>
                    <td>${strengths}</td>
                    <td>${item.portal_rating || 'N/A'}</td>
                    <td>${item.llm_rating || 'N/A'}</td>
                    <td>${formatUseCase(item.q4)}</td>
                    <td>${formatFutureUse(item.q5)}</td>
                    <td>${improvements}</td>
                    <td style="font-size: 12px; color: #666;">${time}</td>
                `;
                tbody.appendChild(row);
            });
        }
        
        function updateStats(data) {
            const statsDiv = document.getElementById('stats');
            
            if (!data || data.length === 0) {
                statsDiv.innerHTML = '<div class="stat-card"><div class="stat-value">0</div><div>Total Responses</div></div>';
                return;
            }
            
            // Calculate statistics
            const total = data.length;
            const portalCount = data.filter(r => r.q1 === 'portal').length;
            const llmCount = data.filter(r => r.q1 === 'llm').length;
            
            // Calculate average ratings
            const portalRatings = data.filter(r => r.portal_rating && !isNaN(r.portal_rating)).map(r => parseInt(r.portal_rating));
            const llmRatings = data.filter(r => r.llm_rating && !isNaN(r.llm_rating)).map(r => parseInt(r.llm_rating));
            
            const avgPortal = portalRatings.length > 0 
                ? (portalRatings.reduce((a, b) => a + b, 0) / portalRatings.length).toFixed(1)
                : 'N/A';
                
            const avgLLM = llmRatings.length > 0
                ? (llmRatings.reduce((a, b) => a + b, 0) / llmRatings.length).toFixed(1)
                : 'N/A';
            
            statsDiv.innerHTML = `
                <div class="stat-card">
                    <div class="stat-value">${total}</div>
                    <div>Total Responses</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${portalCount}</div>
                    <div>Portal Graph</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${llmCount}</div>
                    <div>LLM Graph</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${avgPortal}</div>
                    <div>Avg Portal Rating</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${avgLLM}</div>
                    <div>Avg LLM Rating</div>
                </div>
            `;
        }
        
        function formatUseCase(q4) {
            const map = {
                'test': 'Test Cases',
                'user': 'User Stories',
                'business': 'Business Insights',
                'code': 'Code Review',
                'sprint': 'Sprint Planning',
                'architecture': 'Architecture',
                'all': 'All'
            };
            return map[q4] || q4;
        }
        
        function formatFutureUse(q5) {
            const map = {
                'definitely': 'Definitely',
                'probably': 'Probably',
                'might': 'Might',
                'probably-not': 'Probably Not',
                'definitely-not': 'Definitely Not'
            };
            return map[q5] || q5;
        }
        
        function exportCSV() {
            window.open('/api/export/csv', '_blank');
        }
        
        async function clearData() {
            if (!confirm('WARNING: Delete ALL responses? This cannot be undone.')) return;
            
            const password = prompt('Enter admin password:');
            if (password !== 'admin123') {
                alert('Wrong password');
                return;
            }
            
            try {
                const response = await fetch('/api/responses?password=' + password, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    alert('All data cleared');
                    loadData();
                } else {
                    alert('Error clearing data');
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
    </script>
</body>
</html>
    '''


# DELETE endpoint to clear all data
@app.route('/api/responses', methods=['DELETE'])
def delete_responses():
    try:
        # Get password from query parameter
        password = request.args.get('password')
        if password != 'admin123':
            return jsonify({'error': 'Unauthorized'}), 401
        
        conn = sqlite3.connect('survey.db')
        c = conn.cursor()
        c.execute('DELETE FROM survey_responses')
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'All responses cleared'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Get port from environment variable (for Replit)
    port = int(os.environ.get("PORT", 8080))
    
    print("=" * 60)
    print("🚀 Accessibility Visualization Survey")
    print("=" * 60)
    print(f"🌐 Frontend URL: http://localhost:{port}")
    print(f"📊 Admin Panel: http://localhost:{port}/admin")
    print(f"📝 API Endpoint: http://localhost:{port}/api/submit")
    print(f"📈 Statistics: http://localhost:{port}/api/stats")
    print(f"📥 CSV Export: http://localhost:{port}/api/export/csv")
    print("=" * 60)
    print("💡 Admin password: admin123")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=True)