import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# API Configuration
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "apify_api_dnMdXey1suNihTQbGrOQRDlmPI04pu4jVAZi")
ACTOR_ID = "clockworks/tiktok-scraper"

# Configurable Intent Keywords
INTENT_KEYWORDS = ["where", "link", "dress", "brand", "buy", "shop", "from", "price", "store"]

# UI Constants
THEME_COLOR = "#fe2c55"
BG_COLOR = "#080808"