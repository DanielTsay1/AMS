from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import sqlite3
import PyPDF2
import uuid
from datetime import datetime
import json
import re
from werkzeug.utils import secure_filename
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
DATABASE = 'ams.db'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Ensure upload directory exists
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_database():
    """Initialize the SQLite database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'processing',
            page_count INTEGER,
            document_type TEXT
        )
    ''')
    
    # Create document_content table for searchable text
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS document_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT,
            page_number INTEGER,
            content TEXT,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    ''')
    
    # Create search_logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            results_count INTEGER,
            search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def extract_text_from_pdf(file_path):
    """Extract text from PDF file"""
    try:
        text_content = []
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                if text.strip():
                    text_content.append({
                        'page': page_num + 1,
                        'text': text.strip()
                    })
        return text_content, len(pdf_reader.pages)
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        return [], 0

def determine_document_type(filename, content):
    """Determine document type based on filename and content"""
    filename_lower = filename.lower()
    content_lower = ' '.join([page['text'] for page in content]).lower()
    
    if any(word in filename_lower for word in ['policy', 'policies']):
        return 'policy'
    elif any(word in filename_lower for word in ['manual', 'guide', 'handbook']):
        return 'manual'
    elif any(word in filename_lower for word in ['faq', 'questions', 'answers']):
        return 'faq'
    elif any(word in content_lower for word in ['policy', 'procedure', 'guidelines']):
        return 'policy'
    elif any(word in content_lower for word in ['manual', 'instructions', 'how to']):
        return 'guide'
    else:
        return 'document'

def search_documents(query, doc_type=None, limit=10):
    """Search documents based on query"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Build search query
    search_terms = query.lower().split()
    where_conditions = []
    params = []
    
    # Text search across content
    for term in search_terms:
        where_conditions.append("LOWER(dc.content) LIKE ?")
        params.append(f"%{term}%")
    
    # Document type filter
    type_condition = ""
    if doc_type and doc_type != 'all':
        type_condition = "AND d.document_type = ?"
        params.append(doc_type)
    
    search_query = f"""
        SELECT DISTINCT 
            d.id, d.original_name, d.filename, d.document_type, 
            d.upload_date, dc.page_number, dc.content
        FROM documents d
        JOIN document_content dc ON d.id = dc.document_id
        WHERE d.status = 'indexed' 
        AND ({' AND '.join(where_conditions)})
        {type_condition}
        ORDER BY d.upload_date DESC
        LIMIT ?
    """
    params.append(limit)
    
    cursor.execute(search_query, params)
    results = cursor.fetchall()
    
    # Process results and calculate relevance
    processed_results = []
    for result in results:
        doc_id, original_name, filename, doc_type, upload_date, page_num, content = result
        
        # Calculate simple relevance score
        relevance = 0
        content_lower = content.lower()
        for term in search_terms:
            relevance += content_lower.count(term.lower()) * 10
        
        # Extract snippet around search terms
        snippet = extract_snippet(content, search_terms)
        
        processed_results.append({
            'id': doc_id,
            'title': original_name,
            'document': original_name,
            'filename': filename,
            'page': page_num,
            'snippet': snippet,
            'confidence': min(95, 60 + relevance),
            'type': doc_type,
            'lastUpdated': upload_date
        })
    
    # Log search
    cursor.execute(
        "INSERT INTO search_logs (query, results_count) VALUES (?, ?)",
        (query, len(processed_results))
    )
    conn.commit()
    conn.close()
    
    return processed_results

def extract_snippet(content, search_terms, snippet_length=200):
    """Extract relevant snippet from content around search terms"""
    content_lower = content.lower()
    
    # Find first occurrence of any search term
    first_match_pos = len(content)
    for term in search_terms:
        pos = content_lower.find(term.lower())
        if pos != -1 and pos < first_match_pos:
            first_match_pos = pos
    
    if first_match_pos == len(content):
        return content[:snippet_length] + "..." if len(content) > snippet_length else content
    
    # Extract snippet around the match
    start = max(0, first_match_pos - snippet_length // 2)
    end = min(len(content), start + snippet_length)
    
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    
    return snippet

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    filename = secure_filename(file.filename)
    unique_filename = f"{file_id}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    
    try:
        # Save file
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            return jsonify({'error': 'File too large (max 50MB)'}), 400
        
        # Store in database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (id, filename, original_name, file_size) VALUES (?, ?, ?, ?)",
            (file_id, unique_filename, filename, file_size)
        )
        conn.commit()
        conn.close()
        
        # Process PDF in background (simplified for this example)
        process_pdf_content(file_id, file_path, filename)
        
        return jsonify({
            'id': file_id,
            'filename': filename,
            'size': file_size,
            'status': 'processing'
        })
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

def process_pdf_content(file_id, file_path, filename):
    """Process PDF content and make it searchable"""
    try:
        # Extract text
        content, page_count = extract_text_from_pdf(file_path)
        doc_type = determine_document_type(filename, content)
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Store content
        for page_data in content:
            cursor.execute(
                "INSERT INTO document_content (document_id, page_number, content) VALUES (?, ?, ?)",
                (file_id, page_data['page'], page_data['text'])
            )
        
        # Update document status
        cursor.execute(
            "UPDATE documents SET status = ?, page_count = ?, document_type = ? WHERE id = ?",
            ('indexed', page_count, doc_type, file_id)
        )
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        # Mark as error
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("UPDATE documents SET status = ? WHERE id = ?", ('error', file_id))
        conn.commit()
        conn.close()
        print(f"Error processing PDF {file_id}: {str(e)}")

@app.route('/api/search', methods=['GET'])
def search():
    """Search documents"""
    query = request.args.get('q', '').strip()
    doc_type = request.args.get('type', 'all')
    limit = int(request.args.get('limit', 10))
    
    if not query:
        return jsonify({'error': 'Query parameter is required'}), 400
    
    try:
        results = search_documents(query, doc_type, limit)
        return jsonify({
            'query': query,
            'results': results,
            'total': len(results)
        })
    except Exception as e:
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Get all documents"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, original_name, file_size, upload_date, status, page_count, document_type
        FROM documents 
        ORDER BY upload_date DESC
    """)
    
    documents = []
    for row in cursor.fetchall():
        documents.append({
            'id': row[0],
            'name': row[1],
            'size': row[2],
            'uploadDate': row[3],
            'status': row[4],
            'pageCount': row[5],
            'type': row[6]
        })
    
    conn.close()
    return jsonify(documents)

@app.route('/api/document/<doc_id>', methods=['GET'])
def get_document(doc_id):
    """Get specific document"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Document not found'}), 404
    
    return send_from_directory(UPLOAD_FOLDER, result[0])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Total documents
    cursor.execute("SELECT COUNT(*) FROM documents WHERE status = 'indexed'")
    total_docs = cursor.fetchone()[0]
    
    # Total pages
    cursor.execute("SELECT SUM(page_count) FROM documents WHERE status = 'indexed'")
    total_pages = cursor.fetchone()[0] or 0
    
    # Recent searches
    cursor.execute("SELECT COUNT(*) FROM search_logs WHERE search_date >= datetime('now', '-24 hours')")
    recent_searches = cursor.fetchone()[0]
    
    # Document types
    cursor.execute("SELECT document_type, COUNT(*) FROM documents WHERE status = 'indexed' GROUP BY document_type")
    doc_types = dict(cursor.fetchall())
    
    conn.close()
    
    return jsonify({
        'totalDocuments': total_docs,
        'totalPages': total_pages,
        'recentSearches': recent_searches,
        'documentTypes': doc_types,
        'accuracy': 98.5  # Placeholder
    })

@app.route('/api/recent-searches', methods=['GET'])
def get_recent_searches():
    """Get recent search queries"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT query 
        FROM search_logs 
        ORDER BY search_date DESC 
        LIMIT 10
    """)
    
    searches = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(searches)

@app.route('/', methods=['GET'])
def home():
    """Home endpoint"""
    return jsonify({
        'message': 'AMS Backend API is running',
        'version': '1.0',
        'endpoints': [
            '/api/upload',
            '/api/search',
            '/api/documents',
            '/api/stats',
            '/health'
        ]
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)