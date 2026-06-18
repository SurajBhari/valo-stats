import os
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.henrikdev.xyz"
API_KEY = os.getenv("HENRIK_API_KEY", "")
TWO_YEARS_SECONDS = 730 * 24 * 3600  # 63072000
PAGE_SIZE = 20
RATE_LIMIT_THRESHOLD = 2
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
REGIONS = ["na", "eu", "ap", "kr", "latam", "br"]
