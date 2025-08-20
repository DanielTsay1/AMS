# AMS Search & Storage System

##  Features

- PDF Upload: Drag & drop or click to upload PDF documents
- Full-text search across all uploaded documents

## Quick Start

### Prerequisites

- Python 3.8 or higher
- Modern web browser (Chrome, Firefox, Safari, Edge)

### Installation & Setup

1. **Clone or download** this repository to your local machine

2. **Run the startup script** (recommended):
   ```bash
   ./start.sh
   ```
   
   Or manually:
   ```bash
   # Create virtual environment
   python3 -m venv venv
   
   # Activate virtual environment
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Start the application
   python app.py
   ```

3. **Open your browser** and go to: http://localhost:5001

- **Backend**: Flask (Python) with SQLite database
- **Frontend**: Modern HTML5, CSS3, and vanilla JavaScript
- **Search Engine**: SQLite FTS5 (Full-Text Search) with Porter stemming
- **File Processing**: PyPDF2 for PDF text extraction
- **Database**: SQLite with optimized schemas and FTS5 virtual tables

 Maximum file size (default: 50MB)
- `UPLOAD_FOLDER`: Directory for uploaded files (default: `uploads/`)
- `DATABASE`: Database file path (default: `documents.db`)


### Common Issues

1. **Port already in use**
   - Change the port in `app.py` 
   - Or stop other services using port 5001

2. **Upload fails**
   - Check file size (max 50MB)
   - Ensure file is a valid PDF(Will not read screenshots or images)
   - Check console for error messages

3. **Search not working**
   - Verify documents are fully indexed (check status in upload section)
   - Check browser console for errors
   - Ensure backend is running

4. **Database errors**
   - Delete `documents.db` file to reset
   - Check file permissions in project directory



