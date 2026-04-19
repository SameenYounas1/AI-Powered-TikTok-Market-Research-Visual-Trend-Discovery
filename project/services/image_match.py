"""
ImageMatcher — Reverse Image Search for TikTok Trend Bot
---------------------------------------------------------
Pipeline:  uploaded image
           → Gemini 1.5 Flash (free, cloud, no local AI)
           → clothing description
           → Apify clockworks~free-tiktok-scraper
           → ranked video results

Keys needed (both free):
  Gemini  → https://aistudio.google.com/app/apikey
  Apify   → https://apify.com  (free tier is enough)

Drop-in usage in your Streamlit app:
    from image_matcher import ImageMatcher
    results, query, error = ImageMatcher.get_ranked_matches(
        uploaded_file,          # st.file_uploader result
        apify_token="apify_api_...",
        gemini_key="AIzaSy...",  # optional but strongly recommended
    )
    # results → list of dicts (see _rank_items for keys)
    # query   → the AI-generated description string used to search
    # error   → "" on success, human-readable message on failure
"""

import base64
import io
import time

import requests
from PIL import Image


# ── Apify actor IDs ────────────────────────────────────────────────────────
_ACTOR_PRIMARY  = "clockworks~free-tiktok-scraper"
_ACTOR_FALLBACK = "clockworks~tiktok-scraper"

# ── Gemini 1.5 Flash (free tier: 15 req/min) ──────────────────────────────
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-1.5-flash:generateContent"
)

# ── Buyer-intent keywords to detect in video captions ────────────────────
_BUYER_KEYWORDS = [
    "where is the dress from", "link please", "where to buy", "what brand",
    "source?", "i need this", "outfit link", "shop link", "where did you get",
    "need this dress", "buying this", "omg where", "drop the link",
    "what is this", "can you link", "this is so cute where",
]


class ImageMatcher:

    # ── PUBLIC ENTRY POINT ─────────────────────────────────────────────────
    @staticmethod
    def get_ranked_matches(
        uploaded_file,
        apify_token: str,
        gemini_key: str = "",
    ) -> tuple[list[dict], str, str]:
        """
        Full pipeline: image → description → TikTok search → ranked results.

        Parameters
        ----------
        uploaded_file : file-like object from st.file_uploader
        apify_token   : Apify API token (required)
        gemini_key    : Google Gemini API key (optional but recommended)

        Returns
        -------
        (results, query_used, error_message)
        results       → list[dict] sorted by match score, [] on failure
        query_used    → the search string sent to TikTok
        error_message → "" on success, human-readable string on failure
        """
        if not uploaded_file:
            return [], "", "No file provided."
        if not apify_token or not apify_token.strip():
            return [], "", "Apify token is required."

        # ── 1. Read & normalise image ──────────────────────────────────────
        image_bytes, err = ImageMatcher._read_image(uploaded_file)
        if err:
            return [], "", err

        # ── 2. Describe image (Gemini) ─────────────────────────────────────
        description = ImageMatcher._describe_image(image_bytes, gemini_key)

        # Fallback: use filename if Gemini fails or key not provided
        if not description:
            raw = uploaded_file.name.rsplit(".", 1)[0]
            description = raw.replace("_", " ").replace("-", " ").strip()
            if len(description) < 4:
                description = "women fashion dress outfit"

        search_query = f"{description} fashion dress outfit"

        # ── 3. Search TikTok via Apify ─────────────────────────────────────
        raw_items = ImageMatcher._apify_search(search_query, apify_token)

        # ── 4. Rank & return ───────────────────────────────────────────────
        if not raw_items:
            return [], search_query, (
                "Apify returned no results. Possible reasons: "
                "(1) no remaining Apify credits, "
                "(2) TikTok blocked this query, "
                "(3) actor temporarily unavailable. "
                "Check your Apify dashboard and try again."
            )

        results = ImageMatcher._rank_items(raw_items, description)
        return results, search_query, ""

    # ── STEP 1: READ IMAGE ─────────────────────────────────────────────────
    @staticmethod
    def _read_image(uploaded_file) -> tuple[bytes, str]:
        """
        Read the uploaded file and return JPEG bytes.
        Returns (bytes, "") on success or (b"", error_string) on failure.
        """
        try:
            uploaded_file.seek(0)
            raw = uploaded_file.read()
        except Exception as e:
            return b"", f"Could not read file: {e}"

        if not raw:
            return b"", "Uploaded file is empty. Please re-upload."

        try:
            pil_img = Image.open(io.BytesIO(raw)).convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85)
            return buf.getvalue(), ""
        except Exception as e:
            return b"", f"Could not decode image: {e}"

    # ── STEP 2: GEMINI VISION ─────────────────────────────────────────────
    @staticmethod
    def _describe_image(image_bytes: bytes, gemini_key: str) -> str:
        """
        Call Gemini 1.5 Flash to get a short clothing description.
        Returns "" on any failure so caller can use filename fallback.
        """
        if not gemini_key or not gemini_key.strip():
            return ""

        payload = {
            "contents": [{
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode("utf-8"),
                        }
                    },
                    {
                        "text": (
                            "Describe this clothing item in 5-8 words for a TikTok search. "
                            "Focus on color, style, fabric, garment type. "
                            "Examples: 'white floral cottagecore midi dress', "
                            "'black satin slip mini dress', "
                            "'blue linen wide-leg trousers'. "
                            "Return ONLY the description — no extra words or punctuation."
                        )
                    },
                ]
            }]
        }

        try:
            resp = requests.post(
                f"{_GEMINI_URL}?key={gemini_key.strip()}",
                json=payload,
                timeout=20,
            )
            data = resp.json()
            text = (
                data
                .get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
                .strip('"')
            )
            # Keep first line only, cap at 80 chars
            return text.split("\n")[0][:80]
        except Exception:
            return ""

    # ── STEP 3: APIFY TIKTOK SEARCH ───────────────────────────────────────
    @staticmethod
    def _apify_search(search_query: str, apify_token: str, max_results: int = 15) -> list[dict]:
        """
        Trigger Apify TikTok scraper, poll until done, return raw items.
        Tries primary actor first, falls back to secondary.
        Returns [] if both actors fail.
        """
        token   = apify_token.strip()
        headers = {"Content-Type": "application/json"}
        payload = {
            "searchQueries":      [search_query],
            "searchSection":      "/video",
            "resultsPerPage":     max_results,
            "maxProfilesPerQuery": max_results,
            "maxRequestRetries":  3,
        }

        for actor_id in [_ACTOR_PRIMARY, _ACTOR_FALLBACK]:
            try:
                # waitForFinish=60 → Apify holds the HTTP connection up to 60 s
                run_url = (
                    f"https://api.apify.com/v2/acts/{actor_id}/runs"
                    f"?token={token}&waitForFinish=60"
                )
                run_resp = requests.post(run_url, json=payload,
                                         headers=headers, timeout=90)
                run_data = ImageMatcher._safe_json(run_resp)
                if not run_data:
                    continue

                # Apify wraps response in {"data": {...}} — handle both shapes
                info       = run_data.get("data") or run_data
                run_id     = info.get("id")
                dataset_id = info.get("defaultDatasetId")
                status     = info.get("status", "")

                if not run_id or not dataset_id:
                    continue

                # Extra polling when waitForFinish wasn't enough
                if status not in ("SUCCEEDED", "FINISHED"):
                    for _ in range(15):          # up to 60 s extra
                        time.sleep(4)
                        s = ImageMatcher._safe_json(
                            requests.get(
                                f"https://api.apify.com/v2/actor-runs/{run_id}"
                                f"?token={token}",
                                timeout=15,
                            )
                        )
                        if not s:
                            break
                        status = (s.get("data") or s).get("status", "")
                        if status in ("SUCCEEDED", "FINISHED", "FAILED", "ABORTED"):
                            break

                if status not in ("SUCCEEDED", "FINISHED"):
                    continue

                # Fetch dataset
                items_resp = requests.get(
                    f"https://api.apify.com/v2/datasets/{dataset_id}/items"
                    f"?token={token}&format=json&limit={max_results}",
                    timeout=20,
                )
                items = ImageMatcher._safe_json(items_resp)

                if isinstance(items, list) and items:
                    return items
                if isinstance(items, dict):
                    inner = items.get("items") or items.get("data") or []
                    if inner:
                        return inner

            except requests.exceptions.Timeout:
                continue
            except Exception:
                continue

        return []

    # ── STEP 4: RANK RESULTS ──────────────────────────────────────────────
    @staticmethod
    def _rank_items(raw_items: list[dict], description: str) -> list[dict]:
        """
        Convert raw Apify items into clean dicts scored by relevance.

        Result dict keys:
            creator, description, views, likes, comments, shares,
            post_date, url, score (0.0–1.0), has_intent, keyword_hits
        """
        keywords = [w.lower() for w in description.split() if len(w) > 2]
        results  = []

        for item in raw_items:
            # Field names vary between Apify actor versions — cover all variants
            url = (item.get("webVideoUrl") or item.get("videoUrl")
                   or item.get("url") or "")
            if not url:
                continue  # skip items with no playable link

            text    = (item.get("text") or item.get("desc")
                       or item.get("description") or "")
            author  = item.get("authorMeta") or item.get("author") or {}
            creator = (
                (author.get("uniqueId") or author.get("name"))
                if isinstance(author, dict)
                else str(author)
            ) or item.get("uniqueId") or "tiktok_user"

            views    = int(item.get("playCount")    or item.get("views")    or 0)
            likes    = int(item.get("diggCount")    or item.get("likes")    or 0)
            comments = int(item.get("commentCount") or item.get("comments") or 0)
            shares   = int(item.get("shareCount")   or item.get("shares")   or 0)
            created  = str(item.get("createTimeISO") or item.get("createTime") or "")

            # Score = keyword overlap ratio, mapped to 0.70–0.99
            text_lower = text.lower()
            overlap    = sum(1 for kw in keywords if kw in text_lower)
            score      = min(0.70 + (overlap / max(len(keywords), 1)) * 0.28, 0.99)
            if views > 500_000:
                score = min(score + 0.02, 0.99)

            buyer_hits = [kw for kw in _BUYER_KEYWORDS if kw in text_lower]

            results.append({
                "creator":      "@" + creator.lstrip("@"),
                "description":  text[:120] + ("..." if len(text) > 120 else ""),
                "views":        views,
                "likes":        likes,
                "comments":     comments,
                "shares":       shares,
                "post_date":    created[:10] if created else "—",
                "url":          url,
                "score":        round(score, 4),
                "has_intent":   len(buyer_hits) > 0,
                "keyword_hits": buyer_hits[:3],
            })

        return sorted(results, key=lambda x: x["score"], reverse=True)

    # ── UTILITY ───────────────────────────────────────────────────────────
    @staticmethod
    def _safe_json(response):
        """Parse response JSON without ever raising."""
        try:
            return response.json()
        except Exception:
            return None