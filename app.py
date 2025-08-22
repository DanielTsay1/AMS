from flask import Flask, request, jsonify, send_from_directory, render_template_string
import json
from flask_cors import CORS
import os
import sqlite3
import PyPDF2
import uuid
from datetime import datetime
import threading
import re
from werkzeug.utils import secure_filename
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
DATABASE = 'documents.db'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Cloud Storage Configuration (optional)
USE_CLOUD_STORAGE = False  # Set to True to enable cloud storage
CLOUD_STORAGE_TYPE = 's3'  # 's3', 'gcs', 'azure'
CLOUD_BUCKET_NAME = 'your-bucket-name'
CLOUD_REGION = 'us-east-1'

# Backup Configuration
ENABLE_BACKUPS = True
BACKUP_FOLDER = 'backups'
BACKUP_RETENTION_DAYS = 30  # Keep backups for 30 days
AUTO_BACKUP_ON_UPLOAD = True  # Create backup automatically when files are uploaded

# Ensure upload directory exists
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

# Ensure backup directory exists
if ENABLE_BACKUPS:
    Path(BACKUP_FOLDER).mkdir(exist_ok=True)

def get_db():
    """Establishes a database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def load_backup_config():
    """Load backup configuration from file."""
    global BACKUP_FOLDER
    config_file = os.path.join(os.path.dirname(__file__), 'backup_config.json')
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
                if 'backup_folder' in config_data:
                    BACKUP_FOLDER = config_data['backup_folder']
                    print(f"Loaded backup path from config: {BACKUP_FOLDER}")
        except Exception as e:
            print(f"Error loading backup config: {e}")
            print("Using default backup path")

def init_database():
    """Initialize the SQLite database."""
    conn = get_db()
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
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_cloud(file_path, file_id, original_filename):
    """Upload file to cloud storage (placeholder for cloud integration)."""
    if not USE_CLOUD_STORAGE:
        return True, "Local storage only"
    
    try:
        # This is a placeholder - you would implement actual cloud upload here
        # For AWS S3, you'd use boto3
        # For Google Cloud Storage, you'd use google-cloud-storage
        # For Azure, you'd use azure-storage-blob
        
        print(f"Would upload {file_path} to cloud storage")
        return True, "Cloud upload successful"
    except Exception as e:
        return False, str(e)

def get_file_from_storage(file_id, original_filename):
    """Get file from storage (local or cloud)."""
    if USE_CLOUD_STORAGE:
        # Return cloud storage URL or download from cloud
        return f"https://{CLOUD_BUCKET_NAME}.s3.{CLOUD_REGION}.amazonaws.com/{file_id}_{original_filename}"
    else:
        # Return local file path
        return os.path.join(UPLOAD_FOLDER, f"{file_id}_{original_filename}")

def create_backup(file_path, file_id, original_filename):
    """Create a backup copy of the uploaded file."""
    if not ENABLE_BACKUPS:
        return True, "Backups disabled"
    
    try:
        import shutil
        from datetime import datetime
        
        # Create timestamped backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{timestamp}_{file_id}_{original_filename}"
        backup_path = os.path.join(BACKUP_FOLDER, backup_filename)
        
        # Copy file to backup location
        shutil.copy2(file_path, backup_path)
        
        print(f"Backup created: {backup_path}")
        return True, backup_path
    except Exception as e:
        print(f"Backup failed: {str(e)}")
        return False, str(e)

def cleanup_old_backups():
    """Remove old backup files based on retention policy."""
    if not ENABLE_BACKUPS:
        return
    
    try:
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        
        for filename in os.listdir(BACKUP_FOLDER):
            file_path = os.path.join(BACKUP_FOLDER, filename)
            
            # Check if file is older than retention period
            file_time = datetime.fromtimestamp(os.path.getctime(file_path))
            if file_time < cutoff_date:
                os.remove(file_path)
                print(f"Removed old backup: {filename}")
    except Exception as e:
        print(f"Backup cleanup failed: {str(e)}")

def backup_database():
    """Create a backup of the SQLite database."""
    if not ENABLE_BACKUPS:
        return True, "Backups disabled"
    
    try:
        import shutil
        from datetime import datetime
        
        # Create timestamped database backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_backup_filename = f"documents_backup_{timestamp}.db"
        db_backup_path = os.path.join(BACKUP_FOLDER, db_backup_filename)
        
        # Copy database to backup location
        shutil.copy2(DATABASE, db_backup_path)
        
        print(f"Database backup created: {db_backup_path}")
        return True, db_backup_path
    except Exception as e:
        print(f"Database backup failed: {str(e)}")
        return False, str(e)

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
    """Determines document type based on filename and content."""
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

def process_pdf_background(file_id, file_path, original_filename):
    """Background task to process PDF content."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        print(f"Processing {original_filename} (ID: {file_id})")
        
        content, page_count = extract_text_from_pdf(file_path)
        
        if not content:
            raise Exception("No text content could be extracted from the PDF")
            
        doc_type = determine_document_type(original_filename, content)
        
        print(f"Extracted {len(content)} pages from {original_filename}")
        
        # Store content in FTS5 table
        for page_data in content:
            cursor.execute(
                "INSERT INTO document_content_fts (document_id, page_number, content) VALUES (?, ?, ?)",
                (file_id, page_data['page'], page_data['text'])
            )
        
        # Update document status
        cursor.execute(
            "UPDATE documents SET status = ?, page_count = ?, document_type = ? WHERE id = ?",
            ('indexed', page_count, doc_type, file_id)
        )
        
        conn.commit()
        print(f"Successfully processed: {original_filename}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error processing {original_filename}: {error_msg}")
        
        cursor.execute(
            "UPDATE documents SET status = ?, error_message = ? WHERE id = ?", 
            ('error', error_msg, file_id)
        )
        conn.commit()
    finally:
        conn.close()

@app.route('/')
def home():
    """Main page with HTML interface."""
    html_template = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PDF Search & Storage</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                background: #f3f2ef;
                min-height: 100vh;
                color: #191919;
                line-height: 1.6;
            }
            
            .container {
                max-width: 1128px;
                margin: 0 auto;
                padding: 24px;
            }
            
            .header {
                text-align: center;
                margin-bottom: 48px;
                background: white;
                padding: 32px;
                border-radius: 8px;
                box-shadow: 0 0 0 1px rgba(0,0,0,0.08);
                margin-bottom: 32px;
            }
            
            .header h1 {
                font-size: 2.5rem;
                margin-bottom: 12px;
                color: #0a66c2;
                font-weight: 600;
                letter-spacing: -0.025em;
            }
            
            .header p {
                font-size: 1.125rem;
                color: #666;
                font-weight: 400;
            }
            
            .main-content {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 24px;
                margin-bottom: 32px;
            }
            
            .card {
                background: white;
                border-radius: 8px;
                padding: 24px;
                box-shadow: 0 0 0 1px rgba(0,0,0,0.08);
                transition: box-shadow 0.2s ease;
                border: 1px solid transparent;
            }
            
            .card:hover {
                box-shadow: 0 0 0 1px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.15);
            }
            
            .card h2 {
                color: #191919;
                margin-bottom: 20px;
                font-size: 1.25rem;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .upload-area {
                border: 2px dashed #d0d8dc;
                border-radius: 8px;
                padding: 32px;
                text-align: center;
                transition: all 0.2s ease;
                cursor: pointer;
                background: #fafafa;
            }
            
            .upload-area:hover, .upload-area.dragover {
                border-color: #0a66c2;
                background-color: #f0f8ff;
            }
            
            .upload-area.dragover {
                transform: scale(1.01);
            }
            
            .upload-icon {
                font-size: 2.5rem;
                color: #0a66c2;
                margin-bottom: 16px;
            }
            
            .upload-text {
                font-size: 1rem;
                margin-bottom: 8px;
                color: #191919;
                font-weight: 500;
            }
            
            .upload-subtext {
                color: #666;
                margin-bottom: 20px;
                font-size: 0.875rem;
            }
            
            .upload-btn {
                background: #0a66c2;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 24px;
                font-size: 0.875rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                min-width: 120px;
            }
            
            .upload-btn:hover {
                background: #004182;
                transform: translateY(-1px);
            }
            
            .search-container {
                margin-bottom: 20px;
            }
            
            .search-input {
                width: 100%;
                padding: 12px 16px;
                border: 1px solid #d0d8dc;
                border-radius: 4px;
                font-size: 0.875rem;
                transition: border-color 0.2s ease;
                background: white !important;
                color: #191919 !important;
                font-weight: 400;
            }
            
            .search-input:focus {
                outline: none;
                border-color: #0a66c2;
                box-shadow: 0 0 0 2px rgba(10, 102, 194, 0.1);
                background: white;
                color: #191919;
            }
            
            .search-input::placeholder {
                color: #666;
                opacity: 1;
            }
            
            /* Ensure all input fields have proper contrast */
            input[type="text"], input[type="email"], input[type="password"], input[type="search"], textarea, select {
                color: #191919 !important;
                background: white !important;
                font-weight: 400;
            }
            
            input[type="text"]::placeholder, input[type="email"]::placeholder, input[type="password"]::placeholder, input[type="search"]::placeholder, textarea::placeholder {
                color: #666 !important;
                opacity: 1;
            }
            
            /* Specific rule for search input to ensure visibility */
            #searchInput {
                color: #191919 !important;
                background: white !important;
                font-weight: 400 !important;
            }
            
            #searchInput::placeholder {
                color: #666 !important;
                opacity: 1 !important;
            }
            
            /* Additional browser compatibility */
            #searchInput::-webkit-input-placeholder {
                color: #666 !important;
                opacity: 1 !important;
            }
            
            #searchInput:-moz-placeholder {
                color: #666 !important;
                opacity: 1 !important;
            }
            
            #searchInput::-moz-placeholder {
                color: #666 !important;
                opacity: 1 !important;
            }
            
            #searchInput:-ms-input-placeholder {
                color: #666 !important;
                opacity: 1 !important;
            }
            
            /* Document Library Styles */
            .library-controls {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                flex-wrap: wrap;
                gap: 15px;
            }
            
            .library-filters {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
            }
            
            .library-search {
                flex-shrink: 0;
            }
            
            .library-controls-right {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .document-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            
            .document-card {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 20px;
                transition: all 0.2s ease;
                cursor: pointer;
                position: relative;
            }
            
            .document-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                border-color: #0a66c2;
            }
            
            .document-card.processing {
                border-color: #ffc107;
                background: #fffbf0;
            }
            
            .document-card.error {
                border-color: #dc3545;
                background: #fff5f5;
            }
            
            .document-card.indexed {
                border-color: #28a745;
                background: #f8fff9;
            }
            
            .document-header {
                display: flex;
                align-items: flex-start;
                margin-bottom: 15px;
            }
            
            .document-icon {
                font-size: 2rem;
                margin-right: 15px;
                color: #0a66c2;
            }
            
            .document-info {
                flex: 1;
                min-width: 0;
            }
            
            .document-title {
                font-weight: 600;
                color: #191919;
                margin-bottom: 5px;
                font-size: 1rem;
                line-height: 1.3;
                word-wrap: break-word;
            }
            
            .document-meta {
                color: #666;
                font-size: 0.8rem;
                line-height: 1.4;
            }
            
            .document-status {
                position: absolute;
                top: 15px;
                right: 15px;
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 0.7rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.025em;
            }
            
            .status-processing {
                background: #fff3cd;
                color: #856404;
            }
            
            .status-indexed {
                background: #d1e7dd;
                color: #0f5132;
            }
            
            .status-error {
                background: #f8d7da;
                color: #721c24;
            }
            
            .document-actions {
                display: flex;
                gap: 10px;
                margin-top: 15px;
                flex-wrap: wrap;
            }
            
            .action-btn {
                background: #f8f9fa;
                border: 1px solid #d0d8dc;
                color: #666;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 0.75rem;
                cursor: pointer;
                transition: all 0.2s ease;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                gap: 5px;
            }
            
            .action-btn:hover {
                background: #0a66c2;
                color: white;
                border-color: #0a66c2;
            }
            
            .action-btn.view {
                background: #e3f2fd;
                color: #0d47a1;
                border-color: #2196f3;
            }
            
            .action-btn.download {
                background: #e8f5e8;
                color: #1e7e34;
                border-color: #28a745;
            }
            
            .document-preview {
                margin-top: 15px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 6px;
                border-left: 3px solid #0a66c2;
                font-size: 0.8rem;
                color: #666;
                line-height: 1.5;
                max-height: 100px;
                overflow: hidden;
                position: relative;
            }
            
            .document-preview::after {
                content: '';
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 20px;
                background: linear-gradient(transparent, #f8f9fa);
            }
            
            .no-documents {
                text-align: center;
                padding: 40px;
                color: #666;
            }
            
            .no-documents h3 {
                margin-bottom: 10px;
                color: #191919;
            }
            
            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }
            
            .loading-spinner {
                border: 3px solid #f3f3f3;
                border-top: 3px solid #0a66c2;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .search-btn {
                background: #0a66c2;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 0.875rem;
                font-weight: 600;
                cursor: pointer;
                margin-top: 12px;
                width: 100%;
                transition: all 0.2s ease;
            }
            
            .search-btn:hover {
                background: #004182;
            }
            
            .file-list {
                margin-top: 20px;
            }
            
            .file-item {
                display: flex;
                align-items: center;
                padding: 16px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                margin-bottom: 12px;
                background: #fafafa;
                transition: all 0.2s ease;
            }
            
            .file-item:hover {
                background: #f0f0f0;
                border-color: #d0d8dc;
            }
            
            .file-icon {
                font-size: 1.25rem;
                margin-right: 16px;
                color: #0a66c2;
            }
            
            .file-info {
                flex: 1;
            }
            
            .file-name {
                font-weight: 600;
                margin-bottom: 4px;
                color: #191919;
                font-size: 0.875rem;
            }
            
            .file-meta {
                color: #666;
                font-size: 0.75rem;
            }
            
            .file-status {
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.025em;
            }
            
            .status-processing {
                background: #fff3cd;
                color: #856404;
            }
            
            .status-complete {
                background: #d4edda;
                color: #155724;
            }
            
            .status-error {
                background: #f8d7da;
                color: #721c24;
            }
            
            .results-section {
                margin-top: 20px;
            }
            
            .result-item {
                background: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 20px;
                margin-bottom: 16px;
                transition: all 0.2s ease;
            }
            
            .result-item:hover {
                background: #f0f0f0;
                border-color: #d0d8dc;
            }
            
            .result-title {
                font-weight: 600;
                color: #0a66c2;
                margin-bottom: 8px;
                cursor: pointer;
                font-size: 1rem;
            }
            
            .result-title:hover {
                text-decoration: underline;
            }
            
            .result-meta {
                color: #666;
                font-size: 0.75rem;
                margin-bottom: 12px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .result-snippet {
                background: white;
                padding: 16px;
                border-radius: 6px;
                border-left: 3px solid #0a66c2;
                line-height: 1.6;
                font-size: 0.875rem;
                color: #191919;
            }
            
            .result-actions {
                margin-top: 15px;
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }
            
            .action-btn {
                background: #667eea;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 20px;
                cursor: pointer;
                font-size: 0.9rem;
                transition: all 0.3s ease;
                text-decoration: none;
                display: inline-block;
            }
            
            .action-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            }
            
            .action-btn[onclick*="downloadPDF"] {
                background: #28a745;
            }
            
            .action-btn[onclick*="openPDFInNewTab"] {
                background: #ffc107;
                color: black;
            }
            
            .highlight {
                background: #fff3cd;
                padding: 2px 4px;
                border-radius: 3px;
            }
            
            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }
            
            .loading-spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 16px;
                margin-top: 20px;
            }
            
            .stat-item {
                background: #fafafa;
                padding: 20px;
                border-radius: 6px;
                text-align: center;
                border: 1px solid #e0e0e0;
                transition: all 0.2s ease;
            }
            
            .stat-item:hover {
                background: #f0f0f0;
                border-color: #d0d8dc;
            }
            
            .stat-number {
                font-size: 1.75rem;
                font-weight: 600;
                color: #0a66c2;
                display: block;
                margin-bottom: 4px;
            }
            
            .stat-label {
                color: #666;
                font-size: 0.875rem;
                font-weight: 500;
            }
            
            .filters {
                display: flex;
                gap: 8px;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }
            
            .filter-btn {
                background: #fafafa;
                border: 1px solid #d0d8dc;
                padding: 6px 16px;
                border-radius: 16px;
                cursor: pointer;
                transition: all 0.2s ease;
                color: #666;
                font-size: 0.75rem;
                font-weight: 500;
            }
            
            .filter-btn.active, .filter-btn:hover {
                background: #0a66c2;
                color: white;
                border-color: #0a66c2;
            }
            
            .search-tips {
                margin: 16px 0;
                padding: 12px 16px;
                background: #e3f2fd;
                border-radius: 6px;
                font-size: 0.875rem;
                color: #0d47a1;
                border-left: 3px solid #2196f3;
            }
            
            .backup-section {
                margin-top: 32px;
                text-align: center;
                padding: 24px;
                background: #f8f9fa;
                border-radius: 6px;
                border: 1px solid #e0e0e0;
            }
            
            .backup-section h3 {
                color: #191919;
                margin-bottom: 8px;
                font-size: 1.125rem;
                font-weight: 600;
            }
            
            .backup-section p {
                color: #666;
                margin-bottom: 20px;
                font-size: 0.875rem;
            }
            
            .backup-btn {
                background: #28a745;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 0.875rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                min-width: 140px;
            }
            
            .backup-btn:hover {
                background: #1e7e34;
            }
            
            .backup-btn:disabled {
                background: #6c757d;
                cursor: not-allowed;
            }
            
            .hidden {
                display: none;
            }
            
            @media (max-width: 768px) {
                .main-content {
                    grid-template-columns: 1fr;
                }
                
                .header h1 {
                    font-size: 2rem;
                }
                
                .container {
                    padding: 16px;
                }
                
                .card {
                    padding: 20px;
                }
            }
            
            /* Modal Styles */
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
                backdrop-filter: blur(5px);
            }
            
            .modal-content {
                background-color: white;
                margin: 5% auto;
                padding: 0;
                border-radius: 8px;
                width: 90%;
                max-width: 500px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                animation: modalSlideIn 0.3s ease-out;
            }
            
            @keyframes modalSlideIn {
                from {
                    opacity: 0;
                    transform: translateY(-50px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .modal-header {
                padding: 20px 20px 15px;
                border-bottom: 1px solid #e0e0e0;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            
            .modal-header h3 {
                margin: 0;
                color: #dc3545;
                font-size: 1.2rem;
            }
            
            .close {
                color: #aaa;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
                line-height: 1;
            }
            
            .close:hover {
                color: #000;
            }
            
            .modal-body {
                padding: 20px;
                color: #333;
                line-height: 1.6;
            }
            
            .modal-body p {
                margin-bottom: 15px;
            }
            
            .modal-body ul {
                margin: 15px 0;
                padding-left: 20px;
            }
            
            .modal-body li {
                margin-bottom: 8px;
                color: #666;
            }
            
            .modal-footer {
                padding: 15px 20px 20px;
                border-top: 1px solid #e0e0e0;
                display: flex;
                justify-content: flex-end;
                gap: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1> AMS PDF Search & Storage</h1>
                <p>Upload PDFs and search through their content instantly</p>
            </div>
            
            <div class="main-content">
                <!-- Upload Section -->
                <div class="card">
                    <h2>📤 Upload PDFs</h2>
                    <div class="upload-area" id="uploadArea">
                        <div class="upload-icon">📄</div>
                        <div class="upload-text">Drop PDF files here or click to browse</div>
                        <div class="upload-subtext">Support for PDF documents up to 50MB each</div>
                        <button class="upload-btn" onclick="document.getElementById('fileInput').click()">Choose Files</button>
                        <input type="file" id="fileInput" multiple accept=".pdf" style="display: none;">
                    </div>
                    
                    <div class="file-list" id="fileList"></div>
                </div>
                
                            <!-- Search Section -->
            <div class="card">
                <h2>🔍 Search Documents</h2>
                <div class="search-container">
                    <input type="text" class="search-input" placeholder="What would you like to know? (partial words work too!)" id="searchInput">
                    <div style="display: flex; gap: 10px; margin-top: 10px; align-items: center;">
                        <button class="search-btn" onclick="performSearch()" style="flex: 1;">Search</button>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <label style="font-size: 0.8rem; color: #666;">Search mode:</label>
                            <select id="searchMode" style="padding: 4px 8px; border: 1px solid #d0d8dc; border-radius: 4px; font-size: 0.8rem; background: white; color: #191919;">
                                <option value="and">All Words (AND)</option>
                                <option value="or">Any Words (OR)</option>
                            </select>
                        </div>
                    </div>
                </div>
                
                <div class="search-tips">
                    💡 <strong>Search Tips:</strong> 
                    <ul style="margin: 8px 0 0 20px; padding: 0;">
                        <li>Use partial words like "calc" to find "calculus", "calculate", etc.</li>
                        <li>Search for multiple words: "health computer workers" finds documents containing all three terms</li>
                        <li>Words don't need to be together - the system finds documents with all your search terms</li>
                        <li>Common words like "and", "or", "the" are automatically filtered out for better results</li>
                    </ul>
                </div>
                
                <div class="filters">
                    <button class="filter-btn active" data-filter="all">All Documents</button>
                    <button class="filter-btn" data-filter="policy">Policies</button>
                    <button class="filter-btn" data-filter="manual">Manuals</button>
                    <button class="filter-btn" data-filter="faq">FAQs</button>
                    <button class="filter-btn" data-filter="guide">Guides</button>
                </div>
                
                <div class="results-section" id="resultsSection">
                    <div class="loading">
                        <h3>🔍 Ready to search</h3>
                        <p>Upload PDF documents first, then search through them for relevant information.</p>
                    </div>
                </div>
                
                <!-- Search Suggestions -->
                <div id="searchSuggestions"></div>
            </div>
            </div>
            
            <!-- Document Library Section -->
            <div class="card">
                <h2>📚 Document Library</h2>
                <div class="library-controls">
                    <div class="library-filters">
                        <button class="filter-btn active" data-library-filter="all">All Documents</button>
                        <button class="filter-btn" data-library-filter="policy">Policies</button>
                        <button class="filter-btn" data-library-filter="manual">Manuals</button>
                        <button class="filter-btn" data-library-filter="faq">FAQs</button>
                        <button class="filter-btn" data-library-filter="guide">Guides</button>
                    </div>
                    <div class="library-controls-right">
                        <div class="library-search">
                            <input type="text" id="librarySearch" placeholder="Search documents by name..." class="search-input" style="max-width: 300px;">
                        </div>
                        <button class="action-btn" onclick="refreshDocumentLibrary()" style="margin-left: 10px;">
                            🔄 Refresh
                        </button>
                        <button class="action-btn" onclick="showClearAllConfirmation()" style="margin-left: 10px; background: #dc3545; color: white; border-color: #dc3545;">
                            🗑️ Clear All
                        </button>
                    </div>
                </div>
                
                <div class="document-grid" id="documentGrid">
                    <div class="loading">
                        <div class="loading-spinner"></div>
                        <h3>Loading documents...</h3>
                    </div>
                </div>
            </div>
            
            <!-- Stats Section -->
            <div class="card">
                <h2>📊 System Statistics</h2>
                <div class="stats">
                    <div class="stat-item">
                        <span class="stat-number" id="totalDocsStat">0</span>
                        <div class="stat-label">Total Documents</div>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number" id="pagesIndexedStat">0</span>
                        <div class="stat-label">Pages Indexed</div>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number" id="lastUpdatedStat">Never</span>
                        <div class="stat-label">Last Updated</div>
                    </div>
                    <div class="stat-item">
                        <span class="stat-number" id="accuracyStat">--</span>
                        <div class="stat-label">Search Accuracy</div>
                    </div>
                </div>
                
                <!-- Backup Section -->
                <div class="backup-section">
                    <h3>💾 Data Protection</h3>
                    <p>Create backups of your documents and database</p>
                    
                    <div class="backup-controls" style="margin: 20px 0; padding: 15px; background: #f8f9ff; border-radius: 8px; text-align: left;">
                        <h4 style="margin-top: 0; color: #333;">📁 Change Backup Location</h4>
                        <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 15px;">
                            <input type="text" id="newBackupPath" placeholder="Enter new backup path (e.g., /Users/username/Documents/MyBackups)" style="flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 0.9rem; color: #191919; background: white;">
                            <button onclick="changeBackupPath()" style="background: #17a2b8; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 0.9rem;">Change Path</button>
                        </div>
                        <div style="font-size: 0.8rem; color: #666; line-height: 1.4;">
                            💡 <strong>Examples:</strong><br>
                            • <code>/Users/danieltsay/Documents/PDF_Backups</code><br>
                            • <code>/Volumes/ExternalDrive/Backups</code><br>
                            • <code>~/Desktop/MyBackups</code>
                        </div>
                    </div>
                    
                    <button class="backup-btn" onclick="createBackup()">
                        🔒 Create Backup
                    </button>
                    <div id="backupStatus" style="margin-top: 15px; font-size: 0.9rem;"></div>
                </div>
            </div>
        </div>

        <script>
            let currentFilter = 'all';
            let searchResults = [];

            // File upload functionality
            const uploadArea = document.getElementById('uploadArea');
            const fileInput = document.getElementById('fileInput');

            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });

            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });

            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                handleFiles(files);
            });

            fileInput.addEventListener('change', (e) => {
                handleFiles(e.target.files);
            });

            async function handleFiles(files) {
                Array.from(files).forEach(async (file) => {
                    if (file.type === 'application/pdf') {
                        console.log('Uploading file:', file.name);
                        
                        const fileItem = addFileToList(file);
                        
                        try {
                            const formData = new FormData();
                            formData.append('file', file);
                            
                            const response = await fetch('/api/upload', {
                                method: 'POST',
                                body: formData
                            });
                            
                            if (response.ok) {
                                const result = await response.json();
                                console.log('Upload successful:', result);
                                
                                const status = fileItem.querySelector('.file-status');
                                status.textContent = 'Processing...';
                                status.className = 'file-status status-processing';
                                
                                pollUploadStatus(result.id, fileItem);
                                loadStats();
                                loadDocumentLibrary(); // Refresh document library
                            } else {
                                const error = await response.text();
                                console.error('Upload failed:', error);
                                updateFileStatus(fileItem, 'Error', 'status-error');
                            }
                        } catch (error) {
                            console.error('Upload error:', error);
                            updateFileStatus(fileItem, 'Upload Failed', 'status-error');
                        }
                    } else {
                        alert('Only PDF files are supported');
                    }
                });
            }

            function addFileToList(file) {
                const fileList = document.getElementById('fileList');
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <div class="file-icon">📄</div>
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-meta">${(file.size / 1024 / 1024).toFixed(1)} MB • Just uploaded</div>
                    </div>
                    <div class="file-status status-processing">Processing</div>
                `;
                fileList.appendChild(fileItem);
                return fileItem;
            }

            function updateFileStatus(fileItem, text, className) {
                const status = fileItem.querySelector('.file-status');
                status.textContent = text;
                status.className = `file-status ${className}`;
            }

            async function pollUploadStatus(fileId, fileItem) {
                const maxAttempts = 30;
                let attempts = 0;
                
                const poll = async () => {
                    try {
                        const response = await fetch('/api/documents');
                        const documents = await response.json();
                        const doc = documents.find(d => d.id === fileId);
                        
                        if (doc) {
                            if (doc.status === 'indexed') {
                                updateFileStatus(fileItem, 'Indexed', 'status-complete');
                                loadStats();
                                loadDocumentLibrary(); // Refresh document library
                                return;
                            } else if (doc.status === 'error') {
                                updateFileStatus(fileItem, 'Error', 'status-error');
                                return;
                            }
                        }
                        
                        attempts++;
                        if (attempts < maxAttempts) {
                            setTimeout(poll, 10000);
                        } else {
                            updateFileStatus(fileItem, 'Timeout', 'status-error');
                        }
                    } catch (error) {
                        console.error('Status check failed:', error);
                        attempts++;
                        if (attempts < maxAttempts) {
                            setTimeout(poll, 10000);
                        } else {
                            updateFileStatus(fileItem, 'Status Check Failed', 'status-error');
                        }
                    }
                };
                
                poll();
            }

            // Search functionality
            document.getElementById('searchInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    performSearch();
                }
            });

            async function performSearch() {
                const query = document.getElementById('searchInput').value.trim();
                if (!query) return;

                const searchMode = document.getElementById('searchMode').value;
                showLoading();
                
                try {
                    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&mode=${searchMode}`);
                    if (response.ok) {
                        const data = await response.json();
                        searchResults = data.results || [];
                        displayResults(searchResults);
                        
                        // Show search suggestions for partial matches
                        if (query.length >= 2 && searchResults.length > 0) {
                            showSearchSuggestions(query, searchResults);
                        }
                    } else {
                        console.error('Search failed:', response.statusText);
                        showError('Search failed. Please try again.');
                    }
                } catch (error) {
                    console.error('Search error:', error);
                    showError('Search failed. Please try again.');
                }
            }
            
            function showSearchSuggestions(query, results) {
                const suggestionsDiv = document.getElementById('searchSuggestions');
                if (!suggestionsDiv) return;
                
                // Extract unique words from results for suggestions
                const words = new Set();
                const multiWordSuggestions = new Set();
                results.forEach(result => {
                    const content = result.snippet.toLowerCase();
                    const queryLower = query.toLowerCase();
                    
                    // Find words that contain the query
                    const wordMatches = content.match(/\b\w+\b/g) || [];
                    wordMatches.forEach(word => {
                        if (word.includes(queryLower) && word.length > query.length) {
                            words.add(word);
                        }
                    });
                    
                    // Create multi-word suggestions by combining query with other relevant words
                    const queryTerms = queryLower.split(' ').filter(term => term.length >= 2);
                    if (queryTerms.length > 0) {
                        wordMatches.forEach(word => {
                            if (word.length >= 3 && !queryTerms.includes(word)) {
                                // Create suggestions like "health computer" + "workers" = "health computer workers"
                                const newSuggestion = [...queryTerms, word].join(' ');
                                if (newSuggestion.length < 50) { // Limit suggestion length
                                    multiWordSuggestions.add(newSuggestion);
                                }
                            }
                        });
                    }
                });
                
                let suggestionsHTML = '';
                
                // Add single word suggestions
                if (words.size > 0) {
                    const singleWordSuggestions = Array.from(words).slice(0, 3);
                    suggestionsHTML += `
                        <div style="margin-bottom: 10px;">
                            <strong>📝 Related words:</strong> 
                            ${singleWordSuggestions.map(word => `<span onclick="setSearch('${word}')" style="cursor: pointer; color: #17a2b8; text-decoration: underline; margin: 0 5px;">${word}</span>`).join('')}
                        </div>
                    `;
                }
                
                // Add multi-word suggestions
                if (multiWordSuggestions.size > 0) {
                    const multiWordSuggestionsArray = Array.from(multiWordSuggestions).slice(0, 3);
                    suggestionsHTML += `
                        <div>
                            <strong>🔍 Multi-word searches:</strong> 
                            ${multiWordSuggestionsArray.map(suggestion => `<span onclick="setSearch('${suggestion}')" style="cursor: pointer; color: #28a745; text-decoration: underline; margin: 0 5px;">${suggestion}</span>`).join('')}
                        </div>
                    `;
                }
                
                if (suggestionsHTML) {
                    suggestionsDiv.innerHTML = `
                        <div style="margin-top: 15px; padding: 15px; background: #e8f4fd; border-radius: 8px; border-left: 4px solid #17a2b8;">
                            💡 <strong>Search suggestions:</strong><br>
                            ${suggestionsHTML}
                        </div>
                    `;
                } else {
                    suggestionsDiv.innerHTML = '';
                }
            }
            
            function setSearch(query) {
                document.getElementById('searchInput').value = query;
                performSearch();
            }

            function showLoading() {
                document.getElementById('resultsSection').innerHTML = `
                    <div class="loading">
                        <div class="loading-spinner"></div>
                        <h3>Searching documents...</h3>
                        <p>Analyzing your query and finding relevant information</p>
                    </div>
                `;
            }

            function showError(message) {
                document.getElementById('resultsSection').innerHTML = `
                    <div class="loading">
                        <h3>❌ Error</h3>
                        <p>${message}</p>
                    </div>
                `;
            }

            function displayResults(results) {
                const filteredResults = currentFilter === 'all' 
                    ? results 
                    : results.filter(r => r.type === currentFilter);

                if (filteredResults.length === 0) {
                    const searchMode = document.getElementById('searchMode').value;
                    const modeText = searchMode === 'and' ? 'All Words (AND)' : 'Any Words (OR)';
                    
                    let helpText = 'Try adjusting your search terms or filters';
                    if (searchMode === 'and') {
                        helpText = 'No documents contain ALL your search terms. Try using fewer terms or switch to "Any Words (OR)" mode for broader results.';
                    }
                    
                    document.getElementById('resultsSection').innerHTML = `
                        <div class="loading">
                            <h3>No results found</h3>
                            <p>${helpText}</p>
                            <div style="margin-top: 15px; padding: 10px; background: #fff3cd; border-radius: 6px; border-left: 4px solid #ffc107; font-size: 0.9rem; color: #856404;">
                                💡 <strong>Search Mode:</strong> ${modeText} • <strong>Tip:</strong> AND mode requires all terms to be present, OR mode finds documents with any term
                            </div>
                        </div>
                    `;
                    return;
                }

                const searchMode = document.getElementById('searchMode').value;
                const modeText = searchMode === 'and' ? 'All Words (AND)' : 'Any Words (OR)';
                
                const searchInput = document.getElementById('searchInput').value;
                const resultsHTML = `
                    <div style="margin-bottom: 20px; padding: 12px; background: #e8f4fd; border-radius: 6px; border-left: 4px solid #17a2b8; font-size: 0.9rem; color: #0d47a1;">
                        🔍 <strong>Search Mode:</strong> ${modeText} • <strong>Results:</strong> ${filteredResults.length} documents found<br>
                        📝 <strong>Searching for:</strong> "${searchInput}" (filtered to meaningful terms)
                    </div>
                    ${filteredResults.map(result => createResultHTML(result)).join('')}
                `;
                
                document.getElementById('resultsSection').innerHTML = resultsHTML;
            }

            function createResultHTML(result) {
                return `
                    <div class="result-item">
                        <div class="result-title">
                            ${result.title}
                        </div>
                        <div class="result-meta">
                            📄 ${result.document} • Page ${result.page} • ${result.confidence}% match
                        </div>
                        <div class="result-snippet">${result.snippet}</div>
                        <div class="result-actions" style="margin-top: 15px; display: flex; gap: 10px;">
                            <button class="action-btn" onclick="viewPDF('${result.id}', '${result.filename}', ${result.page})" style="background: #667eea; color: white; border: none; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-size: 0.9rem;">
                                👁️ View PDF
                            </button>
                            <button class="action-btn" onclick="downloadPDF('${result.id}', '${result.filename}')" style="background: #28a745; color: white; border: none; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-size: 0.9rem;">
                                📥 Download
                            </button>
                            <button class="action-btn" onclick="openPDFInNewTab('${result.id}', '${result.filename}')" style="background: #ffc107; color: black; border: none; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-size: 0.9rem;">
                                🔗 Open in New Tab
                            </button>
                        </div>
                    </div>
                `;
            }

            function viewPDF(docId, filename, page) {
                // Open PDF in a modal or new window
                const pdfUrl = `/api/document/${docId}/view`;
                const modal = document.createElement('div');
                modal.style.cssText = `
                    position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
                    background: rgba(0,0,0,0.8); z-index: 1000; display: flex; 
                    align-items: center; justify-content: center;
                `;
                
                modal.innerHTML = `
                    <div style="background: white; border-radius: 10px; padding: 20px; max-width: 90%; max-height: 90%; overflow: hidden;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                            <h3 style="margin: 0;">${filename} - Page ${page}</h3>
                            <button onclick="this.parentElement.parentElement.parentElement.remove()" style="background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer;">✕ Close</button>
                        </div>
                        <iframe src="${pdfUrl}" style="width: 800px; height: 600px; border: none; border-radius: 5px;"></iframe>
                    </div>
                `;
                
                document.body.appendChild(modal);
                
                // Close modal when clicking outside
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) modal.remove();
                });
            }
            
            function downloadPDF(docId, filename) {
                const downloadUrl = `/api/document/${docId}/download`;
                const link = document.createElement('a');
                link.href = downloadUrl;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
            
            function openPDFInNewTab(docId, filename) {
                const pdfUrl = `/api/document/${docId}/view`;
                window.open(pdfUrl, '_blank');
            }

            // Filter functionality
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    currentFilter = this.dataset.filter;
                    if (searchResults.length > 0) {
                        displayResults(searchResults);
                    }
                });
            });

            // Load initial stats, documents, and backup info
            loadStats();
            loadDocumentLibrary();
            loadBackupInfo();

            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    if (response.ok) {
                        const stats = await response.json();
                        document.getElementById('totalDocsStat').textContent = stats.totalDocuments || 0;
                        document.getElementById('pagesIndexedStat').textContent = stats.totalPages || 0;
                        document.getElementById('lastUpdatedStat').textContent = stats.lastUpdated || 'Never';
                        document.getElementById('accuracyStat').textContent = stats.accuracy ? `${stats.accuracy}%` : '--';
                    }
                } catch (error) {
                    console.error('Failed to load stats:', error);
                }
            }
            
            async function loadDocumentLibrary() {
                try {
                    const response = await fetch('/api/documents');
                    if (response.ok) {
                        const documents = await response.json();
                        displayDocuments(documents);
                    }
                } catch (error) {
                    console.error('Failed to load documents:', error);
                    document.getElementById('documentGrid').innerHTML = `
                        <div class="no-documents">
                            <h3>❌ Error Loading Documents</h3>
                            <p>Failed to load document library. Please refresh the page.</p>
                        </div>
                    `;
                }
            }
            
            function displayDocuments(documents) {
                const documentGrid = document.getElementById('documentGrid');
                
                if (documents.length === 0) {
                    documentGrid.innerHTML = `
                        <div class="no-documents">
                            <h3>📚 No Documents Yet</h3>
                            <p>Upload your first PDF to get started!</p>
                        </div>
                    `;
                    return;
                }
                
                const documentsHTML = documents.map(doc => createDocumentCard(doc)).join('');
                documentGrid.innerHTML = documentsHTML;
                
                // Add event listeners to action buttons
                addDocumentEventListeners();
            }
            
            function createDocumentCard(doc) {
                const statusClass = doc.status === 'indexed' ? 'indexed' : 
                                  doc.status === 'error' ? 'error' : 'processing';
                
                const statusText = doc.status === 'indexed' ? 'Indexed' :
                                 doc.status === 'error' ? 'Error' : 'Processing';
                
                const statusColor = doc.status === 'indexed' ? 'status-indexed' :
                                  doc.status === 'error' ? 'status-error' : 'status-processing';
                
                const fileSize = doc.size ? `${(doc.size / 1024 / 1024).toFixed(1)} MB` : 'Unknown size';
                const uploadDate = doc.upload_date ? new Date(doc.upload_date).toLocaleDateString() : 'Never';
                const pageCount = doc.page_count || 'Unknown';
                
                return `
                    <div class="document-card ${statusClass}" data-doc-id="${doc.id}">
                        <div class="document-status ${statusColor}">${statusText}</div>
                        
                        <div class="document-header">
                            <div class="document-icon">📄</div>
                            <div class="document-info">
                                <div class="document-title">${doc.name}</div>
                                <div class="document-meta">
                                    📏 ${fileSize} • 📅 ${uploadDate}<br>
                                    📖 ${pageCount} pages • 🏷️ ${doc.type || 'Document'}
                                </div>
                            </div>
                        </div>
                        
                        ${doc.status === 'indexed' ? `
                            <div class="document-preview">
                                <strong>Ready for search</strong><br>
                                This document has been processed and indexed. You can now search through its content.
                            </div>
                        ` : doc.status === 'error' ? `
                            <div class="document-preview">
                                <strong>Processing failed</strong><br>
                                ${doc.error || 'An error occurred during processing. Please try uploading again.'}
                            </div>
                        ` : `
                            <div class="document-preview">
                                <strong>Processing...</strong><br>
                                This document is being analyzed and indexed. Please wait a moment.
                            </div>
                        `}
                        
                        <div class="document-actions">
                            <button class="action-btn view" onclick="viewDocument('${doc.id}')">
                                👁️ View
                            </button>
                            <button class="action-btn download" onclick="downloadDocument('${doc.id}')">
                                ⬇️ Download
                            </button>
                            ${doc.status === 'indexed' ? `
                                <button class="action-btn" onclick="searchInDocument('${doc.name}')">
                                    🔍 Search
                                </button>
                            ` : ''}
                        </div>
                    </div>
                `;
            }
            
            function addDocumentEventListeners() {
                // Add click handlers for document cards
                document.querySelectorAll('.document-card').forEach(card => {
                    card.addEventListener('click', function(e) {
                        // Don't trigger if clicking on action buttons
                        if (e.target.classList.contains('action-btn')) return;
                        
                        const docId = this.dataset.docId;
                        viewDocument(docId);
                    });
                });
            }
            
            function viewDocument(docId) {
                window.open(`/api/document/${docId}/view`, '_blank');
            }
            
            function downloadDocument(docId) {
                window.open(`/api/document/${docId}/download`, '_blank');
            }
            
            function searchInDocument(docName) {
                document.getElementById('searchInput').value = docName;
                performSearch();
            }
            
            // Library search functionality
            document.getElementById('librarySearch').addEventListener('input', function(e) {
                const searchTerm = e.target.value.toLowerCase();
                const documentCards = document.querySelectorAll('.document-card');
                
                documentCards.forEach(card => {
                    const title = card.querySelector('.document-title').textContent.toLowerCase();
                    const meta = card.querySelector('.document-meta').textContent.toLowerCase();
                    
                    if (title.includes(searchTerm) || meta.includes(searchTerm)) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                });
            });
            
            // Library filter functionality
            document.querySelectorAll('[data-library-filter]').forEach(btn => {
                btn.addEventListener('click', function() {
                    // Update active filter
                    document.querySelectorAll('[data-library-filter]').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    
                    const filter = this.dataset.libraryFilter;
                    filterDocuments(filter);
                });
            });
            
            function filterDocuments(filter) {
                const documentCards = document.querySelectorAll('.document-card');
                
                documentCards.forEach(card => {
                    if (filter === 'all') {
                        card.style.display = 'block';
                    } else {
                        const type = card.querySelector('.document-meta').textContent.toLowerCase();
                        if (type.includes(filter)) {
                            card.style.display = 'block';
                        } else {
                            card.style.display = 'none';
                        }
                    }
                });
            }
            
            function refreshDocumentLibrary() {
                const documentGrid = document.getElementById('documentGrid');
                documentGrid.innerHTML = `
                    <div class="loading">
                        <div class="loading-spinner"></div>
                        <h3>Refreshing documents...</h3>
                    </div>
                `;
                loadDocumentLibrary();
            }
            
            async function loadBackupInfo() {
                try {
                    const response = await fetch('/api/backup/info');
                    if (response.ok) {
                        const info = await response.json();
                        // Update the current backup path display if it exists
                        const currentPathElement = document.getElementById('currentBackupPath');
                        if (currentPathElement) {
                            currentPathElement.textContent = info.current_path;
                        }
                    }
                } catch (error) {
                    console.error('Failed to load backup info:', error);
                }
            }
            
            async function createBackup() {
                const backupBtn = event.target;
                const backupStatus = document.getElementById('backupStatus');
                
                backupBtn.disabled = true;
                backupBtn.textContent = '🔄 Creating Backup...';
                backupStatus.innerHTML = '<span style="color: #007bff;">Creating backup...</span>';
                
                try {
                    const response = await fetch('/api/backup', { method: 'POST' });
                    const result = await response.json();
                    
                    if (result.success) {
                        backupStatus.innerHTML = `
                            <span style="color: #28a745;">✅ Backup completed successfully!</span><br>
                            <small style="color: #666;">Database: ${result.database_backup.success ? '✅' : '❌'}<br>
                            Files: ${result.file_backups.filter(f => f.backup_success).length}/${result.file_backups.length} backed up</small>
                        `;
                    } else {
                        backupStatus.innerHTML = `<span style="color: #dc3545;">❌ Backup failed: ${result.error}</span>`;
                    }
                } catch (error) {
                    backupStatus.innerHTML = `<span style="color: #dc3545;">❌ Backup failed: ${error.message}</span>`;
                } finally {
                    backupBtn.disabled = false;
                    backupBtn.textContent = '🔒 Create Backup';
                }
            }
            
            async function changeBackupPath() {
                const newPath = document.getElementById('newBackupPath').value.trim();
                if (!newPath) {
                    alert('Please enter a backup path');
                    return;
                }
                
                try {
                    const response = await fetch('/api/backup/path', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ path: newPath })
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        document.getElementById('backupStatus').innerHTML = `
                            <span style="color: #28a745;">✅ Backup path changed successfully!</span><br>
                            <small>New location: ${result.new_path}</small>
                        `;
                        document.getElementById('newBackupPath').value = '';
                        
                        // Update the current path display if it exists
                        const currentPathElement = document.getElementById('currentBackupPath');
                        if (currentPathElement) {
                            currentPathElement.textContent = result.new_path;
                        }
                    } else {
                        const error = await response.json();
                        document.getElementById('backupStatus').innerHTML = `
                            <span style="color: #dc3545;">❌ Failed to change backup path: ${error.error}</span>
                        `;
                    }
                } catch (error) {
                    console.error('Change path error:', error);
                    document.getElementById('backupStatus').innerHTML = `
                        <span style="color: #dc3545;">❌ Failed to change backup path: ${error.message}</span>
                    `;
                }
            }
            
            // Clear All functionality
            function showClearAllConfirmation() {
                document.getElementById('clearAllModal').style.display = 'block';
            }
            
            function closeClearAllModal() {
                document.getElementById('clearAllModal').style.display = 'none';
            }
            
            async function clearAllDocuments() {
                const clearBtn = event.target;
                clearBtn.disabled = true;
                clearBtn.textContent = '🗑️ Clearing...';
                
                try {
                    const response = await fetch('/api/clear-all', { method: 'POST' });
                    const result = await response.json();
                    
                    if (result.success) {
                        // Close modal
                        closeClearAllModal();
                        
                        // Show success message
                        alert('✅ All documents have been cleared successfully!');
                        
                        // Refresh the interface
                        loadStats();
                        loadDocumentLibrary();
                        
                        // Clear search results
                        document.getElementById('searchResults').innerHTML = '';
                        document.getElementById('searchInput').value = '';
                        
                        // Clear file list
                        document.getElementById('fileList').innerHTML = '';
                    } else {
                        alert(`❌ Failed to clear documents: ${result.error}`);
                    }
                } catch (error) {
                    alert(`❌ Error clearing documents: ${error.message}`);
                } finally {
                    clearBtn.disabled = false;
                    clearBtn.textContent = 'Yes, Clear Everything';
                }
            }
            
            // Close modal when clicking outside
            window.onclick = function(event) {
                const modal = document.getElementById('clearAllModal');
                if (event.target === modal) {
                    closeClearAllModal();
                }
            }
        </script>
        
        <!-- Clear All Confirmation Modal -->
        <div id="clearAllModal" class="modal" style="display: none;">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>⚠️ Clear All Documents</h3>
                    <span class="close" onclick="closeClearAllModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <p><strong>This action cannot be undone!</strong></p>
                    <p>This will permanently delete:</p>
                    <ul>
                        <li>All uploaded PDF files</li>
                        <li>All search indexes</li>
                        <li>All document metadata</li>
                        <li>All search history</li>
                    </ul>
                    <p>Are you sure you want to continue?</p>
                </div>
                <div class="modal-footer">
                    <button class="action-btn" onclick="closeClearAllModal()">Cancel</button>
                    <button class="action-btn" onclick="clearAllDocuments()" style="background: #dc3545; color: white; border-color: #dc3545;">Yes, Clear Everything</button>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''
    return html_template

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
        
        print(f"File uploaded: {original_filename} (ID: {file_id}, Size: {file_size} bytes)")
        
        # Create backup copy
        backup_success, backup_message = create_backup(file_path, file_id, original_filename)
        if backup_success:
            print(f"Backup created: {backup_message}")
        else:
            print(f"Backup failed: {backup_message}")
        
        # Upload to cloud storage if enabled
        if USE_CLOUD_STORAGE:
            cloud_success, cloud_message = upload_to_cloud(file_path, file_id, original_filename)
            if not cloud_success:
                print(f"Cloud upload failed: {cloud_message}")
                # Continue with local storage if cloud fails
        
        # Start background processing for PDF content extraction and indexing
        thread = threading.Thread(
            target=process_pdf_background, 
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
            'pageCount': 0,
            'storage': 'cloud' if USE_CLOUD_STORAGE else 'local'
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
    search_mode = request.args.get('mode', 'and').lower()  # 'and' or 'or'
    limit = int(request.args.get('limit', 10))
    
    print(f"Search request - Query: '{query}', Type: '{doc_type}', Mode: '{search_mode}', Limit: {limit}")
    
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
        
        # Filter out only the most common logical words that interfere with search
        logical_words = {'and', 'or', 'the', 'a', 'an'}
        
        # Split into terms and filter out only the most problematic logical words
        search_terms = [term.lower() for term in clean_query.split() 
                       if term.lower() not in logical_words and len(term) >= 2]
        
        if not search_terms:
            return jsonify({'results': [], 'total': 0, 'query': query, 'message': 'No meaningful search terms found after filtering'})
        
        print(f"Filtered search terms: {search_terms}")
        
        # Create multi-word search patterns
        # For FTS5: Use AND logic to find documents containing ALL search terms
        fts_and_patterns = []
        fts_or_patterns = []
        
        for term in search_terms:
            # Add the original term
            fts_and_patterns.append(f'"{term}"')
            fts_or_patterns.append(f'"{term}"')
            # Add wildcard pattern for partial matching
            fts_and_patterns.append(f'"{term}*"')
            fts_or_patterns.append(f'"{term}*"')
        
        # Create AND query (all terms must be present) and OR query (any term can be present)
        fts_and_query = ' AND '.join(fts_and_patterns)
        fts_or_query = ' OR '.join(fts_or_patterns)
        
        print(f"FTS AND query: {fts_and_query}")
        print(f"FTS OR query: {fts_or_query}")
        
        # Try FTS5 first, then fall back to LIKE queries for partial matching
        try:
            # Use the selected search mode
            if search_mode == 'or':
                # Use OR query for broader results
                fts_query_to_use = fts_or_query
                print(f"Using OR search mode: {fts_query_to_use}")
            else:
                # Use AND query for more precise results (default)
                fts_query_to_use = fts_and_query
                print(f"Using AND search mode: {fts_query_to_use}")
            
            if doc_type and doc_type != 'all':
                fts_query_sql = """
                    SELECT T.document_id, T.page_number, T.content
                    FROM document_content_fts AS T 
                    JOIN documents AS d ON T.document_id = d.id 
                    WHERE document_content_fts MATCH ? AND d.document_type = ? AND d.status = 'indexed'
                    LIMIT ?
                """
                params = [fts_query_to_use, doc_type, limit]
            else:
                fts_query_sql = """
                    SELECT T.document_id, T.page_number, T.content
                    FROM document_content_fts AS T 
                    JOIN documents AS d ON T.document_id = d.id 
                    WHERE document_content_fts MATCH ? AND d.status = 'indexed'
                    LIMIT ?
                """
                params = [fts_query_to_use, limit]
            
            cursor.execute(fts_query_sql, params)
            fts_matches = cursor.fetchall()
            print(f"FTS query returned {len(fts_matches)} results")
            
            # If FTS5 returns no results, try LIKE queries for partial matching
            if not fts_matches:
                print("FTS5 returned no results, trying LIKE queries for partial matching")
                
                # Build LIKE query for multi-word search based on search mode
                like_conditions = []
                like_params = []
                
                for term in search_terms:
                    like_conditions.append("T.content LIKE ?")
                    like_params.append(f"%{term}%")
                
                if like_conditions:
                    # Use the selected search mode for LIKE queries
                    if search_mode == 'or':
                        like_query = f"""
                            SELECT T.document_id, T.page_number, T.content
                            FROM document_content_fts AS T 
                            JOIN documents AS d ON T.document_id = d.id 
                            WHERE ({' OR '.join(like_conditions)}) AND d.status = 'indexed'
                            LIMIT ?
                        """
                        print(f"Executing LIKE OR query: {like_query}")
                    else:
                        like_query = f"""
                            SELECT T.document_id, T.page_number, T.content
                            FROM document_content_fts AS T 
                            JOIN documents AS d ON T.document_id = d.id 
                            WHERE ({' AND '.join(like_conditions)}) AND d.status = 'indexed'
                            LIMIT ?
                        """
                        print(f"Executing LIKE AND query: {like_query}")
                    
                    like_params.append(limit)
                    print(f"Parameters: {like_params}")
                    
                    cursor.execute(like_query, like_params)
                    fts_matches = cursor.fetchall()
                    print(f"LIKE query found {len(fts_matches)} matches")
        except Exception as e:
            print(f"FTS5 query failed, using LIKE fallback: {e}")
            # Fallback to LIKE queries with multi-word support based on search mode
            like_conditions = []
            like_params = []
            
            for term in search_terms:
                like_conditions.append("T.content LIKE ?")
                like_params.append(f"%{term}%")
            
            if like_conditions:
                # Use the selected search mode for LIKE queries
                if search_mode == 'or':
                    like_query = f"""
                        SELECT T.document_id, T.page_number, T.content
                        FROM document_content_fts AS T 
                        JOIN documents AS d ON T.document_id = d.id 
                        WHERE ({' OR '.join(like_conditions)}) AND d.status = 'indexed'
                        LIMIT ?
                    """
                else:
                    like_query = f"""
                        SELECT T.document_id, T.page_number, T.content
                        FROM document_content_fts AS T 
                        JOIN documents AS d ON T.document_id = d.id 
                        WHERE ({' AND '.join(like_conditions)}) AND d.status = 'indexed'
                        LIMIT ?
                    """
                
                like_params.append(limit)
                cursor.execute(like_query, like_params)
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
                    'lastUpdated': doc_details['upload_date'],
                    'filename': doc_details['original_name']
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
        snippet = pattern.sub(f'<span class="highlight">{term}</span>', snippet)
    
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

@app.route('/api/document/<doc_id>/view', methods=['GET'])
def view_pdf(doc_id):
    """Serves a PDF document for viewing in the browser."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT filename, original_name FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    
    if not result:
        return jsonify({'error': 'Document not found'}), 404
    
    file_path = os.path.join(UPLOAD_FOLDER, result['filename'])
    if not os.path.exists(file_path):
        return jsonify({'error': 'Document file not found on disk'}), 404
    
    # Serve the PDF with proper headers for browser viewing
    return send_from_directory(
        UPLOAD_FOLDER, 
        result['filename'],
        mimetype='application/pdf',
        as_attachment=False
    )

@app.route('/api/document/<doc_id>/download', methods=['GET'])
def download_pdf(doc_id):
    """Downloads a PDF document."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT filename, original_name FROM documents WHERE id = ?", (doc_id,))
    result = cursor.fetchone()
    
    if not result:
        return jsonify({'error': 'Document not found'}), 404
    
    file_path = os.path.join(UPLOAD_FOLDER, result['filename'])
    if not os.path.exists(file_path):
        return jsonify({'error': 'Document file not found on disk'}), 404
    
    # Serve the PDF as a download
    return send_from_directory(
        UPLOAD_FOLDER, 
        result['filename'],
        as_attachment=True,
        download_name=result['original_name']
    )

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

@app.route('/api/backup', methods=['POST'])
def create_backup_endpoint():
    """Manually trigger a backup of files and database."""
    try:
        # Backup database
        db_backup_success, db_backup_message = backup_database()
        
        # Get list of all documents for file backup
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, filename, original_name FROM documents WHERE status = 'indexed'")
        documents = cursor.fetchall()
        
        backup_results = []
        for doc in documents:
            file_path = os.path.join(UPLOAD_FOLDER, doc['filename'])
            if os.path.exists(file_path):
                backup_success, backup_message = create_backup(file_path, doc['id'], doc['original_name'])
                backup_results.append({
                    'file': doc['original_name'],
                    'backup_success': backup_success,
                    'message': backup_message
                })
        
        return jsonify({
            'success': True,
            'database_backup': {
                'success': db_backup_success,
                'message': db_backup_message
            },
            'file_backups': backup_results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/backup/path', methods=['POST'])
def change_backup_path():
    """Changes the backup folder path."""
    try:
        data = request.get_json()
        new_path = data.get('path', '').strip()
        
        if not new_path:
            return jsonify({'error': 'No path provided'}), 400
        
        # Expand user path (e.g., ~/Documents -> /Users/username/Documents)
        expanded_path = os.path.expanduser(new_path)
        
        # Create the directory if it doesn't exist
        try:
            os.makedirs(expanded_path, exist_ok=True)
        except PermissionError:
            return jsonify({'error': f'Permission denied: Cannot create directory at {expanded_path}'}), 403
        except Exception as e:
            return jsonify({'error': f'Cannot create directory: {str(e)}'}), 400
        
        # Test if we can write to the directory
        test_file = os.path.join(expanded_path, '.test_write')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            return jsonify({'error': f'Directory not writable: {str(e)}'}), 400
        
        # Update the global backup folder
        global BACKUP_FOLDER
        BACKUP_FOLDER = expanded_path
        
        # Save the new path to a config file for persistence
        config_data = {
            'backup_folder': expanded_path,
            'last_updated': datetime.now().isoformat()
        }
        
        config_file = os.path.join(os.path.dirname(__file__), 'backup_config.json')
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        print(f"Backup path changed to: {expanded_path}")
        
        return jsonify({
            'success': True,
            'new_path': expanded_path,
            'message': f'Backup path successfully changed to {expanded_path}'
        })
        
    except Exception as e:
        print(f"Change backup path error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/backup/info', methods=['GET'])
def get_backup_info():
    """Gets current backup configuration information."""
    return jsonify({
        'current_path': BACKUP_FOLDER,
        'enabled': ENABLE_BACKUPS,
        'retention_days': BACKUP_RETENTION_DAYS,
        'auto_backup': AUTO_BACKUP_ON_UPLOAD
    })

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

@app.route('/api/clear-all', methods=['POST'])
def clear_all_documents():
    """Clears all documents, indexes, and files from the system."""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Get all document filenames to delete from disk
        cursor.execute("SELECT filename FROM documents")
        filenames = cursor.fetchall()
        
        # Delete physical files from uploads folder
        for (filename,) in filenames:
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")
                except Exception as e:
                    print(f"Failed to delete file {file_path}: {e}")
        
        # Clear all tables
        cursor.execute("DELETE FROM documents")
        cursor.execute("DELETE FROM document_content_fts")
        cursor.execute("DELETE FROM search_logs")
        
        # Reset auto-increment counters
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('documents', 'document_content_fts', 'search_logs')")
        
        db.commit()
        
        print("All documents and data cleared successfully")
        
        return jsonify({
            'success': True,
            'message': 'All documents and data cleared successfully',
            'deleted_files': len(filenames),
            'deleted_records': cursor.rowcount
        })
        
    except Exception as e:
        print(f"Error clearing all documents: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("Initializing PDF Search & Storage System...")
    
    # Load backup configuration
    load_backup_config()
    
    init_database()
    
    # Clean up old backups on startup
    if ENABLE_BACKUPS:
        cleanup_old_backups()
    
    print("Starting server on http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)
