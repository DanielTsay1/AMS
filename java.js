        // Navigation functionality
        function showSection(section) {
            // Update nav links
            document.querySelectorAll('.nav-link').forEach(link => {
                link.classList.remove('active');
            });
            event.target.classList.add('active');

            // Show/hide sections
            if (section === 'upload') {
                document.getElementById('uploadSection').classList.add('active');
                document.getElementById('searchSection').style.display = 'none';
                document.getElementById('contentTitle').textContent = 'Document Upload';
                document.getElementById('contentSubtitle').textContent = 'Upload PDF documents to make them searchable';
                document.getElementById('fileList').style.display = 'block';
            } else {
                document.getElementById('uploadSection').classList.remove('active');
                document.getElementById('searchSection').style.display = 'block';
                document.getElementById('contentTitle').textContent = 'Document Search';
                document.getElementById('contentSubtitle').textContent = 'Find information across your company\'s document library';
            }
        }

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

        function handleFiles(files) {
            Array.from(files).forEach(file => {
                if (file.type === 'application/pdf') {
                    // In a real implementation, you would upload the file to your server
                    console.log('Uploading file:', file.name);
                    // Show upload progress, then add to file list
                    addFileToList(file);
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
            
            // Simulate processing completion
            setTimeout(() => {
                const status = fileItem.querySelector('.file-status');
                status.textContent = 'Indexed';
                status.className = 'file-status status-complete';
            }, 3000);
        }
        let searchResults = [];

        // Sample data for demonstration
        const sampleResults = [
            {
                title: "Employee Handbook - Remote Work Policy",
                snippet: "Remote work is permitted for all eligible employees with manager approval. Employees must maintain regular communication and meet all productivity standards while working from home.",
                document: "Employee_Handbook_2024.pdf",
                page: 23,
                confidence: 95,
                type: "policy",
                lastUpdated: "2024-01-15"
            },
            {
                title: "IT Security Guidelines - Password Requirements",
                snippet: "All passwords must be at least 12 characters long and include a combination of uppercase, lowercase, numbers, and special characters. Passwords should be changed every 90 days.",
                document: "IT_Security_Manual.pdf",
                page: 8,
                confidence: 92,
                type: "manual",
                lastUpdated: "2024-02-01"
            },
            {
                title: "Vacation Policy FAQ",
                snippet: "Vacation requests should be submitted at least 2 weeks in advance through the HR portal. Approval is subject to business needs and team coverage.",
                document: "HR_FAQ_2024.pdf",
                page: 15,
                confidence: 88,
                type: "faq",
                lastUpdated: "2024-01-10"
            }
        ];

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

        // Search input enter key
        document.getElementById('searchInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                performSearch();
            }
        });

        // Nav search functionality
        document.getElementById('navSearchInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                document.getElementById('searchInput').value = this.value;
                performSearch();
            }
        });

        function performSearch() {
            const query = document.getElementById('searchInput').value.trim();
            if (!query) return;

            showLoading();
            
            // Simulate API call delay
            setTimeout(() => {
                searchResults = sampleResults.map(result => ({
                    ...result,
                    snippet: highlightSearchTerms(result.snippet, query)
                }));
                displayResults(searchResults);
            }, 1200);
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

        function displayResults(results) {
            const filteredResults = currentFilter === 'all' 
                ? results 
                : results.filter(r => r.type === currentFilter);

            const resultsHTML = filteredResults.length > 0 
                ? filteredResults.map(result => createResultHTML(result)).join('')
                : '<div class="loading"><h3>No results found</h3><p>Try adjusting your search terms or filters</p></div>';

            document.getElementById('resultsSection').innerHTML = resultsHTML;
        }

        function createResultHTML(result) {
            return `
                <div class="result-item">
                    <div class="result-header">
                        <div class="result-title" onclick="viewPDF('${result.document}', ${result.page})">${result.title}</div>
                        <div class="result-meta">
                            <span>📄 ${result.document}</span>
                            <span>Page ${result.page}</span>
                            <span>${result.confidence}% match</span>
                            <span>Updated ${new Date(result.lastUpdated).toLocaleDateString()}</span>
                        </div>
                    </div>
                    <div class="result-snippet">${result.snippet}</div>
                    <div class="result-actions">
                        <button class="action-btn view-pdf" onclick="viewPDF('${result.document}', ${result.page})">
                            View PDF
                        </button>
                        <button class="action-btn copy-link" onclick="copyLink('${result.document}', ${result.page})">
                            Copy Link
                        </button>
                    </div>
                </div>
            `;
        }

        function highlightSearchTerms(text, query) {
            const terms = query.toLowerCase().split(' ').filter(term => term.length > 2);
            let highlightedText = text;
            
            terms.forEach(term => {
                const regex = new RegExp(`(${term})`, 'gi');
                highlightedText = highlightedText.replace(regex, '<span class="highlight">$1</span>');
            });
            
            return highlightedText;
        }

        function viewPDF(document, page) {
            alert(`Opening ${document} at page ${page}`);
        }

        function copyLink(document, page) {
            const link = `${window.location.origin}/documents/${document}#page=${page}`;
            navigator.clipboard.writeText(link).then(() => {
                event.target.textContent = 'Copied!';
                setTimeout(() => {
                    event.target.textContent = 'Copy Link';
                }, 2000);
            });
        }

        function setSearch(query) {
            document.getElementById('searchInput').value = query;
            document.getElementById('navSearchInput').value = query;
            performSearch();
        }

        // Auto-focus search input
        document.getElementById('searchInput').focus();