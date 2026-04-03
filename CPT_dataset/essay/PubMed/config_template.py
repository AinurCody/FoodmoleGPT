"""
PMC Downloader Configuration for FoodmoleGPT
=============================================
Configuration settings for downloading food science articles from PubMed Central.
"""

# =============================================================================
# NCBI API Settings
# =============================================================================

# Your email (REQUIRED by NCBI)
NCBI_EMAIL = "YOUR_EMAIL_HERE"

# NCBI API Key (Optional but recommended)
NCBI_API_KEY = "YOUR_API_KEY_HERE"

# Tool identifier for NCBI tracking
NCBI_TOOL = "FoodmoleGPT-Downloader"


# =============================================================================
# Search Configuration
# =============================================================================

# Food science related MeSH terms and keywords
# These will be combined with OR operator
SEARCH_TERMS = [
    # Core food science terms
    '"Food Science"[MeSH]',
    '"Food Chemistry"[MeSH]',
    '"Food Analysis"[MeSH]',
    '"Food Preservation"[MeSH]',
    '"Food Technology"[MeSH]',
    
    # Food safety and quality
    '"Food Safety"[MeSH]',
    '"Food Contamination"[MeSH]',
    '"Food Microbiology"[MeSH]',
    '"Foodborne Diseases"[MeSH]',
    '"Food Additives"[MeSH]',
    
    # Nutrition related
    '"Nutrients"[MeSH]',
    '"Nutritive Value"[MeSH]',
    '"Food, Functional"[MeSH]',
    '"Dietary Supplements"[MeSH]',
    
    # Food processing
    '"Food Handling"[MeSH]',
    '"Cooking"[MeSH]',
    '"Fermentation"[MeSH]',
    '"Food Packaging"[MeSH]',
    
    # Specific food categories
    '"Beverages"[MeSH]',
    '"Dairy Products"[MeSH]',
    '"Meat"[MeSH]',
    '"Seafood"[MeSH]',
    '"Vegetables"[MeSH]',
    '"Fruit"[MeSH]',
    '"Cereals"[MeSH]',
]

# Additional filters
# Only open access articles (required for full-text download)
OPEN_ACCESS_FILTER = "open access[filter]"

# Date range filter (optional, format: YYYY/MM/DD)
# Set to None to include all dates
DATE_FROM = None  # e.g., "2010/01/01"
DATE_TO = None    # e.g., "2024/12/31"


# =============================================================================
# Download Settings
# =============================================================================

# Maximum number of articles to download (set to None for no limit)
MAX_ARTICLES = None

# Batch size for each API request (max 500 for efetch)
BATCH_SIZE = 100

# Delay between requests in seconds
# Without API key: ~0.34s (3 req/s)
# With API key: ~0.1s (10 req/s)
REQUEST_DELAY = 0.12  # With API key: 10 req/s allowed

# Number of retry attempts for failed requests
MAX_RETRIES = 3

# Timeout for each request in seconds
REQUEST_TIMEOUT = 60


# =============================================================================
# Output Settings
# =============================================================================

# Base directory for downloads (relative to script location)
OUTPUT_DIR = "data"

# Subdirectories
XML_DIR = "xml"           # Raw XML files
METADATA_DIR = "metadata" # Article metadata JSON
LOGS_DIR = "logs"         # Log files

# Progress file for resuming downloads
PROGRESS_FILE = "download_progress.json"

# Log file name
LOG_FILE = "download.log"
