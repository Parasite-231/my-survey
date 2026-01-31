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
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 2px solid #f0f0f0;
            }
            h1 {
                color: #2c3e50;
                font-size: 2.5rem;
                margin-bottom: 10px;
            }
            .subtitle {
                color: #7f8c8d;
                font-size: 1.1rem;
            }
            .controls {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 30px;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 10px;
            }
            button {
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                transition: all 0.3s ease;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            .btn-primary {
                background: #3498db;
                color: white;
            }
            .btn-success {
                background: #27ae60;
                color: white;
            }
            .btn-danger {
                background: #e74c3c;
                color: white;
            }
            .btn-secondary {
                background: #95a5a6;
                color: white;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                padding: 25px;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.05);
                border-left: 5px solid #3498db;
            }
            .stat-card h3 {
                color: #2c3e50;
                margin-bottom: 15px;
                font-size: 1.2rem;
            }
            .stat-value {
                font-size: 2.5rem;
                font-weight: bold;
                color: #3498db;
                margin-bottom: 10px;
            }
            .stat-label {
                color: #7f8c8d;
                font-size: 0.9rem;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                background: white;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 5px 15px rgba(0,0,0,0.05);
            }
            th, td {
                padding: 15px;
                text-align: left;
                border-bottom: 1px solid #f0f0f0;
                font-size: 14px;
            }
            th {
                background: #3498db;
                color: white;
                font-weight: 600;
                position: sticky;
                top: 0;
            }
            tr:hover {
                background-color: #f8f9fa;
            }
            .badge {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
                text-transform: uppercase;
            }
            .badge-portal {
                background: #3498db;
                color: white;
            }
            .badge-llm {
                background: #9b59b6;
                color: white;
            }
            .rating {
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 5px;
                display: inline-block;
            }
            .rating-portal {
                background: #d6eaf8;
                color: #21618c;
            }
            .rating-llm {
                background: #e8daef;
                color: #6c3483;
            }
            .improvements {
                max-width: 300px;
                word-wrap: break-word;
                line-height: 1.4;
                font-size: 13px;
            }
            .timestamp {
                font-size: 12px;
                color: #7f8c8d;
            }
            .no-data {
                text-align: center;
                padding: 40px;
                color: #95a5a6;
                font-size: 1.2rem;
            }
            .loading {
                text-align: center;
                padding: 40px;
                color: #3498db;
            }
            @media (max-width: 768px) {
                .container {
                    padding: 15px;
                }
                .controls {
                    flex-direction: column;
                }
                button {
                    width: 100%;
                    justify-content: center;
                }
                table {
                    display: block;
                    overflow-x: auto;
                }
            }
        </style>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><i class="fas fa-chart-bar"></i> Survey Responses Dashboard</h1>
                <p class="subtitle">Real-time monitoring of accessibility visualization survey responses</p>
            </div>
            
            <div class="controls">
                <button class="btn-primary" onclick="loadData()">
                    <i class="fas fa-sync-alt"></i> Refresh Data
                </button>
                <button class="btn-success" onclick="exportCSV()">
                    <i class="fas fa-download"></i> Export CSV
                </button>
                <button class="btn-secondary" onclick="viewStats()">
                    <i class="fas fa-chart-pie"></i> View Statistics
                </button>
                <button class="btn-danger" onclick="clearData()">
                    <i class="fas fa-trash-alt"></i> Clear All Data
                </button>
            </div>
            
            <div class="stats-grid" id="statsGrid">
                <div class="loading" id="loadingStats">
                    <i class="fas fa-spinner fa-spin"></i> Loading statistics...
                </div>
            </div>
            
            <div style="overflow-x: auto;">
                <table id="responsesTable">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Preferred Graph</th>
                            <th>Strengths</th>
                            <th>Portal Rating</th>
                            <th>LLM Rating</th>
                            <th>Use Case</th>
                            <th>Future Use</th>
                            <th>Improvements</th>
                            <th>Submitted</th>
                        </tr>
                    </thead>
                    <tbody id="responsesBody">
                        <tr>
                            <td colspan="9" class="loading">
                                <i class="fas fa-spinner fa-spin"></i> Loading responses...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <script>
            async function loadData() {
                try {
                    // Show loading state
                    document.getElementById('responsesBody').innerHTML = `
                        <tr>
                            <td colspan="9" class="loading">
                                <i class="fas fa-spinner fa-spin"></i> Loading responses...
                            </td>
                        </tr>
                    `;
                    
                    // Load responses
                    const response = await fetch('/api/responses');
                    const data = await response.json();
                    
                    // Load statistics
                    await loadStatistics();
                    
                    // Update table
                    updateTable(data);
                    
                } catch (error) {
                    console.error('Error loading data:', error);
                    document.getElementById('responsesBody').innerHTML = `
                        <tr>
                            <td colspan="9" style="color: #e74c3c; text-align: center; padding: 30px;">
                                <i class="fas fa-exclamation-triangle"></i> Error loading data. Please try again.
                            </td>
                        </tr>
                    `;
                }
            }
            
            async function loadStatistics() {
                try {
                    const response = await fetch('/api/stats');
                    const stats = await response.json();
                    
                    const statsGrid = document.getElementById('statsGrid');
                    statsGrid.innerHTML = `
                        <div class="stat-card">
                            <h3><i class="fas fa-users"></i> Total Responses</h3>
                            <div class="stat-value">${stats.total_responses || 0}</div>
                            <div class="stat-label">Survey Submissions</div>
                        </div>
                        <div class="stat-card">
                            <h3><i class="fas fa-project-diagram"></i> Portal Graph</h3>
                            <div class="stat-value">${stats.q1_distribution?.portal || 0}</div>
                            <div class="stat-label">Preferred by users</div>
                        </div>
                        <div class="stat-card">
                            <h3><i class="fas fa-brain"></i> LLM Graph</h3>
                            <div class="stat-value">${stats.q1_distribution?.llm || 0}</div>
                            <div class="stat-label">Preferred by users</div>
                        </div>
                        <div class="stat-card">
                            <h3><i class="fas fa-star"></i> Average Ratings</h3>
                            <div class="stat-value">${stats.average_ratings?.portal || 0}/10</div>
                            <div class="stat-label">Portal: ${stats.average_ratings?.portal || 0}, LLM: ${stats.average_ratings?.llm || 0}</div>
                        </div>
                    `;
                    
                } catch (error) {
                    console.error('Error loading statistics:', error);
                }
            }
            
            function updateTable(data) {
                const tbody = document.getElementById('responsesBody');
                
                if (!data || data.length === 0) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="9" class="no-data">
                                <i class="fas fa-inbox"></i><br>
                                No survey responses yet
                            </td>
                        </tr>
                    `;
                    return;
                }
                
                tbody.innerHTML = '';
                
                data.forEach(item => {
                    const row = document.createElement('tr');
                    
                    // Format strengths
                    const strengths = Array.isArray(item.q2) 
                        ? item.q2.map(str => `<div style="margin: 3px 0; font-size: 12px; color: #2c3e50;">✓ ${str}</div>`).join('')
                        : `<div style="font-size: 12px;">${item.q2}</div>`;
                    
                    // Format improvements
                    const improvements = item.has_improvements && item.improvements
                        ? `<div class="improvements">${item.improvements}</div>`
                        : '<span style="color: #95a5a6;">None</span>';
                    
                    row.innerHTML = `
                        <td><strong>#${item.id}</strong></td>
                        <td>
                            <span class="badge ${item.q1 === 'portal' ? 'badge-portal' : 'badge-llm'}">
                                ${item.q1 === 'portal' ? 'Portal Graph' : 'LLM Graph'}
                            </span>
                        </td>
                        <td>${strengths}</td>
                        <td>
                            ${item.portal_rating ? `
                                <span class="rating rating-portal">
                                    ${item.portal_rating}/10
                                </span>
                            ` : '<span style="color: #95a5a6;">N/A</span>'}
                        </td>
                        <td>
                            ${item.llm_rating ? `
                                <span class="rating rating-llm">
                                    ${item.llm_rating}/10
                                </span>
                            ` : '<span style="color: #95a5a6;">N/A</span>'}
                        </td>
                        <td>
                            <div style="font-size: 13px; max-width: 200px;">
                                ${formatUseCase(item.q4)}
                            </div>
                        </td>
                        <td>
                            <div style="font-size: 13px;">
                                ${formatFutureUse(item.q5)}
                            </div>
                        </td>
                        <td class="improvements">${improvements}</td>
                        <td class="timestamp">
                            ${formatDate(item.timestamp)}
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            }
            
            function formatUseCase(q4) {
                const useCases = {
                    'test': 'Test Case Generation',
                    'user': 'User Story Generation',
                    'business': 'Business Insights',
                    'code': 'Code Review',
                    'sprint': 'Sprint Planning',
                    'architecture': 'Architecture Design',
                    'all': 'All are equally helpful'
                };
                return useCases[q4] || q4;
            }
            
            function formatFutureUse(q5) {
                const futureUses = {
                    'definitely': 'Definitely will use',
                    'probably': 'Probably will use',
                    'might': 'Might use',
                    'probably-not': 'Probably won\'t use',
                    'definitely-not': 'Definitely won\'t use'
                };
                return futureUses[q5] || q5;
            }
            
            function formatDate(timestamp) {
                const date = new Date(timestamp);
                return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            }
            
            function exportCSV() {
                window.open('/api/export/csv', '_blank');
            }
            
            async function viewStats() {
                try {
                    const response = await fetch('/api/stats');
                    const stats = await response.json();
                    
                    let statsHTML = '<h2>Detailed Statistics</h2>';
                    statsHTML += `<p><strong>Total Responses:</strong> ${stats.total_responses}</p>`;
                    statsHTML += `<p><strong>Portal vs LLM:</strong> ${stats.q1_distribution?.portal || 0} vs ${stats.q1_distribution?.llm || 0}</p>`;
                    statsHTML += `<p><strong>Average Ratings:</strong> Portal: ${stats.average_ratings?.portal || 0}/10, LLM: ${stats.average_ratings?.llm || 0}/10</p>`;
                    
                    alert(statsHTML);
                } catch (error) {
                    alert('Error loading statistics: ' + error.message);
                }
            }
            
            async function clearData() {
                if (!confirm('⚠️ WARNING: This will delete ALL survey responses. This action cannot be undone.\n\nAre you sure?')) {
                    return;
                }
                
                const password = prompt('Enter admin password to confirm:');
                if (password !== 'admin123') {
                    alert('Incorrect password. Operation cancelled.');
                    return;
                }
                
                try {
                    const response = await fetch('/api/responses', {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        alert('All responses have been cleared.');
                        loadData();
                    } else {
                        alert('Error clearing responses.');
                    }
                } catch (error) {
                    alert('Error: ' + error.message);
                }
            }
            
            // Add DELETE endpoint for responses
            app.route('/api/responses', methods=['DELETE'])(async function delete_responses() {
                try:
                    conn = sqlite3.connect('survey.db')
                    c = conn.cursor()
                    c.execute('DELETE FROM survey_responses')
                    conn.commit()
                    conn.close()
                    return jsonify({'status': 'success', 'message': 'All responses cleared'}), 200
                except Exception as e:
                    return jsonify({'status': 'error', 'message': str(e)}), 500
            })
            
            // Load data on page load
            document.addEventListener('DOMContentLoaded', loadData);
            
            // Auto-refresh every 60 seconds
            setInterval(loadData, 60000);
        </script>
    </body>
    </html>
    '''

# DELETE endpoint for responses
@app.route('/api/responses', methods=['DELETE'])
def delete_responses():
    try:
        password = request.args.get('password')
        if password != 'admin123':
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
            
        conn = sqlite3.connect('survey.db')
        c = conn.cursor()
        c.execute('DELETE FROM survey_responses')
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'message': 'All responses cleared'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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