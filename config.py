# Configuration file for PDF Search & Storage System

# File Storage Settings
UPLOAD_FOLDER = 'uploads'
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = {'pdf'}

# Database Settings
DATABASE = 'documents.db'

# Backup Settings
ENABLE_BACKUPS = True
BACKUP_FOLDER = 'backups'
BACKUP_RETENTION_DAYS = 30  # Keep backups for 30 days
AUTO_BACKUP_ON_UPLOAD = True  # Create backup automatically when files are uploaded

# Cloud Storage Settings (Optional)
USE_CLOUD_STORAGE = False  # Set to True to enable cloud storage
CLOUD_STORAGE_TYPE = 's3'  # 's3', 'gcs', 'azure'
CLOUD_BUCKET_NAME = 'your-bucket-name'
CLOUD_REGION = 'us-east-1'

# AWS S3 Configuration (if using S3)
AWS_ACCESS_KEY_ID = 'your-access-key'
AWS_SECRET_ACCESS_KEY = 'your-secret-key'

# Google Cloud Storage Configuration (if using GCS)
GCS_PROJECT_ID = 'your-project-id'
GCS_CREDENTIALS_FILE = 'path/to/service-account-key.json'

# Azure Blob Storage Configuration (if using Azure)
AZURE_CONNECTION_STRING = 'your-connection-string'
AZURE_CONTAINER_NAME = 'your-container-name'

# Server Settings
HOST = '0.0.0.0'
PORT = 5001
DEBUG = True

# Security Settings
SECRET_KEY = 'your-secret-key-here'  # Change this in production
CORS_ENABLED = True

# Performance Settings
MAX_SEARCH_RESULTS = 100
SEARCH_TIMEOUT = 30  # seconds
UPLOAD_TIMEOUT = 300  # seconds
