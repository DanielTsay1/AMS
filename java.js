// API Base URL - CHANGE THIS to match your Python backend port
const API_BASE = 'http://localhost:5001'; // Change from 5001 to your actual Python port

// Global variables
let searchResults = [];
let currentFilter = 'all';
let isSearching = false;

// Enhanced search function with better error handling
async function performSearch() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query || isSearching) return;

    console.log('🔍 Starting search for:', query);
    console.log('📡 API_BASE:', API_BASE);
    
    isSearching = true;
    showLoading();
    
    try {
        // Test if backend is reachable first
        console.log('🔌 Testing backend connection...');
        const testResponse = await fetch(API_BASE, { 
            method: 'GET',
            mode: 'cors' // Explicitly enable CORS
        });
        console.log('✅ Backend test response:', testResponse.status);
        
        // Construct search URL - try different formats your backend might expect
        let searchUrl, searchData;
        
        // Option 1: GET request with query parameters
        searchUrl = `${API_BASE}/api/search?q=${encodeURIComponent(query)}`;
        console.log('📤 Trying GET request:', searchUrl);
        
        let response = await fetch(searchUrl, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            mode: 'cors'
        });
        
        // If GET fails, try POST
        if (!response.ok) {
            console.log('❌ GET failed, trying POST method');
            searchUrl = `${API_BASE}/api/search`;
            response = await fetch(searchUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                mode: 'cors',
                body: JSON.stringify({ 
                    query: query,
                    q: query, // Some APIs use 'q' instead
                    search_term: query, // Others use 'search_term'
                    limit: 10 
                })
            });
        }
        
        console.log('📥 Search response status:', response.status);
        console.log('📥 Search response headers:', [...response.headers.entries()]);
        
        if (response.ok) {
            const data = await response.json();
            console.log('📋 Raw API response:', data);
            
            // Handle different response formats your backend might return
            let results = [];
            if (Array.isArray(data)) {
                results = data;
            } else if (data.results && Array.isArray(data.results)) {
                results = data.results;
            } else if (data.data && Array.isArray(data.data)) {
                results = data.data;
            } else if (data.documents && Array.isArray(data.documents)) {
                results = data.documents;
            } else {
                console.log('Unexpected response format, trying to extract results...');
                // Try to find any array in the response
                for (const [key, value] of Object.entries(data)) {
                    if (Array.isArray(value)) {
                        results = value;
                        console.log(`📦 Found results in '${key}' field`);
                        break;
                    }
                }
            }
            
            searchResults = results;
            console.log('✅ Processed search results:', searchResults.length, 'items');
            
            if (searchResults.length === 0) {
                console.log('📭 No results found');
                displayResults([]);
            } else {
                // Add search term highlighting
                searchResults = searchResults.map(result => ({
                    ...result,
                    snippet: result.snippet ? highlightSearchTerms(result.snippet, query) : 'No snippet available'
                }));
                displayResults(searchResults);
            }
        } else {
            const errorText = await response.text();
            console.error('❌ API error:', response.status, errorText);
            throw new Error(`Backend returned ${response.status}: ${errorText}`);
        }
        
    } catch (error) {
        console.error('💥 Search error:', error);
        
        // Enhanced error detection
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            console.log('🌐 Network error - backend probably not running');
            displayBackendError('Cannot connect to backend. Is your Python server running?');
        } else if (error.message.includes('CORS')) {
            console.log('🚫 CORS error - backend needs CORS configuration');
            displayBackendError('CORS error. Check your Python backend CORS settings.');
        } else {
            console.log('⚠️ API error - backend responded but with error');
            displayBackendError(`Backend error: ${error.message}`);
        }
    } finally {
        isSearching = false;
    }
}

// Enhanced backend connection test
async function testBackendConnection() {
    console.log('🧪 Testing backend connection...');
    const results = [];
    
    // Test 1: Basic connection
    try {
        console.log('Test 1: Basic connection to', API_BASE);
        const response = await fetch(API_BASE, { 
            method: 'GET',
            mode: 'cors',
            headers: { 'Content-Type': 'application/json' }
        });
        results.push(`✅ Basic connection: ${response.status} ${response.statusText}`);
        console.log('✅ Basic connection works:', response.status);
    } catch (error) {
        results.push(`❌ Basic connection failed: ${error.message}`);
        console.log('❌ Basic connection failed:', error.message);
    }
    
    // Test 2: Health endpoint
    try {
        console.log('Test 2: Health endpoint');
        const response = await fetch(`${API_BASE}/health`, { mode: 'cors' });
        if (response.ok) {
            const data = await response.text();
            results.push(`✅ Health endpoint: ${response.status} - ${data}`);
        } else {
            results.push(`⚠️ Health endpoint: ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        results.push(`❌ Health endpoint failed: ${error.message}`);
    }
    
    // Test 3: Search endpoint
    try {
        console.log('Test 3: Search endpoint');
        const response = await fetch(`${API_BASE}/api/search?q=test`, { mode: 'cors' });
        if (response.ok) {
            const data = await response.json();
            results.push(`✅ Search endpoint works: Found ${JSON.stringify(data).length} chars of data`);
            console.log('Search endpoint response:', data);
        } else {
            const errorText = await response.text();
            results.push(`❌ Search endpoint error: ${response.status} - ${errorText}`);
        }
    } catch (error) {
        results.push(`❌ Search endpoint failed: ${error.message}`);
    }
    
    // Show results
    alert('Backend Test Results:\n\n' + results.join('\n\n'));
    console.log('🧪 Test completed:', results);
}

// Enhanced error display
function displayBackendError(customMessage = null) {
    const errorMessage = customMessage || `Cannot connect to the search API at ${API_BASE}`;
    
    document.getElementById('resultsSection').innerHTML = `
        <div class="loading">
            <h3>⚠️ Backend Connection Error</h3>
            <p>${errorMessage}</p>
            <div style="text-align: left; max-width: 500px; margin: 20px auto; padding: 15px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #dc3545;">
                <h4>🔧 Troubleshooting Steps:</h4>
                <ol>
                    <li><strong>Check Python backend:</strong> Is it running? What port?</li>
                    <li><strong>Check API_BASE:</strong> Currently set to <code>${API_BASE}</code></li>
                    <li><strong>Check CORS:</strong> Does your Flask app have CORS enabled?</li>
                    <li><strong>Check endpoints:</strong> Does <code>/api/search</code> exist in your Python code?</li>
                </ol>
                <p><strong>Common fixes:</strong></p>
                <ul>
                    <li>Start your Python server: <code>python app.py</code></li>
                    <li>Install CORS: <code>pip install flask-cors</code></li>
                    <li>Add to Python: <code>from flask_cors import CORS; CORS(app)</code></li>
                </ul>
            </div>
            <button onclick="testBackendConnection()" style="margin-top: 15px; padding: 12px 24px; background: #0a66c2; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                🧪 Run Detailed Backend Test
            </button>
            <button onclick="showPythonExample()" style="margin-left: 10px; padding: 12px 24px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">
                📋 Show Python Example
            </button>
        </div>
    `;
}

// Show Python backend example
function showPythonExample() {
    const pythonCode = `
# Example Python Flask backend (app.py)
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/')
def home():
    return "Backend is running!"

@app.route('/health')
def health():
    return "OK"

@app.route('/api/search', methods=['GET', 'POST'])
def search():
    if request.method == 'GET':
        query = request.args.get('q', '')
    else:
        data = request.get_json()
        query = data.get('q') or data.get('query') or data.get('search_term', '')
    
    # Your search logic here
    results = [
        {
            "id": "1",
            "title": f"Sample result for: {query}",
            "document": "sample.pdf",
            "page": 1,
            "confidence": 95,
            "snippet": f"This is a sample result for '{query}'"
        }
    ]
    
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True, port=5001)  # Make sure port matches API_BASE
    `;
    
    alert('Python Backend Example (copy this code):\n\n' + pythonCode);
    console.log('Python example:', pythonCode);
}

// Rest of your existing functions...
function displayResults(results) {
    console.log('📊 Displaying results:', results);
    
    if (!results || results.length === 0) {
        document.getElementById('resultsSection').innerHTML = `
            <div class="loading">
                <h3>📭 No results found</h3>
                <p>Try adjusting your search terms or check if documents are uploaded</p>
                <details style="margin-top: 15px; text-align: left; max-width: 500px; margin-left: auto; margin-right: auto;">
                    <summary style="cursor: pointer; font-weight: bold;">🔧 Troubleshooting</summary>
                    <ul>
                        <li>Check that your documents are indexed</li>
                        <li>Try broader search terms</li>
                        <li>Verify your backend search endpoint is working</li>
                        <li>Check browser console for errors</li>
                    </ul>
                    <button onclick="testBackendConnection()" style="margin-top: 10px; padding: 6px 12px; background: #0a66c2; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        Test Backend
                    </button>
                </details>
            </div>
        `;
        return;
    }

    const filteredResults = currentFilter === 'all' 
        ? results 
        : results.filter(r => r.type === currentFilter);

    const resultsHTML = filteredResults.length > 0 
        ? filteredResults.map(result => createResultHTML(result)).join('')
        : '<div class="loading"><h3>No results found for current filter</h3><p>Try changing the filter or adjusting your search terms</p></div>';

    document.getElementById('resultsSection').innerHTML = resultsHTML;
}

function showLoading() {
    document.getElementById('resultsSection').innerHTML = `
        <div class="loading">
            <div class="loading-spinner"></div>
            <h3>🔍 Searching documents...</h3>
            <p>Analyzing your query and finding relevant information</p>
        </div>
    `;
}

function createResultHTML(result) {
    // Handle missing fields gracefully
    const title = result.title || result.name || 'Untitled Document';
    const document = result.document || result.filename || result.file || 'Unknown File';
    const page = result.page || result.page_number || 1;
    const confidence = result.confidence || result.score || 0;
    const snippet = result.snippet || result.content || result.text || 'No preview available';
    const lastUpdated = result.lastUpdated || result.updated || result.date || new Date().toISOString();
    
    return `
        <div class="result-item">
            <div class="result-header">
                <div class="result-title" onclick="viewPDF('${document}', ${page})">${title}</div>
                <div class="result-meta">
                    <span>📄 ${document}</span>
                    <span>Page ${page}</span>
                    <span>${Math.round(confidence)}% match</span>
                    <span>Updated ${new Date(lastUpdated).toLocaleDateString()}</span>
                </div>
            </div>
            <div class="result-snippet">${snippet}</div>
            <div class="result-actions">
                <button class="action-btn view-pdf" onclick="viewPDF('${document}', ${page})">
                    📄 View PDF
                </button>
                <button class="action-btn copy-link" onclick="copyLink('${document}', ${page})">
                    🔗 Copy Link
                </button>
            </div>
        </div>
    `;
}

function highlightSearchTerms(text, query) {
    if (!query || !text) return text;
    
    const terms = query.toLowerCase().split(' ').filter(term => term.length > 2);
    let highlightedText = text;
    
    terms.forEach(term => {
        const regex = new RegExp(`(${term})`, 'gi');
        highlightedText = highlightedText.replace(regex, '<span class="highlight">$1</span>');
    });
    
    return highlightedText;
}

// Keep your existing event listeners and other functions...
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                performSearch();
            }
        });
        searchInput.focus(); // Auto-focus
    }
    
    // Filter buttons
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
    
    console.log('🚀 Search functionality initialized');
    console.log('📡 API_BASE:', API_BASE);
});

