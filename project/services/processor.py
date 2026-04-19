from utils.config import INTENT_KEYWORDS

class DataProcessor:
    @staticmethod
    def analyze_trends(raw_data, min_views):
        if not raw_data:
            return []

        processed = []
        # Requirement: Detect specific intent keywords like "where is the dress from"
        high_intent_phrases = ["where", "link", "buy", "from", "brand", "store", "dress"]

        for item in raw_data:
            views = item.get("playCount", 0)
            if views < min_views:
                continue
            
            # Logic for "High Intent" Badge
            desc = str(item.get("text", "")).lower()
            # We also check comments if the API provides them
            is_high_intent = any(word in desc for word in high_intent_phrases)

            processed.append({
                "Creator": item.get("authorMeta", {}).get("name", "Unknown"),
                "Views": views,
                "Likes": item.get("diggCount", 0),
                "Comments": item.get("commentCount", 0),
                "Date": item.get("createTimeISO", "N/A")[:10],
                "URL": item.get("webVideoUrl"),
                "EmbedURL": item.get("videoMeta", {}).get("downloadAddr", ""), # For in-app player
                "Description": item.get("text", ""),
                "High Intent": is_high_intent
            })
        return processed