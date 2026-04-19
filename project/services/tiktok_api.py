import streamlit as st
from apify_client import ApifyClient
from utils.config import APIFY_TOKEN, ACTOR_ID

class TikTokService:
    def __init__(self):
        self.client = ApifyClient(APIFY_TOKEN)

    @st.cache_data(show_spinner=False)
    def fetch_data(_self, query, mode, limit):
        """Fetches data with caching to prevent redundant API calls."""
        try:
            run_input = {
                "searchQueries": [query],
                "searchType": mode.lower(),
                "resultsPerPage": limit
            }
            # Execute Actor
            run = _self.client.actor(ACTOR_ID).call(run_input=run_input)
            
            # Fetch Dataset
            return list(_self.client.dataset(run["defaultDatasetId"]).iterate_items())
        except Exception as e:
            st.error(f"Apify Connection Failed: {str(e)}")
            return None