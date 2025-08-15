# 📚 AMS - Document Management System

A modern, web-based document management system that allows you to upload, index, and search through PDF documents using advanced text search capabilities.

## ✨ Features

- **📤 PDF Upload**: Drag & drop or click to upload PDF documents
- **🔍 Advanced Search**: Full-text search across all uploaded documents
- **📊 Document Analytics**: View statistics and document types
- **🎯 Smart Filtering**: Filter results by document type (policies, manuals, FAQs, etc.)
- **📱 Responsive Design**: Works on desktop and mobile devices
- **⚡ Fast Indexing**: Background processing with real-time status updates

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
   python3 app.py
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
- Click on document titles to view PDFs
- Copy direct links to specific pages
- See confidence scores for search relevance

## 🏗️ Architecture

- **Backend**: Flask (Python) with SQLite database
- **Frontend**: Vanilla JavaScript with modern CSS
- **Search Engine**: SQLite FTS5 (Full-Text Search) with fallback
- **File Processing**: PyPDF2 for PDF text extraction
- **Database**: SQLite with optimized schemas

## 🔧 Configuration

### Environment Variables
- `MAX_FILE_SIZE`: Maximum file size (default: 50MB)
- `UPLOAD_FOLDER`: Directory for uploaded files (default: `uploads/`)
- `DATABASE`: Database file path (default: `ams.db`)

### API Endpoints
- `POST /api/upload` - Upload PDF documents
- `GET /api/search?q=<query>` - Search documents
- `GET /api/documents` - List all documents
- `GET /api/stats` - System statistics
- `GET /api/recent-searches` - Recent search queries

## 📁 Project Structure

```
AMS/
├── app.py              # Flask backend application
├── index.html          # Main frontend interface
├── index.css           # Styling and layout
├── java.js             # Frontend functionality
├── requirements.txt    # Python dependencies
├── start.sh           # Startup script
├── uploads/           # PDF storage directory
├── ams.db             # SQLite database (created automatically)
└── README.md          # This file
```

## 🐛 Troubleshooting

### Common Issues

1. **Port already in use**
   - Change the port in `app.py` (line 969)
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
   - Delete `ams.db` file to reset
   - Check file permissions in project directory

### Debug Mode

The application includes debug controls in the search section:
- **Restore Search Results**: Restore previous search
- **Debug Info**: View console logs

## 🔒 Security Notes

- File uploads are validated for type and size
- SQL injection protection via parameterized queries
- CORS enabled for development (configure for production)
- File names are sanitized before storage

## 🚧 Development

### Adding New Features

1. **Backend**: Modify `app.py` for new API endpoints
2. **Frontend**: Update `java.js` for new functionality
3. **Styling**: Modify `index.css` for UI changes

### Testing

- Test with various PDF types and sizes
- Verify search functionality with different queries
- Check responsive design on mobile devices

## 📄 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

---

**Happy Document Searching! 📚🔍**
