# AMS - Document Management System

A modern document management system with PDF upload, indexing, and semantic search capabilities.

## Features

- **PDF Upload & Processing**: Drag & drop PDF files for automatic text extraction and indexing
- **Smart Search**: Full-text search across all uploaded documents with relevance scoring
- **Document Management**: Track document status, file sizes, and processing metadata
- **Modern UI**: Clean, responsive interface built with vanilla HTML/CSS/JavaScript
- **RESTful API**: Flask backend with comprehensive API endpoints

## Setup

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd AMS
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to `http://localhost:5001`

## Usage

### Uploading Documents

1. Click the "Upload" tab in the navigation
2. Drag and drop PDF files or click "Choose Files"
3. Files will be automatically processed and indexed
4. Monitor processing status in real-time

### Searching Documents

1. Use the main search bar to find information
2. Apply filters by document type (Policies, Manuals, FAQs, etc.)
3. View search results with highlighted matching terms
4. Click "View PDF" to open documents in a new tab

### API Endpoints

- `GET /` - Home endpoint with API information
- `POST /api/upload` - Upload PDF files
- `GET /api/search?q=<query>&type=<filter>&limit=<number>` - Search documents
- `GET /api/documents` - Get all uploaded documents
- `GET /api/document/<id>` - Download specific document
- `GET /api/stats` - Get system statistics
- `GET /api/recent-searches` - Get recent search queries
- `GET /health` - Health check endpoint

## File Structure

```
AMS/
├── app.py              # Flask backend application
├── index.html          # Frontend interface
├── requirements.txt    # Python dependencies
├── ams.db             # SQLite database (created automatically)
├── uploads/           # Uploaded PDF storage (created automatically)
└── README.md          # This file
```

## Database Schema

The system uses SQLite with three main tables:

- **documents**: Stores file metadata and processing status
- **document_content**: Contains extracted text content for search
- **search_logs**: Tracks search queries and results

## Configuration

Key configuration options in `app.py`:

- `UPLOAD_FOLDER`: Directory for storing uploaded files
- `MAX_FILE_SIZE`: Maximum file size limit (default: 50MB)
- `ALLOWED_EXTENSIONS`: Supported file types (currently PDF only)

## Development

### Adding New Features

- **Frontend**: Modify `index.html` JavaScript functions
- **Backend**: Add new routes in `app.py`
- **Database**: Update schema in `init_database()` function

### Testing

The application includes basic error handling and validation:

- File type validation (PDF only)
- File size limits
- Database connection error handling
- Search result validation

## Troubleshooting

### Common Issues

1. **Upload fails**: Check file size and format (PDF only)
2. **Search returns no results**: Ensure documents have been uploaded and indexed
3. **Database errors**: Delete `ams.db` to reset the database
4. **Port conflicts**: Change port in `app.py` if 5001 is in use

### Logs

Check the console output for error messages and processing status.

## License

This project is open source and available under the MIT License.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues and questions, please open an issue in the repository.
