# 📚 PDF Search & Storage System

A modern, web-based document management system that allows you to upload, index, and search through PDF documents using advanced full-text search capabilities.

## ✨ Features

- **📤 PDF Upload**: Drag & drop or click to upload PDF documents
- **🔍 Advanced Search**: Full-text search across all uploaded documents
- **📊 Document Analytics**: View statistics and document types
- **🎯 Smart Filtering**: Filter results by document type (policies, manuals, FAQs, etc.)
- **📱 Responsive Design**: Works on desktop and mobile devices
- **⚡ Fast Indexing**: Background processing with real-time status updates
- **🎨 Modern UI**: Beautiful, intuitive interface with smooth animations

## 🚀 Quick Start

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

## 📖 How to Use

### 1. Upload Documents
- Navigate to the **Upload** section
- Drag & drop PDF files or click to browse
- Watch real-time processing status
- Documents are automatically indexed for search

### 2. Search Documents
- Use the search bar to find information
- Type your query (minimum 2 characters)
- Results show relevant snippets with highlighted terms
- Use filters to narrow down by document type

### 3. View Results
- Click on document titles to view details
- See confidence scores for search relevance
- Filter results by document type
- View page numbers and document metadata

## 🏗️ Architecture

- **Backend**: Flask (Python) with SQLite database
- **Frontend**: Modern HTML5, CSS3, and vanilla JavaScript
- **Search Engine**: SQLite FTS5 (Full-Text Search) with Porter stemming
- **File Processing**: PyPDF2 for PDF text extraction
- **Database**: SQLite with optimized schemas and FTS5 virtual tables

## 🔧 Configuration

### Environment Variables
- `MAX_FILE_SIZE`: Maximum file size (default: 50MB)
- `UPLOAD_FOLDER`: Directory for uploaded files (default: `uploads/`)
- `DATABASE`: Database file path (default: `documents.db`)

### API Endpoints
- `GET /` - Main web interface
- `POST /api/upload` - Upload PDF documents
- `GET /api/search?q=<query>` - Search documents
- `GET /api/documents` - List all documents
- `GET /api/stats` - System statistics

## 📁 Project Structure

```
PDF-Search-System/
├── app.py              # Flask backend application
├── requirements.txt    # Python dependencies
├── start.sh            # Startup script
├── uploads/            # PDF storage directory
├── documents.db        # SQLite database (created automatically)
├── venv/               # Python virtual environment
└── README.md           # This file
```

## 🐛 Troubleshooting

### Common Issues

1. **Port already in use**
   - Change the port in `app.py` (line 543)
   - Or stop other services using port 5001

2. **Upload fails**
   - Check file size (max 50MB)
   - Ensure file is a valid PDF
   - Check console for error messages

3. **Search not working**
   - Verify documents are fully indexed (check status in upload section)
   - Check browser console for errors
   - Ensure backend is running

4. **Database errors**
   - Delete `documents.db` file to reset
   - Check file permissions in project directory

### Debug Mode

The application includes comprehensive logging:
- Check terminal output for backend logs
- Use browser developer tools for frontend debugging
- Monitor file processing status in real-time

## 🔒 Security Notes

- File uploads are validated for type and size
- SQL injection protection via parameterized queries
- CORS enabled for development (configure for production)
- File names are sanitized before storage
- Background processing prevents blocking

## 🚧 Development

### Adding New Features

1. **Backend**: Modify `app.py` for new API endpoints
2. **Frontend**: Update HTML/CSS/JavaScript in the template string
3. **Database**: Modify schema in `init_database()` function
4. **Styling**: Update CSS within the HTML template

### Testing

- Test with various PDF types and sizes
- Verify search functionality with different queries
- Check responsive design on mobile devices
- Monitor performance with large document collections

## 📄 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

---

**Happy Document Searching! 📚🔍**
