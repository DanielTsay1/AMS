// API Base URL - IMPORTANT: Ensure this matches your Flask backend URL
const API_BASE = 'http://localhost:5001';

// Global variables for managing state
let searchResults = [];
let currentFilter = 'all';
let isSearching = false;
let lastSearchQuery = '';
let fileUploadPollingIntervals = {}; // To store intervals for each file upload

// --- Utility Functions ---
function showMessage(message, type = 'info') {
    const modal = document.getElementById('myModal');
    const modalMessage = document.getElementById('modalMessage');
    modalMessage.textContent = message;
    // You could add classes for different message types (info, error, success)
    modal.style.display = 'flex'; // Show modal

    const closeButton = document.querySelector('.close-button');
    closeButton.onclick = function() {
        modal.style.display = 'none';
    };

    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = 'none';
        }
    };
}

// Debounce function to limit API calls
function debounce(func, delay) {
    let timeout;
    return function(...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

// --- Navigation and Section Display ---
function showSection(section, event) {
    if (event) event.preventDefault(); // Prevent default link behavior

    // Update nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    // Add active class to the clicked link
    if (event && event.target) { // Check if event and event.target exist (for click events)
        event.target.classList.add('active');
    } else { // For initial load or programmatic calls, set 'search' as active
        const searchNavLink = document.querySelector('.nav-link[onclick*="showSection(\'search\')"]');
        if (searchNavLink) {
            searchNavLink.classList.add('active');
        }
    }

    // Show/hide sections
    const uploadSection = document.getElementById('uploadSection');
    const searchSection = document.getElementById('searchSection');
    const contentTitle = document.getElementById('contentTitle');
    const contentSubtitle = document.getElementById('contentSubtitle');
    const fileList = document.getElementById('fileList');
    const debugControls = document.getElementById('debugControls');

    if (section === 'upload') {
        uploadSection.classList.add('active');
        searchSection.style.display = 'none';
        contentTitle.textContent = 'Document Upload';
        contentSubtitle.textContent = 'Upload PDF documents to make them searchable';
        fileList.style.display = 'block';
        debugControls.style.display = 'none'; // Hide debug controls in upload
        fetchDocumentsForList(); // Fetch and display uploaded files
    } else if (section === 'search') {
        uploadSection.classList.remove('active');
        searchSection.style.display = 'block';
        contentTitle.textContent = 'Document Search';
        contentSubtitle.textContent = 'Find information across your company\'s document library';
        // fileList.style.display = 'none'; // Keep file list hidden
        // Re-display existing search results if any, or default state
        displayResults(searchResults); // Display last search results or default message
        debugControls.style.display = 'block'; // Show debug controls in search
    } else if (section === 'analytics') {
        // Placeholder for analytics section
        uploadSection.classList.remove('active');
        searchSection.style.display = 'none';
        contentTitle.textContent = 'Analytics (Coming Soon!)';
        contentSubtitle.textContent = 'Detailed insights into document usage and search patterns.';
        fileList.style.display = 'none';
        document.getElementById('resultsSection').innerHTML = `<div class="loading"><h3>📊 Analytics Dashboard</h3><p>This section will provide detailed statistics and visualizations soon!</p></div>`;
        debugControls.style.display = 'none'; // Hide debug controls in analytics
    }
}

// --- File Upload Functionality ---
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
    for (const file of Array.from(files)) {
        if (file.type === 'application/pdf') {
            await uploadFile(file); // Await each upload to prevent race conditions in UI updates
        } else {
            showMessage(`Skipping "${file.name}": Only PDF files are supported.`);
        }
    }
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    // Generate unique temp ID
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    try {
        // Add a temporary item to the list immediately
        const tempFileItem = createTemporaryFileItem(file, tempId);
        document.getElementById('fileList').appendChild(tempFileItem);
        document.getElementById('fileList').style.display = 'block';

        console.log('Starting upload for:', file.name);

        const response = await fetch(`${API_BASE}/api/upload`, {
            method: 'POST',
            body: formData
        });

        console.log('Upload response status:', response.status);

        if (response.ok) {
            const result = await response.json();
            console.log('Upload result:', result);
            
            // Update the temporary item with the actual ID and start polling
            updateFileItem(tempFileItem, result, tempId);
            checkFileStatus(result.id, tempFileItem);
        } else {
            const error = await response.json();
            console.error('Upload error response:', error);
            updateFileItemToError(tempFileItem, error.error || 'Upload failed');
        }
    } catch (error) {
        console.error('Upload network error:', error);
        // Find the temp file item and update it to error state
        const tempFileItem = document.querySelector(`[data-temp-id="${tempId}"]`);
        if (tempFileItem) {
            updateFileItemToError(tempFileItem, 'Network Error - Check if backend is running');
        }
    }
}

function createTemporaryFileItem(file, tempId) {
    const fileItem = document.createElement('div');
    fileItem.className = 'file-item';
    fileItem.dataset.tempId = tempId;
    fileItem.innerHTML = `
        <div class="file-icon">📄</div>
        <div class="file-info">
            <div class="file-name">${file.name}</div>
            <div class="file-meta">${(file.size / 1024 / 1024).toFixed(2)} MB • Uploading...</div>
        </div>
        <div class="file-status status-processing">Uploading</div>
    `;
    return fileItem;
}

function updateFileItem(tempFileItem, fileData, tempId) {
    // Find the file item using its temporary ID
    const existingItem = document.querySelector(`[data-temp-id="${tempId}"]`);
    if (existingItem) {
        existingItem.dataset.id = fileData.id; // Set the real ID
        existingItem.removeAttribute('data-temp-id'); // Remove temp ID
        existingItem.querySelector('.file-name').textContent = fileData.name;
        existingItem.querySelector('.file-meta').textContent = `${(fileData.size / 1024 / 1024).toFixed(2)} MB • Processing...`;
        const statusElement = existingItem.querySelector('.file-status');
        statusElement.textContent = 'Processing';
        statusElement.className = 'file-status status-processing';
        console.log('Updated file item to processing state for:', fileData.name);
    }
}

function updateFileItemToError(fileItem, errorMessage) {
    if (!fileItem) {
        console.error('File item is null/undefined in updateFileItemToError');
        return;
    }
    
    const statusElement = fileItem.querySelector('.file-status');
    const metaElement = fileItem.querySelector('.file-meta');
    const iconElement = fileItem.querySelector('.file-icon');
    
    if (statusElement) statusElement.textContent = `Error: ${errorMessage}`;
    if (statusElement) statusElement.className = 'file-status status-error';
    if (iconElement) iconElement.style.color = '#dc3545'; // Red icon for error
    if (metaElement) {
        const currentText = metaElement.textContent || '';
        metaElement.textContent = currentText.replace('Uploading...', 'Upload Failed').replace('Processing...', 'Processing Failed');
    }
    
    // Clear any polling interval if it was set
    const fileId = fileItem.dataset.id || fileItem.dataset.tempId;
    if (fileId && fileUploadPollingIntervals[fileId]) {
        clearInterval(fileUploadPollingIntervals[fileId]);
        delete fileUploadPollingIntervals[fileId];
    }
    
    console.log('Updated file item to error state:', errorMessage);
}

async function checkFileStatus(fileId, fileItem) {
    let attempts = 0;
    const maxAttempts = 60; // Check for up to 2 minutes (60 * 2s)
    
    console.log('Starting status check for file ID:', fileId);

    const intervalId = setInterval(async () => {
        attempts++;
        console.log(`Status check attempt ${attempts}/${maxAttempts} for file:`, fileId);
        
        if (attempts > maxAttempts) {
            clearInterval(intervalId);
            delete fileUploadPollingIntervals[fileId];
            updateFileItemToError(fileItem, 'Processing timeout - file may still be processing in background');
            console.log('File processing timed out for:', fileId);
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/api/documents`);
            if (!response.ok) {
                console.error(`Documents API error! status: ${response.status}`);
                return; // Don't stop interval, keep trying
            }
            
            const documents = await response.json();
            const doc = documents.find(d => d.id === fileId);
            
            if (doc) {
                console.log(`Found document status: ${doc.status} for file:`, doc.name);
                
                const statusElement = fileItem.querySelector('.file-status');
                const metaElement = fileItem.querySelector('.file-meta');
                const iconElement = fileItem.querySelector('.file-icon');

                if (doc.status === 'indexed') {
                    clearInterval(intervalId);
                    delete fileUploadPollingIntervals[fileId];
                    
                    if (statusElement) statusElement.textContent = 'Indexed';
                    if (statusElement) statusElement.className = 'file-status status-complete';
                    if (metaElement) metaElement.textContent = `${(doc.size / 1024 / 1024).toFixed(2)} MB • Indexed ${new Date(doc.uploadDate).toLocaleDateString()}`;
                    if (iconElement) iconElement.style.color = '#0a66c2'; // Blue icon for complete
                    
                    showMessage(`"${doc.name}" successfully indexed!`);
                    debouncedUpdateStats(); // Update stats after successful indexing
                    console.log('File successfully indexed:', doc.name);
                    
                } else if (doc.status === 'error') {
                    clearInterval(intervalId);
                    delete fileUploadPollingIntervals[fileId];
                    updateFileItemToError(fileItem, doc.error || 'Indexing Failed');
                    debouncedUpdateStats(); // Update stats even on error
                    console.log('File indexing failed:', doc.name, doc.error);
                } else {
                    console.log(`File still processing (${doc.status}):`, doc.name);
                }
            } else {
                console.log('Document not found in response, attempt:', attempts);
            }
        } catch (error) {
            console.error('Status check network error:', error);
            // Don't stop interval on network error, keep trying
        }
    }, 2000); // Check every 2 seconds
    
    fileUploadPollingIntervals[fileId] = intervalId; // Store interval ID
}

async function fetchDocumentsForList() {
    const fileList = document.getElementById('fileList');
    fileList.innerHTML = ''; // Clear existing list
    
    try {
        console.log('Fetching documents list...');
        const response = await fetch(`${API_BASE}/api/documents`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const documents = await response.json();
        
        console.log('Documents fetched:', documents);

        if (documents.length === 0) {
            fileList.innerHTML = '<div class="loading" style="padding: 20px;"><h3>No documents uploaded yet.</h3><p>Use the area above to add your first PDF!</p></div>';
            fileList.style.display = 'block';
        } else {
            documents.forEach(doc => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.dataset.id = doc.id; // Store the ID on the element

                let statusClass = 'status-processing';
                let iconColor = '#d32f2f'; // Default red
                let statusText = doc.status;
                
                if (doc.status === 'indexed') {
                    statusClass = 'status-complete';
                    iconColor = '#0a66c2'; // Blue
                    statusText = 'Indexed';
                } else if (doc.status === 'error') {
                    statusClass = 'status-error';
                    iconColor = '#dc3545'; // Red
                    statusText = `Error: ${doc.error || 'Processing failed'}`;
                } else if (doc.status === 'processing') {
                    statusClass = 'status-processing';
                    iconColor = '#ff9800'; // Orange
                    statusText = 'Processing';
                }

                const uploadDate = new Date(doc.uploadDate).toLocaleDateString();
                const metaText = doc.status === 'processing' ? 
                    `${(doc.size / 1024 / 1024).toFixed(2)} MB • Processing...` :
                    `${(doc.size / 1024 / 1024).toFixed(2)} MB • Indexed ${uploadDate}`;
                
                fileItem.innerHTML = `
                    <div class="file-icon" style="color: ${iconColor};">📄</div>
                    <div class="file-info">
                        <div class="file-name">${doc.name}</div>
                        <div class="file-meta">${metaText}</div>
                    </div>
                    <div class="file-status ${statusClass}">${statusText}</div>
                `;
                fileList.appendChild(fileItem);

                // If still processing, start polling for its status (but don't duplicate)
                if (doc.status === 'processing' && !fileUploadPollingIntervals[doc.id]) {
                    console.log('Starting status polling for existing processing document:', doc.name);
                    checkFileStatus(doc.id, fileItem);
                }
            });
            fileList.style.display = 'block';
        }
    } catch (error) {
        console.error('Failed to fetch documents for list:', error);
        fileList.innerHTML = '<div class="loading" style="padding: 20px;"><h3>Failed to load documents.</h3><p>Please check your backend connection.</p></div>';
    }
}

// --- Search Functionality ---
let searchTimeout;
const searchInput = document.getElementById('searchInput');
const navSearchInput = document.getElementById('navSearchInput');
const searchButton = document.getElementById('searchButton');
const searchIndicator = document.getElementById('searchIndicator');

// Use a debounced version of performSearch for input events
const debouncedPerformSearch = debounce(performSearch, 500);

searchInput.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    if (query.length >= 2) {
        searchIndicator.textContent = 'Typing...';
        searchIndicator.style.display = 'block';
        debouncedPerformSearch();
    } else if (query.length === 0) {
        clearSearchResults();
    } else {
        searchIndicator.style.display = 'none';
    }
    // Keep nav search input in sync
    navSearchInput.value = query;
});

// Search input Enter key
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        searchButton.click(); // Trigger search button click
    }
});

// Search button click handler
searchButton.addEventListener('click', (e) => {
    e.preventDefault();
    performSearch();
});

// Nav search input event listener
navSearchInput.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    if (query.length >= 2) {
        searchIndicator.textContent = 'Typing...'; // Show indicator even for nav search
        searchIndicator.style.display = 'block';
        debouncedPerformSearch();
    } else if (query.length === 0) {
        clearSearchResults();
    } else {
        searchIndicator.style.display = 'none';
    }
    // Keep main search input in sync
    searchInput.value = query;
});

navSearchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        document.getElementById('searchInput').value = navSearchInput.value; // Sync main input
        performSearch();
    }
});

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query || isSearching) return;

    lastSearchQuery = query;
    isSearching = true;
    searchIndicator.textContent = 'Searching...';
    searchIndicator.style.display = 'block';
    showLoading(); // Show loading spinner and message

    try {
        const response = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&type=${currentFilter}&limit=10`);
        
        if (response.ok) {
            const data = await response.json();
            searchResults = data.results; // FTS5 returns pre-highlighted snippets
            sessionStorage.setItem('lastSearchResults', JSON.stringify(searchResults));
            sessionStorage.setItem('lastSearchQuery', query);
            
            displayResults(searchResults);
        } else {
            const error = await response.json();
            document.getElementById('resultsSection').innerHTML = `
                <div class="loading">
                    <h3>Search failed</h3>
                    <p>${error.error || 'An unknown error occurred during search.'}</p>
                </div>
            `;
            showMessage(`Search failed: ${error.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Search network error:', error);
        document.getElementById('resultsSection').innerHTML = `
            <div class="loading">
                <h3>Search connection error</h3>
                <p>Could not connect to the backend. Please ensure the Flask server is running at ${API_BASE}.</p>
            </div>
        `;
        showMessage(`Search failed. Please ensure the backend is running at ${API_BASE}.`, 'error');
    } finally {
        isSearching = false;
        searchIndicator.style.display = 'none'; // Hide indicator after search
        debouncedUpdateRecentSearches(); // Update recent searches after a successful search
    }
}

function showLoading() {
    document.getElementById('resultsSection').innerHTML = `
        <div class="loading">
            <div class="loading-spinner"></div>
            <h3>Searching documents...</h3>
            <p>Analyzing your query and finding relevant information</p>
        </div>
    `;
    document.getElementById('debugControls').style.display = 'none'; // Hide debug during loading
}

function displayResults(results) {
    const filteredResults = currentFilter === 'all' 
        ? results 
        : results.filter(r => r.type === currentFilter);

    const resultsHTML = filteredResults.length > 0 
        ? filteredResults.map(result => createResultHTML(result)).join('')
        : '<div class="loading"><h3>No results found</h3><p>Try adjusting your search terms or filters, or upload more documents.</p></div>';

    document.getElementById('resultsSection').innerHTML = resultsHTML;
    document.getElementById('debugControls').style.display = 'block'; // Show debug after results
}

function createResultHTML(result) {
    // Note: snippet is already highlighted by backend FTS5
    return `
        <div class="result-item">
            <div class="result-header">
                <div class="result-title" onclick="viewPDF('${result.id}')">${result.title}</div>
                <div class="result-meta">
                    <span>📄 ${result.document}</span>
                    <span>Page ${result.page}</span>
                    <span>${result.confidence}% match</span>
                    <span>Updated ${new Date(result.lastUpdated).toLocaleDateString()}</span>
                </div>
            </div>
            <div class="result-snippet">${result.snippet}</div>
            <div class="result-actions">
                <button class="action-btn view-pdf" onclick="viewPDF('${result.id}')">
                    View PDF
                </button>
                <button class="action-btn copy-link" onclick="copyLink('${result.id}', ${result.page})">
                    Copy Link
                </button>
            </div>
        </div>
    `;
}

function clearSearchResults() {
    searchResults = [];
    lastSearchQuery = '';
    sessionStorage.removeItem('lastSearchResults');
    sessionStorage.removeItem('lastSearchQuery');
    document.getElementById('resultsSection').innerHTML = `
        <div class="loading" id="defaultState">
            <h3>🔍 Ready to search</h3>
            <p>Upload PDF documents first, then search through them for relevant information.</p>
        </div>
        <div id="debugControls" style="display: none; margin-top: 20px; text-align: center;">
            <button onclick="restoreSearchResults()" style="padding: 8px 16px; background: #0a66c2; color: white; border: none; border-radius: 4px; cursor: pointer;">
                Restore Search Results
            </button>
            <button onclick="console.log('Search Results:', searchResults); console.log('Last Query:', lastSearchQuery);" style="padding: 8px 16px; background: #0a66c2; color: white; border: none; border-radius: 4px; cursor: pointer; margin-left: 10px;">
                Debug Info
            </button>
        </div>
    `;
    document.getElementById('searchIndicator').style.display = 'none';
}

// --- PDF Viewing and Linking ---
function viewPDF(docId) {
    // Open PDF in a new tab using the backend endpoint
    const pdfUrl = `${API_BASE}/api/document/${docId}`;
    window.open(pdfUrl, '_blank');
}

function copyLink(docId, page) {
    const link = `${window.location.origin}/view-document?id=${docId}#page=${page}`; // Example client-side link
    navigator.clipboard.writeText(link).then(() => {
        const btn = event.target;
        btn.textContent = 'Copied!';
        setTimeout(() => {
            btn.textContent = 'Copy Link';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy text: ', err);
        showMessage('Failed to copy link. Please try again or copy manually.');
    });
}

function setSearch(query) {
    document.getElementById('searchInput').value = query;
    document.getElementById('navSearchInput').value = query;
    performSearch();
}

function restoreSearchResults() {
    const storedResults = sessionStorage.getItem('lastSearchResults');
    const storedQuery = sessionStorage.getItem('lastSearchQuery');
    if (storedResults && storedQuery) {
        searchResults = JSON.parse(storedResults);
        lastSearchQuery = storedQuery;
        document.getElementById('searchInput').value = storedQuery;
        document.getElementById('navSearchInput').value = storedQuery;
        displayResults(searchResults);
        showMessage('Previous search results restored.');
    } else {
        showMessage('No previous search results found to restore.');
    }
}

// --- Sidebar Stats and Recent Searches ---
async function updateStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const stats = await response.json();

        document.getElementById('totalDocsStat').textContent = stats.totalDocuments.toLocaleString();
        document.getElementById('pagesIndexedStat').textContent = stats.totalPages.toLocaleString();
        document.getElementById('lastUpdatedStat').textContent = stats.lastUpdated;
        document.getElementById('accuracyStat').textContent = `${stats.accuracy}%`;

        // Optionally display document types (if you add a breakdown)
        // console.log('Document types:', stats.documentTypes);
    } catch (error) {
        console.error('Failed to fetch stats:', error);
        document.getElementById('totalDocsStat').textContent = 'N/A';
        document.getElementById('pagesIndexedStat').textContent = 'N/A';
        document.getElementById('lastUpdatedStat').textContent = 'Error';
        document.getElementById('accuracyStat').textContent = 'N/A';
    }
}

async function updateRecentSearches() {
    try {
        const response = await fetch(`${API_BASE}/api/recent-searches`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const searches = await response.json();
        const recentSearchesList = document.getElementById('recentSearchesList');
        recentSearchesList.innerHTML = ''; // Clear existing list

        if (searches.length === 0) {
            recentSearchesList.innerHTML = '<div class="recent-item">No recent searches</div>';
        } else {
            searches.forEach(query => {
                const item = document.createElement('div');
                item.className = 'recent-item';
                item.textContent = query;
                item.onclick = () => setSearch(query); // Set search input and perform search
                recentSearchesList.appendChild(item);
            });
        }
    } catch (error) {
        console.error('Failed to fetch recent searches:', error);
        document.getElementById('recentSearchesList').innerHTML = '<div class="recent-item" style="color: #dc3545;">Failed to load.</div>';
    }
}

// Debounced versions for frequent updates
const debouncedUpdateStats = debounce(updateStats, 1000);
const debouncedUpdateRecentSearches = debounce(updateRecentSearches, 1000);

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing application...');
    showSection('search'); // Show search section by default
    updateStats(); // Initial load of stats
    updateRecentSearches(); // Initial load of recent searches

    // Restore last search results on page load if available
    const storedResults = sessionStorage.getItem('lastSearchResults');
    const storedQuery = sessionStorage.getItem('lastSearchQuery');
    if (storedResults && storedQuery) {
        searchResults = JSON.parse(storedResults);
        lastSearchQuery = storedQuery;
        document.getElementById('searchInput').value = storedQuery;
        document.getElementById('navSearchInput').value = storedQuery;
        displayResults(searchResults);
    }
    
    // Auto-focus search input if it exists
    const searchInputElement = document.getElementById('searchInput');
    if (searchInputElement) {
        searchInputElement.focus();
    }
    
    console.log('Application initialized successfully');
});