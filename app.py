from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
import os
import sqlite3
import PyPDF2
import uuid
from datetime import datetime
import threading
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

def get_db():
    """Establishes a database connection or returns the existing one."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # Return rows as dict-like objects
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_database():
    """Initialize the SQLite database with FTS5 table."""
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
    
    # Create FTS5 table for searchable content
    # This table is specifically for full-text search and should be kept in sync with document_content
    # The 'content' column is indexed for full-text search
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS document_content_fts USING fts5(
            document_id, 
            page_number, 
            content, 
            tokenize='porter'
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

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    """Extract text from PDF file."""
    try:
        text_content = []
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                if text and text.strip(): # Ensure text is not None or empty after stripping
                    text_content.append({
                        'page': page_num + 1,
                        'text': text.strip()
                    })
        return text_content, len(pdf_reader.pages)
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")
        return [], 0

def determine_document_type(filename, content):
    """Determines document type based on filename and content heuristics."""
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

def process_pdf_content_background(file_id, file_path, original_filename):
    """
    Background task to process PDF content, extract text, determine type,
    and update the database for search indexing.
    """
    conn = sqlite3.connect(DATABASE) # New connection for the thread
    cursor = conn.cursor()
    
    try:
        content, page_count = extract_text_from_pdf(file_path)
        doc_type = determine_document_type(original_filename, content)
        
        # Store content in FTS5 table
        for page_data in content:
            cursor.execute(
                "INSERT INTO document_content_fts (document_id, page_number, content) VALUES (?, ?, ?)",
                (file_id, page_data['page'], page_data['text'])
            )
        
        # Update document status to indexed
        cursor.execute(
            "UPDATE documents SET status = ?, page_count = ?, document_type = ? WHERE id = ?",
            ('indexed', page_count, doc_type, file_id)
        )
        
        conn.commit()
        print(f"Successfully processed and indexed PDF: {original_filename} (ID: {file_id})")
        
    except Exception as e:
        # Mark as error if processing fails
        cursor.execute("UPDATE documents SET status = ? WHERE id = ?", ('error', file_id))
        conn.commit()
        print(f"Error processing PDF {original_filename} (ID: {file_id}): {str(e)}")
    finally:
        conn.close()
        # Clean up the physical file after processing (optional, depends on need for raw files)
        # os.remove(file_path) # Uncomment if you don't need to keep the original PDFs

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Handles file upload and initiates background PDF processing."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only PDF files (.pdf) are allowed'}), 400
    
    # Generate unique filename using UUID
    file_id = str(uuid.uuid4())
    original_filename = secure_filename(file.filename)
    unique_filename_on_disk = f"{file_id}_{original_filename}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename_on_disk)
    
    try:
        # Save file temporarily
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            return jsonify({'error': f'File too large. Max size is {MAX_FILE_SIZE / (1024 * 1024)}MB'}), 400
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO documents (id, filename, original_name, file_size, status) VALUES (?, ?, ?, ?, ?)",
            (file_id, unique_filename_on_disk, original_filename, file_size, 'processing')
        )
        db.commit()
        
        # Start background processing for PDF content extraction and indexing
        thread = threading.Thread(
            target=process_pdf_content_background, 
            args=(file_id, file_path, original_filename)
        )
        thread.daemon = True # Allow the main program to exit even if thread is running
        thread.start()
        
        return jsonify({
            'id': file_id,
            'name': original_filename,
            'size': file_size,
            'status': 'processing',
            'uploadDate': datetime.now().isoformat(),
            'pageCount': 0 # Will be updated by background process
        }), 202 # 202 Accepted, as processing is ongoing
        
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        return jsonify({'error': f'An unexpected error occurred during upload: {str(e)}'}), 500

@app.route('/api/search', methods=['GET'])
def search():
    """Searches documents using FTS5."""
    query = request.args.get('q', '').strip()
    doc_type = request.args.get('type', 'all').lower()
    limit = int(request.args.get('limit', 10))
    
    if not query:
        return jsonify({'results': [], 'total': 0, 'query': ''})
    
    db = get_db()
    cursor = db.cursor()
    
    # Build FTS5 query
    # Use "BM25" rank for better relevance sorting
    # Highlight function to mark matches in snippets
    fts_query = f"SELECT document_id, page_number, snippet(document_content_fts, 2, '<b>', '</b>', '...', 60) FROM document_content_fts WHERE content MATCH ?"
    
    params = [query + '*'] # Use '*' for prefix matching (e.g., 'remot*' matches 'remote', 'remotely')

    # Apply document type filter if specified
    type_filter_condition = ""
    if doc_type and doc_type != 'all':
        # Need to join with the documents table to filter by document_type
        fts_query = f"""
            SELECT T.document_id, T.page_number, snippet(T, 2, '<b>', '</b>', '...', 60) 
            FROM document_content_fts AS T 
            JOIN documents AS d ON T.document_id = d.id 
            WHERE T.content MATCH ? AND d.document_type = ?
        """
        params.append(doc_type)

    # Add ORDER BY and LIMIT
    fts_query += " ORDER BY bm25(document_content_fts) DESC LIMIT ?"
    params.append(limit)

    try:
        cursor.execute(fts_query, params)
        fts_matches = cursor.fetchall()
        
        results_data = []
        document_ids_seen = set() # To get distinct documents

        for match in fts_matches:
            doc_id, page_num, highlighted_snippet = match
            
            # Fetch document details for the matched content
            doc_cursor = db.cursor()
            doc_cursor.execute(
                "SELECT original_name, upload_date, document_type, page_count FROM documents WHERE id = ?", 
                (doc_id,)
            )
            doc_details = doc_cursor.fetchone()

            if doc_details:
                # Calculate a simple confidence (placeholder, FTS5 doesn't give a direct % like previous example)
                # You could implement a more sophisticated confidence metric based on term frequency etc.
                confidence = min(100, 70 + highlighted_snippet.count('<b>') * 5) # Example: higher confidence for more highlights

                results_data.append({
                    'id': doc_id,
                    'title': doc_details['original_name'],
                    'document': doc_details['original_name'], # For display in frontend
                    'filename': doc_details['original_name'], # Original filename, for display
                    'page': page_num,
                    'snippet': highlighted_snippet,
                    'confidence': confidence,
                    'type': doc_details['document_type'],
                    'lastUpdated': doc_details['upload_date']
                })
        
        # Log search
        cursor.execute(
            "INSERT INTO search_logs (query, results_count) VALUES (?, ?)",
            (query, len(results_data))
        )
        db.commit()
        
        return jsonify({
            'query': query,
            'results': results_data,
            'total': len(results_data)
        })
    except sqlite3.OperationalError as e:
        if "no such function: snippet" in str(e) or "no such module: fts5" in str(e):
             return jsonify({'error': 'Full-text search (FTS5) module is not enabled in your SQLite. Please compile SQLite with FTS5 support.'}), 500
        return jsonify({'error': f'Database operational error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Gets metadata for all uploaded documents."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, original_name, file_size, upload_date, status, page_count, document_type
        FROM documents 
        ORDER BY upload_date DESC
    """)
    
    documents = []
    for row in cursor.fetchall():
        documents.append({
            'id': row['id'],
            'name': row['original_name'],
            'size': row['file_size'],
            'uploadDate': row['upload_date'],
            'status': row['status'],
            'pageCount': row['page_count'],
            'type': row['document_type']
        })
    
    return jsonify(documents)

@app.route('/api/document/<doc_id>', methods=['GET'])
def get_document(doc_id):
    """Serves a specific PDF document by its unique ID."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT filename, original_name FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    
    if not result:
        return jsonify({'error': 'Document not found'}), 404
    
    # Use the filename stored on disk, and serve it with the original_name
    return send_from_directory(UPLOAD_FOLDER, result['filename'], as_attachment=False, download_name=result['original_name'])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Gets system statistics."""
    db = get_db()
    cursor = db.cursor()
    
    # Total indexed documents
    cursor.execute("SELECT COUNT(*) FROM documents WHERE status = 'indexed'")
    total_docs = cursor.fetchone()[0]
    
    # Total pages indexed
    cursor.execute("SELECT SUM(page_count) FROM documents WHERE status = 'indexed'")
    total_pages = cursor.fetchone()[0] or 0
    
    # Recent searches (last 24 hours)
    cursor.execute("SELECT COUNT(*) FROM search_logs WHERE search_date >= datetime('now', '-24 hours')")
    recent_searches_count = cursor.fetchone()[0]
    
    # Last update time (latest document upload)
    cursor.execute("SELECT MAX(upload_date) FROM documents WHERE status = 'indexed'")
    last_updated_ts = cursor.fetchone()[0]
    last_updated_readable = "N/A"
    if last_updated_ts:
        # Assuming upload_date is stored as ISO format string
        dt_object = datetime.fromisoformat(last_updated_ts) 
        time_diff = datetime.now() - dt_object
        if time_diff.total_seconds() < 60:
            last_updated_readable = "just now"
        elif time_diff.total_seconds() < 3600:
            minutes = int(time_diff.total_seconds() / 60)
            last_updated_readable = f"{minutes} minutes ago"
        elif time_diff.total_seconds() < 86400:
            hours = int(time_diff.total_seconds() / 3600)
            last_updated_readable = f"{hours} hours ago"
        else:
            days = int(time_diff.total_seconds() / 86400)
            last_updated_readable = f"{days} days ago"

    # Document types
    cursor.execute("SELECT document_type, COUNT(*) FROM documents WHERE status = 'indexed' GROUP BY document_type")
    doc_types = dict(cursor.fetchall())
    
    return jsonify({
        'totalDocuments': total_docs,
        'totalPages': total_pages,
        'recentSearches': recent_searches_count,
        'documentTypes': doc_types,
        'lastUpdated': last_updated_readable,
        'accuracy': 98.5 # This is still a placeholder, actual accuracy would need ML
    })

@app.route('/api/recent-searches', methods=['GET'])
def get_recent_searches():
    """Gets recent distinct search queries."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT DISTINCT query 
        FROM search_logs 
        ORDER BY search_date DESC 
        LIMIT 5
    """)
    
    searches = [row['query'] for row in cursor.fetchall()]
    return jsonify(searches)

@app.route('/', methods=['GET'])
def home():
    """Home endpoint for API status."""
    return jsonify({
        'message': 'AMS Backend API is running',
        'version': '1.1',
        'endpoints': [
            '/api/upload',
            '/api/search',
            '/api/documents',
            '/api/stats',
            '/api/recent-searches',
            '/health'
        ]
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)