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
            document_type TEXT,
            error_message TEXT
        )
    ''')
    
    # Create FTS5 table for searchable content
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
    print("Database initialized successfully")

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
                if text and text.strip():
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
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        print(f"Starting background processing for {original_filename} (ID: {file_id})")
        
        content, page_count = extract_text_from_pdf(file_path)
        
        if not content:
            raise Exception("No text content could be extracted from the PDF")
            
        doc_type = determine_document_type(original_filename, content)
        
        print(f"Extracted {len(content)} pages of text from {original_filename}")
        
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
        error_msg = str(e)
        print(f"Error processing PDF {original_filename} (ID: {file_id}): {error_msg}")
        
        # Mark as error with error message
        cursor.execute(
            "UPDATE documents SET status = ?, error_message = ? WHERE id = ?", 
            ('error', error_msg, file_id)
        )
        conn.commit()
    finally:
        conn.close()

@app.route('/api/search', methods=['GET', 'POST'])
def search():
    if request.method == 'GET':
        query = request.args.get('q', '').strip()
    else:
        data = request.get_json() or {}
        query = data.get('q') or data.get('query') or data.get('search_term', '')
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
        
        print(f"File uploaded: {original_filename} (ID: {file_id}, Size: {file_size} bytes)")
        
        # Start background processing for PDF content extraction and indexing
        thread = threading.Thread(
            target=process_pdf_content_background, 
            args=(file_id, file_path, original_filename)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'id': file_id,
            'name': original_filename,
            'size': file_size,
            'status': 'processing',
            'uploadDate': datetime.now().isoformat(),
            'pageCount': 0
        }), 202
        
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        error_msg = f'An unexpected error occurred during upload: {str(e)}'
        print(f"Upload error: {error_msg}")
        return jsonify({'error': error_msg}), 500

@app.route('/api/search', methods=['GET'])
def search():
    """Searches documents using FTS5."""
    query = request.args.get('q', '').strip()
    doc_type = request.args.get('type', 'all').lower()
    limit = int(request.args.get('limit', 10))
    
    print(f"Search request - Query: '{query}', Type: '{doc_type}', Limit: {limit}")
    
    if not query:
        return jsonify({'results': [], 'total': 0, 'query': ''})
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        # First check if we have any indexed documents
        cursor.execute("SELECT COUNT(*) FROM documents WHERE status = 'indexed'")
        indexed_count = cursor.fetchone()[0]
        print(f"Total indexed documents: {indexed_count}")
        
        if indexed_count == 0:
            return jsonify({
                'query': query,
                'results': [],
                'total': 0,
                'message': 'No documents have been indexed yet. Please upload and wait for documents to be processed.'
            })
        
        # Clean the query to prevent FTS5 syntax errors
        clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
        if not clean_query:
            return jsonify({'results': [], 'total': 0, 'query': query})
        
        # Use simple word matching for better compatibility
        search_terms = clean_query.split()
        fts_query_terms = ' OR '.join([f'"{term}"' for term in search_terms])
        
        print(f"FTS query terms: {fts_query_terms}")
        
        # Build FTS5 query with proper syntax
        if doc_type and doc_type != 'all':
            fts_query = """
                SELECT T.document_id, T.page_number, T.content
                FROM document_content_fts AS T 
                JOIN documents AS d ON T.document_id = d.id 
                WHERE document_content_fts MATCH ? AND d.document_type = ? AND d.status = 'indexed'
                LIMIT ?
            """
            params = [fts_query_terms, doc_type, limit]
        else:
            fts_query = """
                SELECT T.document_id, T.page_number, T.content
                FROM document_content_fts AS T 
                JOIN documents AS d ON T.document_id = d.id 
                WHERE document_content_fts MATCH ? AND d.status = 'indexed'
                LIMIT ?
            """
            params = [fts_query_terms, limit]

        print(f"Executing query: {fts_query}")
        print(f"Parameters: {params}")
        
        cursor.execute(fts_query, params)
        fts_matches = cursor.fetchall()
        
        print(f"Found {len(fts_matches)} matches")
        
        results_data = []

        for match in fts_matches:
            doc_id, page_num, content = match
            
            # Fetch document details
            doc_cursor = db.cursor()
            doc_cursor.execute(
                "SELECT original_name, upload_date, document_type, page_count FROM documents WHERE id = ? AND status = 'indexed'", 
                (doc_id,)
            )
            doc_details = doc_cursor.fetchone()

            if doc_details:
                # Create snippet with highlighting
                snippet = create_snippet(content, search_terms)
                
                # Calculate confidence based on term matches
                confidence = calculate_confidence(content, search_terms)

                result_item = {
                    'id': doc_id,
                    'title': doc_details['original_name'].replace('.pdf', ''),
                    'document': doc_details['original_name'],
                    'page': page_num, 
                    'snippet': snippet,
                    'confidence': confidence,
                    'type': doc_details['document_type'] or 'document',
                    'lastUpdated': doc_details['upload_date']
                }
                
                results_data.append(result_item)
                print(f"Added result: {result_item['title']} (page {page_num}, confidence: {confidence}%)")
        
        # Log search
        try:
            cursor.execute(
                "INSERT INTO search_logs (query, results_count) VALUES (?, ?)",
                (query, len(results_data))
            )
            db.commit()
        except Exception as log_error:
            print(f"Failed to log search: {log_error}")
        
        response = {
            'query': query,
            'results': results_data,
            'total': len(results_data)
        }
        
        print(f"Returning {len(results_data)} results")
        return jsonify(response)
        
    except sqlite3.OperationalError as e:
        error_msg = str(e)
        print(f"SQLite error: {error_msg}")
        
        if "no such module: fts5" in error_msg:
            return jsonify({
                'error': 'FTS5 full-text search is not available in your SQLite installation. Please upgrade SQLite or recompile with FTS5 support.'
            }), 500
        elif "fts5: syntax error" in error_msg:
            return jsonify({
                'error': f'Search syntax error. Try using simpler search terms.'
            }), 400
        else:
            return jsonify({'error': f'Database error: {error_msg}'}), 500
            
    except Exception as e:
        error_msg = str(e)
        print(f"Search error: {error_msg}")
        return jsonify({'error': f'Search failed: {error_msg}'}), 500

def create_snippet(content, search_terms):
    """Create a highlighted snippet from content."""
    if not content or not search_terms:
        return "No preview available"
    
    # Find the first occurrence of any search term
    content_lower = content.lower()
    best_pos = len(content)
    
    for term in search_terms:
        pos = content_lower.find(term.lower())
        if pos != -1 and pos < best_pos:
            best_pos = pos
    
    # If no terms found, return beginning
    if best_pos == len(content):
        best_pos = 0
    
    # Extract snippet around the found position
    start = max(0, best_pos - 100)
    end = min(len(content), best_pos + 200)
    snippet = content[start:end]
    
    # Add ellipsis if needed
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    
    # Highlight search terms
    for term in search_terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        snippet = pattern.sub(f'<b>{term}</b>', snippet)
    
    return snippet

def calculate_confidence(content, search_terms):
    """Calculate search confidence based on term frequency."""
    if not content or not search_terms:
        return 50
    
    content_lower = content.lower()
    total_matches = 0
    
    for term in search_terms:
        matches = content_lower.count(term.lower())
        total_matches += matches
    
    # Base confidence + bonus for matches
    confidence = min(100, 60 + (total_matches * 8))
    return confidence

@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Gets metadata for all uploaded documents."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, original_name, file_size, upload_date, status, page_count, document_type, error_message
        FROM documents 
        ORDER BY upload_date DESC
    """)
    
    documents = []
    for row in cursor.fetchall():
        doc_data = {
            'id': row['id'],
            'name': row['original_name'],
            'size': row['file_size'],
            'uploadDate': row['upload_date'],
            'status': row['status'],
            'pageCount': row['page_count'],
            'type': row['document_type']
        }
        
        # Add error message if status is error
        if row['status'] == 'error' and row['error_message']:
            doc_data['error'] = row['error_message']
            
        documents.append(doc_data)
    
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
    
    file_path = os.path.join(UPLOAD_FOLDER, result['filename'])
    if not os.path.exists(file_path):
        return jsonify({'error': 'Document file not found on disk'}), 404
    
    return send_from_directory(UPLOAD_FOLDER, result['filename'], 
                             as_attachment=False, 
                             download_name=result['original_name'])

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
    
    # Last update time
    cursor.execute("SELECT MAX(upload_date) FROM documents WHERE status = 'indexed'")
    last_updated_ts = cursor.fetchone()[0]
    last_updated_readable = "No documents yet"
    
    if last_updated_ts:
        try:
            dt_object = datetime.fromisoformat(last_updated_ts.replace('Z', '+00:00'))
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
        except:
            last_updated_readable = "recently"

    # Document types
    cursor.execute("SELECT document_type, COUNT(*) FROM documents WHERE status = 'indexed' GROUP BY document_type")
    doc_types = dict(cursor.fetchall())
    
    return jsonify({
        'totalDocuments': total_docs,
        'totalPages': total_pages,
        'recentSearches': recent_searches_count,
        'documentTypes': doc_types,
        'lastUpdated': last_updated_readable,
        'accuracy': 95.0
    })

@app.route('/api/recent-searches', methods=['GET'])
def get_recent_searches():
    """Gets recent distinct search queries."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT DISTINCT query 
        FROM search_logs 
        WHERE query != '' 
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
        'version': '1.2',
        'status': 'healthy',
        'endpoints': [
            '/api/upload',
            '/api/search', 
            '/api/documents',
            '/api/document/<id>',
            '/api/stats',
            '/api/recent-searches',
            '/health'
        ]
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    db = get_db()
    cursor = db.cursor()
    
    # Quick database check
    try:
        cursor.execute("SELECT COUNT(*) FROM documents")
        doc_count = cursor.fetchone()[0]
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected',
            'documents': doc_count
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("Initializing AMS Backend...")
    init_database()
    print("Starting server on http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)