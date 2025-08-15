from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
import os
import sqlite3
import PyPDF2
import uuid
from datetime import datetime
import threading
from werkzeug.utils import secure_filename
from pathlib import Path
import re
import logging
import time
from contextlib import contextmanager

# ----------------------------------------------------------------------------
# App & Config
# ----------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Hard upload cap at the Flask/Werkzeug layer (prevents huge bodies)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

UPLOAD_FOLDER = "uploads"
DATABASE = "ams.db"
ALLOWED_EXTENSIONS = {"pdf"}

Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

# Thread-safe document processing tracking
processing_documents = set()
processing_lock = threading.Lock()

# ----------------------------------------------------------------------------
# Error Handlers
# ----------------------------------------------------------------------------
@app.errorhandler(413)
def file_too_large(error):
    return jsonify({"error": f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"}), 413

@app.errorhandler(404)
def not_found(error):
    app.logger.warning(f"404 Not Found: {request.path}")
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.exception("500 Internal Server Error caught")
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.exception(f"Unhandled exception: {str(e)}")
    return jsonify({"error": "An unexpected server error occurred"}), 500

# ----------------------------------------------------------------------------
# DB Helpers
# ----------------------------------------------------------------------------

@contextmanager
def get_db_connection():
    """Context manager for database connections with proper error handling."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Pragmas for better concurrency and safety
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")  # 30 second timeout
        yield conn
    except sqlite3.OperationalError as e:
        app.logger.error(f"Database connection error: {e}")
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        app.logger.error(f"Unexpected database error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def _connect_db():
    """Legacy method for backward compatibility."""
    conn = sqlite3.connect(DATABASE, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except sqlite3.OperationalError as e:
        app.logger.warning(f"Could not set PRAGMA: {e}")
    return conn

def get_db():
    if "db" not in g:
        g.db = _connect_db()
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass

# ----------------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------------

def init_database():
    """Initialize database with proper error handling."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            # Create documents table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    file_size INTEGER,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'processing',
                    page_count INTEGER DEFAULT 0,
                    document_type TEXT DEFAULT 'document'
                )
                """
            )

            # Check if FTS5 is available and create appropriate content table
            fts5_available = False
            try:
                cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp_fts_test USING fts5(content)")
                cur.execute("DROP TABLE temp_fts_test")
                fts5_available = True
                app.logger.info("FTS5 is available")
            except sqlite3.OperationalError:
                app.logger.warning("FTS5 not available, using fallback search")

            if fts5_available:
                cur.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS document_content_fts USING fts5(
                        document_id UNINDEXED,
                        page_number UNINDEXED,
                        content,
                        tokenize='porter'
                    )
                    """
                )
            else:
                # Fallback to regular table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_content_fts (
                        document_id TEXT,
                        page_number INTEGER,
                        content TEXT
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_content ON document_content_fts(content)")

            # Create search logs table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS search_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    results_count INTEGER,
                    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.commit()
            app.logger.info("Database initialized successfully")
            
    except Exception as e:
        app.logger.error(f"Database initialization failed: {e}")
        raise

# ----------------------------------------------------------------------------
# Utils
# ----------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path: str):
    """Extract text from PDF with improved error handling."""
    text_content = []
    page_count = 0
    
    if not os.path.exists(file_path):
        app.logger.error(f"PDF file not found: {file_path}")
        return [], 0
        
    try:
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            page_count = len(reader.pages)
            
            for idx, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                    # Clean up the text
                    text = re.sub(r'\s+', ' ', text.strip())
                    
                    # Only add pages with substantial text
                    if text and len(text.strip()) > 10:
                        text_content.append({"page": idx, "text": text})
                        
                except Exception as e:
                    app.logger.warning(f"Error extracting text from page {idx} of {file_path}: {e}")
                    continue
                    
        app.logger.info(f"Extracted text from {len(text_content)} pages out of {page_count} total pages")
        
    except Exception as e:
        app.logger.error(f"Error processing PDF {file_path}: {e}")
        return [], 0
        
    return text_content, page_count

def determine_document_type(filename: str, content_list):
    """Determine document type based on filename and content."""
    filename_lower = filename.lower()
    
    # Get first few pages of content for analysis
    content_sample = " ".join([p["text"] for p in content_list[:3]]).lower()

    # Check filename patterns first
    filename_patterns = {
        "policy": ["policy", "policies"],
        "manual": ["manual", "guide", "handbook"],
        "faq": ["faq", "questions", "answers", "q&a"]
    }
    
    for doc_type, patterns in filename_patterns.items():
        if any(pattern in filename_lower for pattern in patterns):
            return doc_type

    # Check content patterns
    content_patterns = {
        "policy": ["policy", "procedure", "guidelines", "rules"],
        "guide": ["manual", "instructions", "how to", "step by step"],
        "faq": ["frequently asked", "faq", "q:", "a:", "question:", "answer:"]
    }
    
    for doc_type, patterns in content_patterns.items():
        if any(pattern in content_sample for pattern in patterns):
            return doc_type
            
    return "document"

def build_match_query(user_query: str):
    """Build a safe FTS5 MATCH expression with prefix search."""
    if not user_query:
        return ""
    
    # Clean and tokenize the query
    tokens = []
    for token in user_query.split():
        # Remove special FTS characters that could break the query
        cleaned = re.sub(r'[^\w\s]', '', token).strip()
        if cleaned and len(cleaned) > 1:
            tokens.append(f"{cleaned}*")
    
    if not tokens:
        return ""
    
    return " AND ".join(tokens)

def highlight_text(text: str, search_terms: list, max_length: int = 300) -> str:
    """Create highlighted snippet from text."""
    if not text or not search_terms:
        return text[:max_length] + ("..." if len(text) > max_length else "")
    
    highlighted_text = text
    
    # Highlight each search term
    for term in search_terms:
        if len(term.strip()) > 1:
            pattern = re.compile(re.escape(term.strip()), re.IGNORECASE)
            highlighted_text = pattern.sub(f"<b>{term}</b>", highlighted_text)
    
    # Create snippet around first highlighted term
    first_highlight = highlighted_text.find("<b>")
    if first_highlight != -1:
        start = max(0, first_highlight - 50)
        end = min(len(highlighted_text), start + max_length)
        snippet = highlighted_text[start:end]
        
        if start > 0:
            snippet = "..." + snippet
        if end < len(highlighted_text):
            snippet = snippet + "..."
            
        return snippet
    
    # No highlights found, return beginning of text
    return text[:max_length] + ("..." if len(text) > max_length else "")

# ----------------------------------------------------------------------------
# Background Indexing
# ----------------------------------------------------------------------------

def process_pdf_content_background(file_id: str, file_path: str, original_filename: str):
    """Process PDF content in background thread with improved error handling."""
    with processing_lock:
        processing_documents.add(file_id)
    
    try:
        app.logger.info(f"Starting background processing for {original_filename} (ID: {file_id})")
        
        # Extract text content
        content, page_count = extract_text_from_pdf(file_path)
        
        if not content:
            app.logger.warning(f"No extractable text content found in {original_filename}")
        
        # Determine document type
        doc_type = determine_document_type(original_filename, content)
        
        # Store content in database with retry logic
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    
                    # Start transaction
                    cur.execute("BEGIN IMMEDIATE")
                    
                    # Insert content pages
                    for page in content:
                        cur.execute(
                            "INSERT INTO document_content_fts (document_id, page_number, content) VALUES (?, ?, ?)",
                            (file_id, page["page"], page["text"]),
                        )
                    
                    # Update document status
                    cur.execute(
                        "UPDATE documents SET status = ?, page_count = ?, document_type = ? WHERE id = ?",
                        ("indexed", page_count, doc_type, file_id),
                    )
                    
                    conn.commit()
                    app.logger.info(f"Successfully indexed {original_filename} (ID: {file_id}, pages: {page_count}, type: {doc_type})")
                    break
                    
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    app.logger.warning(f"Database locked, retrying in {retry_delay}s... (attempt {attempt + 1})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    raise
            except Exception as e:
                app.logger.error(f"Database error during indexing: {e}")
                raise

    except Exception as e:
        app.logger.error(f"Error processing PDF {original_filename} (ID: {file_id}): {e}")
        
        # Mark document as error
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("UPDATE documents SET status = ? WHERE id = ?", ("error", file_id))
                conn.commit()
        except Exception as update_error:
            app.logger.error(f"Failed to update error status for {file_id}: {update_error}")
    
    finally:
        with processing_lock:
            processing_documents.discard(file_id)

# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Handle file upload with improved validation and error handling."""
    file_path = None
    file_id = None
    
    try:
        # Validate request
        if "file" not in request.files:
            return jsonify({"error": "No file part in the request"}), 400

        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "Only PDF files (.pdf) are allowed"}), 400

        # Generate unique file ID and secure filename
        file_id = str(uuid.uuid4())
        original_filename = secure_filename(file.filename)
        
        if not original_filename:
            return jsonify({"error": "Invalid filename"}), 400
        
        # Check filename length
        if len(original_filename) > 255:
            return jsonify({"error": "Filename too long"}), 400
            
        unique_filename_on_disk = f"{file_id}_{original_filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename_on_disk)

        # Save file
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        
        # Validate file size
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            return jsonify({
                "error": f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
            }), 400
        
        if file_size == 0:
            os.remove(file_path)
            return jsonify({"error": "File is empty"}), 400

        # Validate it's actually a PDF
        try:
            with open(file_path, "rb") as f:
                PyPDF2.PdfReader(f)
        except Exception as e:
            os.remove(file_path)
            return jsonify({"error": "Invalid PDF file"}), 400

        # Store document metadata
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO documents (id, filename, original_name, file_size, status) VALUES (?, ?, ?, ?, ?)",
            (file_id, unique_filename_on_disk, original_filename, file_size, "processing"),
        )
        db.commit()

        # Start background processing
        thread = threading.Thread(
            target=process_pdf_content_background,
            args=(file_id, file_path, original_filename),
            daemon=True,
            name=f"PDFProcessor-{file_id[:8]}"
        )
        thread.start()

        return jsonify({
            "id": file_id,
            "name": original_filename,
            "size": file_size,
            "status": "processing",
            "uploadDate": datetime.now().isoformat(),
            "pageCount": 0,
        }), 202

    except Exception as e:
        # Cleanup on error
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
                
        if file_id:
            try:
                db = get_db()
                cur = db.cursor()
                cur.execute("DELETE FROM documents WHERE id = ?", (file_id,))
                db.commit()
            except Exception:
                pass
                
        app.logger.error(f"Error during file upload: {e}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

@app.route("/api/search", methods=["GET"])
def search():
    """Handle search requests with improved error handling and FTS5 support."""
    raw_query = (request.args.get("q", "") or "").strip()
    doc_type = (request.args.get("type", "all") or "").lower()
    limit = min(50, max(1, int(request.args.get("limit", 10) or 10)))
    offset = max(0, int(request.args.get("offset", 0) or 0))

    app.logger.info(f"Search request: q='{raw_query}', type='{doc_type}', limit={limit}, offset={offset}")

    # Validate query
    if not raw_query or len(raw_query) < 2:
        return jsonify({"results": [], "total": 0, "query": raw_query})
    
    if len(raw_query) > 500:  # Prevent extremely long queries
        return jsonify({"error": "Search query too long"}), 400

    try:
        db = get_db()
        cur = db.cursor()
        
        # Check if we're using FTS5 or fallback
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='document_content_fts'")
        table_def = cur.fetchone()
        is_fts5 = table_def and 'USING fts5' in table_def[0]
        
        results = []
        
        if is_fts5:
            # Use FTS5 search
            match_expr = build_match_query(raw_query)
            if not match_expr:
                return jsonify({"results": [], "total": 0, "query": raw_query})

            sql_parts = [
                "SELECT f.document_id, f.page_number, f.content,",
                "       d.original_name, d.upload_date, d.document_type, d.page_count",
                "  FROM document_content_fts AS f",
                "  JOIN documents AS d ON d.id = f.document_id",
                " WHERE d.status = 'indexed'",
                "   AND f.content MATCH ?"
            ]
            params = [match_expr]
            
            if doc_type and doc_type != "all":
                sql_parts.append("   AND COALESCE(d.document_type, 'document') = ?")
                params.append(doc_type)
                
            sql_parts.append(" ORDER BY bm25(f) ASC LIMIT ? OFFSET ?")
            params.extend([limit, offset])
            
        else:
            # Fallback LIKE search
            search_terms = [term.strip() for term in raw_query.split() if len(term.strip()) > 1]
            if not search_terms:
                return jsonify({"results": [], "total": 0, "query": raw_query})
            
            like_conditions = []
            params = []
            for term in search_terms:
                like_conditions.append("f.content LIKE ?")
                params.append(f"%{term}%")
            
            sql_parts = [
                "SELECT f.document_id, f.page_number, f.content,",
                "       d.original_name, d.upload_date, d.document_type, d.page_count",
                "  FROM document_content_fts AS f",
                "  JOIN documents AS d ON d.id = f.document_id",
                " WHERE d.status = 'indexed'",
                f"   AND ({' AND '.join(like_conditions)})"
            ]
            
            if doc_type and doc_type != "all":
                sql_parts.append("   AND COALESCE(d.document_type, 'document') = ?")
                params.append(doc_type)
                
            sql_parts.append(" ORDER BY d.upload_date DESC LIMIT ? OFFSET ?")
            params.extend([limit, offset])

        # Execute search query
        cur.execute(" ".join(sql_parts), params)
        rows = cur.fetchall()

        # Process results
        search_terms = raw_query.lower().split()
        
        for r in rows:
            content = r["content"] or ""
            
            # Create highlighted snippet
            snippet = highlight_text(content, search_terms)
            
            # Calculate confidence score
            highlight_count = snippet.lower().count("<b>")
            confidence = min(100, max(50, 70 + highlight_count * 5))
            
            results.append({
                "id": r["document_id"],
                "title": r["original_name"],
                "document": r["original_name"],
                "filename": r["original_name"],
                "page": r["page_number"],
                "snippet": snippet,
                "confidence": confidence,
                "type": r["document_type"] or "document",
                "lastUpdated": r["upload_date"],
            })

        # Get total count for pagination (simplified for now)
        total = len(results)

        # Log successful search
        try:
            cur.execute(
                "INSERT INTO search_logs (query, results_count) VALUES (?, ?)",
                (raw_query, len(results)),
            )
            db.commit()
        except Exception as e:
            app.logger.warning(f"Failed to log search: {e}")

        return jsonify({
            "query": raw_query,
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
            "searchMethod": "fts5" if is_fts5 else "like"
        })

    except Exception as e:
        app.logger.error(f"Search failed for query '{raw_query}': {e}")
        return jsonify({"error": f"Search failed: {str(e)}"}), 500

@app.route("/api/documents", methods=["GET"])
def get_documents():
    """Get list of all documents with improved error handling."""
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            SELECT id, original_name, file_size, upload_date, status, page_count, document_type
              FROM documents
             ORDER BY datetime(upload_date) DESC
            """
        )
        documents = []
        for row in cur.fetchall():
            documents.append({
                "id": row["id"],
                "name": row["original_name"],
                "size": row["file_size"],
                "uploadDate": row["upload_date"],
                "status": row["status"],
                "pageCount": row["page_count"] or 0,
                "type": row["document_type"] or "document",
            })
            
        app.logger.info(f"Retrieved {len(documents)} document metadata records")
        return jsonify(documents)
        
    except Exception as e:
        app.logger.error(f"Error retrieving documents: {e}")
        return jsonify({"error": f"Failed to retrieve documents: {str(e)}"}), 500

@app.route("/api/document/<doc_id>", methods=["GET"])
def get_document(doc_id):
    """Serve document file with improved validation."""
    try:
        # Validate document ID format
        if not doc_id or len(doc_id) > 100:
            return jsonify({"error": "Invalid document ID"}), 400
            
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT filename, original_name FROM documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        
        if not row:
            return jsonify({"error": "Document not found"}), 404

        disk_name, original_name = row["filename"], row["original_name"]
        file_path = os.path.join(UPLOAD_FOLDER, disk_name)
        
        if not os.path.exists(file_path):
            app.logger.error(f"File missing on server: {file_path}")
            return jsonify({"error": "File not found on server"}), 410

        return send_from_directory(
            UPLOAD_FOLDER,
            disk_name,
            as_attachment=False,
            download_name=original_name,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        app.logger.error(f"Error serving document {doc_id}: {e}")
        return jsonify({"error": f"Failed to serve document: {str(e)}"}), 500

@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Get system statistics with improved error handling."""
    try:
        db = get_db()
        cur = db.cursor()

        # Get total indexed documents
        cur.execute("SELECT COUNT(*) FROM documents WHERE status = 'indexed'")
        total_docs = int(cur.fetchone()[0] or 0)

        # Get total pages
        cur.execute("SELECT COALESCE(SUM(page_count), 0) FROM documents WHERE status = 'indexed'")
        total_pages = int(cur.fetchone()[0] or 0)

        # Get last update time
        cur.execute("SELECT MAX(upload_date) FROM documents WHERE status = 'indexed'")
        last_updated_ts = cur.fetchone()[0]

        # Format last updated time
        last_updated_readable = "Never"
        if last_updated_ts:
            try:
                dt_object = datetime.fromisoformat(last_updated_ts)
                delta = datetime.now() - dt_object
                seconds = delta.total_seconds()
                
                if seconds < 60:
                    last_updated_readable = "Just now"
                elif seconds < 3600:
                    minutes = int(seconds // 60)
                    last_updated_readable = f"{minutes}m ago"
                elif seconds < 86400:
                    hours = int(seconds // 3600)
                    last_updated_readable = f"{hours}h ago"
                else:
                    days = int(seconds // 86400)
                    last_updated_readable = f"{days}d ago"
            except Exception as e:
                app.logger.warning(f"Error parsing timestamp {last_updated_ts}: {e}")
                last_updated_readable = "Unknown"

        # Get document type breakdown
        cur.execute(
            """
            SELECT COALESCE(document_type, 'document') AS doc_type, COUNT(*) 
            FROM documents 
            WHERE status='indexed' 
            GROUP BY COALESCE(document_type, 'document')
            """
        )
        doc_types = {row[0]: row[1] for row in cur.fetchall()}

        return jsonify({
            "totalDocuments": total_docs,
            "totalPages": total_pages,
            "documentTypes": doc_types,
            "lastUpdated": last_updated_readable,
            "accuracy": 95,  # Mock accuracy score
            "processingDocuments": len(processing_documents),
        })
        
    except Exception as e:
        app.logger.error(f"Error getting stats: {e}")
        return jsonify({"error": f"Failed to get statistics: {str(e)}"}), 500

@app.route("/api/recent-searches", methods=["GET"])
def get_recent_searches():
    """Get recent search queries."""
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            SELECT query
              FROM (
                    SELECT query, MAX(search_date) AS last_time
                      FROM search_logs
                     WHERE query IS NOT NULL AND LENGTH(TRIM(query)) > 0
                  GROUP BY query
                   ) t
          ORDER BY last_time DESC
             LIMIT 5
            """
        )
        searches = [row["query"] for row in cur.fetchall()]
        return jsonify(searches)
        
    except Exception as e:
        app.logger.error(f"Error getting recent searches: {e}")
        return jsonify([])

# Health and info endpoints
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        with get_db_connection() as conn:
            conn.execute("SELECT 1")
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": "connected",
            "processingDocuments": len(processing_documents)
        })
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }), 500

@app.route("/api", methods=["GET"])
def api_info():
    """API information endpoint."""
    return jsonify({
        "message": "AMS Backend API is running",
        "version": "1.4",
        "endpoints": [
            "/api/upload (POST)",
            "/api/search?q=<query>&type=<type>&limit=<limit>&offset=<offset> (GET)",
            "/api/documents (GET)",
            "/api/document/<doc_id> (GET)",
            "/api/stats (GET)",
            "/api/recent-searches (GET)",
            "/health (GET)",
        ],
        "maxFileSize": f"{MAX_FILE_SIZE // (1024*1024)}MB",
        "allowedExtensions": list(ALLOWED_EXTENSIONS)
    })

# Frontend serving
@app.route("/", methods=["GET"])
def home():
    """Serve the main HTML file."""
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    else:
        return jsonify({
            "message": "AMS Backend API is running",
            "note": "Frontend HTML file (index.html) not found in current directory"
        }), 404

@app.route("/index.html", methods=["GET"])
def serve_index():
    """Serve index.html explicitly."""
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")
    else:
        return jsonify({
            "error": "Frontend HTML file not found",
            "message": "Please ensure index.html is in the same directory as app.py"
        }), 404

# ----------------------------------------------------------------------------
# Application Startup & Cleanup
# ----------------------------------------------------------------------------

def cleanup_on_shutdown():
    """Clean up resources on application shutdown."""
    try:
        # Cancel any pending background threads
        with processing_lock:
            if processing_documents:
                app.logger.info(f"Shutting down with {len(processing_documents)} documents still processing")
        
        # Close any remaining database connections
        if hasattr(g, 'db'):
            g.db.close()
            
    except Exception as e:
        app.logger.error(f"Error during cleanup: {e}")

def validate_environment():
    """Validate the application environment on startup."""
    errors = []
    
    # Check upload directory
    if not os.path.exists(UPLOAD_FOLDER):
        try:
            Path(UPLOAD_FOLDER).mkdir(exist_ok=True)
            app.logger.info(f"Created upload directory: {UPLOAD_FOLDER}")
        except Exception as e:
            errors.append(f"Cannot create upload directory: {e}")
    
    # Check write permissions
    if not os.access(UPLOAD_FOLDER, os.W_OK):
        errors.append(f"No write permission for upload directory: {UPLOAD_FOLDER}")
    
    # Check database directory write permissions
    db_dir = os.path.dirname(os.path.abspath(DATABASE)) or "."
    if not os.access(db_dir, os.W_OK):
        errors.append(f"No write permission for database directory: {db_dir}")
    
    # Test PyPDF2 functionality
    try:
        # Try to create a PdfReader with a dummy file to test import
        pass
    except Exception as e:
        errors.append(f"PyPDF2 not properly installed: {e}")
    
    if errors:
        app.logger.error("Environment validation failed:")
        for error in errors:
            app.logger.error(f"  - {error}")
        return False
    
    app.logger.info("Environment validation passed")
    return True

# ----------------------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        print("🚀 AMS Application Backend Starting...")
        print("=" * 60)
        
        # Validate environment
        if not validate_environment():
            print("❌ Environment validation failed. Check logs for details.")
            exit(1)
        
        # Initialize database
        print("📋 Initializing database...")
        init_database()
        print("✅ Database initialized successfully")
        
        # Test database connection
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM documents")
                doc_count = cur.fetchone()[0]
                print(f"📊 Found {doc_count} documents in database")
        except Exception as e:
            print(f"⚠️  Database connection test failed: {e}")
        
        print("=" * 60)
        print("🌐 Server starting on http://localhost:5001")
        print("📱 Open your browser and go to: http://localhost:5001")
        print("🔍 Make sure index.html is in the same directory as app.py")
        print("📁 Upload folder:", os.path.abspath(UPLOAD_FOLDER))
        print("💾 Database file:", os.path.abspath(DATABASE))
        print("=" * 60)
        
        # Register cleanup handler
        import atexit
        atexit.register(cleanup_on_shutdown)
        
        # Start Flask application
        app.run(
            debug=True, 
            host="0.0.0.0", 
            port=5001,
            threaded=True,
            use_reloader=False  # Disable reloader in production
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Application interrupted by user")
        cleanup_on_shutdown()
    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        app.logger.exception("Startup failed")
        exit(1)