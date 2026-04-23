import os
import json
import httpx
import asyncio
import datetime
import difflib
import re
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from notion_client import AsyncClient
from tavily import TavilyClient
from openai import OpenAI
from dotenv import load_dotenv
from backend.clarification.clarifier import QueryClarifier

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Absolute path enforcement for local environments
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_base_dir, ".env")
load_dotenv(_env_path)

class TravelAgent:
    def __init__(self, notion_token: str):
        self.notion = AsyncClient(auth=notion_token)
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        self.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.clarifier = QueryClarifier()
        self.model = "gpt-4o"
        self.notion_headers = {
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        # Discovery Registry (Now used as a hint, not a blocker)
        self.db_registry = {
            "Cities": os.getenv("NOTION_CITIES_DB_ID"),
            "Hotels": os.getenv("NOTION_HOTELS_DB_ID"),
            "Restaurants": os.getenv("NOTION_RESTAURANTS_DB_ID"),
            "Itinerary": os.getenv("NOTION_ITINERARY_DB_ID")
        }
        self.db_registry = {k: v for k, v in self.db_registry.items() if v}

    def _get_now_str(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    async def _query_database(self, db_id: str, filter_obj: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Manual HTTP query to bypass SDK missing 'query' method or 404 errors."""
        url = f"https://api.notion.com/v1/databases/{db_id}/query"
        async with httpx.AsyncClient() as client:
            payload = {}
            if filter_obj: payload["filter"] = filter_obj
            resp = await client.post(url, headers=self.notion_headers, json=payload, timeout=20.0)
            if resp.status_code != 200:
                return {"results": []}
            return resp.json()

    async def find_master_databases(self):
        """Flexible naming discovery for common travel databases."""
        try:
            search_res = await self.notion.search()
            for obj in search_res.get("results", []):
                if obj.get("object") == "database":
                    title = "".join([t.get("plain_text", "") for t in obj.get("title", [])])
                    for kw in ["Cities", "Hotels", "Restaurants", "Itinerary", "Venues", "Beaches", "Sights"]:
                        if kw.lower() in title.lower() and kw not in self.db_registry:
                            self.db_registry[kw] = obj["id"]
        except: pass

    def _sanitize_link(self, lnk: Any) -> Optional[str]:
        if not lnk or not isinstance(lnk, str): return None
        import re
        # Link Sniper: Extracts the first valid http/https URL from a string
        match = re.search(r'https?://[^\s<>"]+', lnk)
        return match.group(0) if match else None

    def _parse_properties(self, props: Dict[str, Any]) -> Dict[str, Any]:
        clean = {}
        for name, data in props.items():
            ptype = data.get("type")
            if ptype == "title": clean[name] = "".join([t.get("plain_text", "") for t in data.get("title", [])])
            elif ptype == "rich_text": clean[name] = "".join([t.get("plain_text", "") for t in data.get("rich_text", [])])
            elif ptype == "select": clean[name] = data.get("select", {}).get("name") if data.get("select") else None
            elif ptype == "multi_select": clean[name] = [s.get("name") for s in data.get("multi_select", [])]
            elif ptype == "number": clean[name] = data.get("number")
            elif ptype == "relation": clean[name] = [r.get("id") for r in data.get("relation", [])]
            elif ptype == "url": clean[name] = data.get("url")
            elif ptype == "date": clean[name] = data.get("date", {}).get("start") if data.get("date") else None
            elif ptype == "files": 
                urls = []
                for f in data.get("files", []):
                    url = f.get("file", {}).get("url") or f.get("external", {}).get("url")
                    if url: urls.append(url)
                if urls:
                    clean[name] = urls[0] # Primary
                    clean[f"{name}_assets"] = urls # All assets
        return clean

    async def get_row_body_content(self, page_id: str) -> str:
        text_content = []
        try:
            results = await self.notion.blocks.children.list(block_id=page_id)
            for block in results.get("results", []):
                b_type = block.get("type", "unsupported")
                if b_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item"]:
                    rich_text = block.get(b_type, {}).get("rich_text", [])
                    text_content.append("".join([t.get("plain_text", "") for t in rich_text]))
        except: pass
        return "\n".join(text_content)

    async def discover_hierarchy(self, query: str) -> Dict[str, Any]:
        """Dual-Track Discovery: Scans hardcoded Databases FIRST, then falls back to Pages."""
        discovery_results = {"city_info": {}, "details": {}, "sources": [], "error": None}
        
        # Identity Extraction
        system_id = "Extract Target Location (City or Country). JSON: {'entity': '...'}"
        try:
            res = self.openai.chat.completions.create(model="gpt-4o-mini", response_format={"type": "json_object"}, messages=[{"role": "system", "content": system_id}, {"role": "user", "content": query}])
            loc_name = json.loads(res.choices[0].message.content).get("entity", query)
        except: loc_name = query

        logger.info(f"DUAL-TRACK DISCOVERY: '{loc_name}'")
        found_item_ids = set()
        
        # --- TRACK 1: DATABASE SCAN (High Precision) ---
        # Querying the Cities DB for a direct match
        cities_db_id = self.db_registry.get("Cities")
        if cities_db_id:
            logger.info(f"Querying Cities DB: {cities_db_id}")
            db_res = await self._query_database(cities_db_id)
            clean_target = loc_name.strip().lower()
            
            matching_city_rows = []
            for row in db_res.get("results", []):
                props = self._parse_properties(row["properties"])
                if any(clean_target in str(v).lower() for v in props.values()):
                    matching_city_rows.append({"id": row["id"], "props": props, "url": row.get("url")})
            
            if matching_city_rows:
                city = matching_city_rows[0]
                city_names = [c["props"].get("Name", loc_name).lower() for c in matching_city_rows]
                city_ids = [c["id"].replace("-", "") for c in matching_city_rows]
                
                discovery_results["city_info"] = {"id": city["id"], "name": city["props"].get("Name", loc_name), "content": await self.get_row_body_content(city["id"]), "url": city.get("url")}
                discovery_results["sources"].append({"title": f"City: {city['props'].get('Name', loc_name)}", "url": city.get("url"), "type": "Notion (DB)"})
                logger.info(f"DB City Match: {city['props'].get('Name')}")
                
                # Relational Scan: Scan Hotels, Restaurants, etc. for these City IDs/Names
                for cat, db_id in self.db_registry.items():
                    if cat == "Cities": continue
                    db_res = await self._query_database(db_id)
                    for row in db_res.get("results", []):
                        props = self._parse_properties(row["properties"])
                        # AGGRESSIVE MATCH: Check IDs (relations) AND Text Names (tags/text)
                        is_match = False
                        p_val_str = " ".join([str(v).lower() for v in props.values()]).replace("-", "")
                        if any(cid in p_val_str for cid in city_ids) or any(cn in p_val_str for cn in city_names):
                            is_match = True

                        if is_match and row["id"] not in found_item_ids:
                            props["_page_content"] = await self.get_row_body_content(row["id"])
                            if cat not in discovery_results["details"]: discovery_results["details"][cat] = []
                            discovery_results["details"][cat].append(props)
                            discovery_results["sources"].append({"title": props.get("Name", "Untitled"), "url": row.get("url"), "type": "Notion (DB)"})
                            found_item_ids.add(row["id"])
                            logger.info(f"Found {cat} in DB: {props.get('Name')}")

        # --- TRACK 2: PAGE SEARCH FALLBACK (Broad Discovery) ---
        logger.info(f"Running Page Search Fallback...")
        try:
            search_res = await self.notion.search(query=loc_name)
            for p in search_res.get("results", []):
                if p["id"] in [c["id"] for c in discovery_results.get("city_info", {}).values() if isinstance(c, str)]: continue
                if p["id"] in found_item_ids: continue
                
                title = ""
                if p.get("object") == "page":
                    props = p.get("properties", {})
                    title = "".join([t.get("plain_text", "") for p_v in props.values() if p_v.get("type") == "title" for t in p_v.get("title", [])])
                elif p.get("object") == "database":
                    title = "".join([t.get("plain_text", "") for t in p.get("title", [])])
                
                if not title: continue
                clean_title = title.lower()
                clean_loc = loc_name.lower()
                
                if clean_loc in clean_title:
                    cat = "Venues"
                    if any(k in clean_title for k in ["hotel", "stay", "resort"]): cat = "Hotels"
                    elif any(k in clean_title for k in ["restaurant", "cafe", "food"]): cat = "Restaurants"
                    
                    if not discovery_results["city_info"] and clean_title == clean_loc:
                        discovery_results["city_info"] = {"id": p["id"], "name": title, "content": await self.get_row_body_content(p["id"]), "url": p.get("url")}
                        discovery_results["sources"].append({"title": f"City: {title}", "url": p.get("url"), "type": "Notion (Page)"})
                        logger.info(f"Page City Match: {title}")
                    else:
                        item_props = self._parse_properties(p.get("properties", {}))
                        item_props["Name"] = title
                        item_props["_page_content"] = await self.get_row_body_content(p["id"])
                        if cat not in discovery_results["details"]: discovery_results["details"][cat] = []
                        discovery_results["details"][cat].append(item_props)
                        discovery_results["sources"].append({"title": title, "url": p.get("url"), "type": "Notion (Page)"})
                        found_item_ids.add(p["id"])
                        logger.info(f"Found {cat} via Page: {title}")
        except: pass

        return discovery_results

    async def run_query_stream(self, user_query: str, history: List[Dict[str, str]], mode: str = "Hybrid", is_confirmed: bool = False, travel_date: str = None) -> AsyncGenerator[str, None]:
        # Domain Context for Clarifier
        travel_rules = """
--- TRAVEL DOMAIN CLARIFICATION RULES ---
You are an expert travel planning assistant and query analyst.
Your ONLY job is to analyze the user's trip query and gather the necessary variables to make the query fully self-contained and answerable with high precision.

[FEW-SHOT EXAMPLES]
User: "plan a trip" -> Assistant: {"clarification_needed": true, "clarifications": [{"question": "Which destination are you planning to visit?", "example_answer": "Goa"}, {"question": "What are your travel dates or trip duration?", "example_answer": "3 days in June"}, {"question": "What type of trip are you looking for (party, relaxation, adventure)?", "example_answer": "Relaxation"}]}
User: "suggest hotels in Goa" -> Assistant: {"clarification_needed": true, "clarifications": [{"question": "What is your budget per night?", "example_answer": "INR 4,000-8,000"}, {"question": "How many guests?", "example_answer": "2 adults"}]}
User: "good restaurants in Goa" -> Assistant: {"clarification_needed": true, "clarifications": [{"question": "What type of cuisine?", "example_answer": "Seafood"}, {"question": "What is your budget per person?", "example_answer": "INR 1,500"}]}
User: "3 day Paris itinerary for couple under EUR 1000" -> Assistant: {"clarification_needed": false}

[TRIVIAL LOOKUP OVERRIDE]
- If the user is asking to EXCLUSIVELY view THEIR own existing data (e.g. "What are my hotels...", "Show my current restaurants...") and a City/Destination was mentioned in history:
  -> Proceed immediately.
- **EXCEPTION**: If the user uses action verbs like "Book", "Find", "Search", "Suggest", or "Plan", this is an ACTION and requires Location.

STRICT MANDATES:
- [LOCATION MANDATE]: You are FORBIDDEN from approving an ACTION query if Location is missing.
- [CITY SUFFICIENCY]: Once a major city or destination (e.g., Barcelona, Goa, Paris) is identified, THIS IS COMPLETE. Do NOT ask for specific neighborhoods, villages, or areas within that city. Proceed with finding all famous and relevant entries for the entire city.
- [BATCH CLARIFICATION]: Identify ALL missing dimensions (Location, Budget, Dates, Style, Dietary, Group) required. Return ALL found gaps simultaneously. 
- [RESTAURANT MANDATE]: If 'Restaurant', 'Food', or 'Dining' is mentioned, YOU MUST ask for 'Dietary Preference'.
- [NO EMOJIS]: DO NOT use any emojis or icons in your questions or responses. Keep it professional and textual.
---------------------------------------"""
        domain_prompts = {
            "Notion Only": f"You are a Strictly Data-Driven Personal Travel Assistant. Only Notion data matters.{travel_rules}",
            "Web Only": f"You are a Professional Web Travel Researcher investigating live events, hotels, ratings, etc.{travel_rules}",
            "Hybrid": f"You are an Advanced Hybrid Travel Intelligence Engine combining personal itineraries with live web discovery.{travel_rules}"
        }
        sys_p_base = domain_prompts.get(mode, domain_prompts["Hybrid"])

        # --- CLARIFICATION & CONSENT TIER ---
        if not is_confirmed:
            history_list = list(history)
            
            # 1. Answer Turn Detection: Was the last assistant message a checklist?
            last_asst = next((m for m in reversed(history_list) if m["role"] == "assistant"), None)
            is_answer_turn = last_asst and "perfect your itinerary" in last_asst["content"].lower()

            # 4. Formulate Standalone Query
            if is_answer_turn:
                logger.info("Q&A MAPPING MODE: Syncing answers to specific questions.")
                checklist_questions = last_asst["content"] if last_asst else ""
                
                opt_sys_p = (
                    "You are a Search Query Generator. Merge the User's Answer with the Checklist.\n"
                    "RULES:\n1. Return ONLY clean search keywords.\n2. NO BOLDING, NO LABELS, NO LISTS.\n"
                    "3. Include ONLY (City, Subject, Budget). Max 10 words."
                )
                
                standalone_res = self.openai.chat.completions.create(
                    model="gpt-4o-mini", 
                    messages=[
                        {"role": "system", "content": opt_sys_p}, 
                        {"role": "user", "content": f"QUESTIONS:\n{checklist_questions}\n\nANSWERS:\n{user_query}\n\nCONTEXT:\n{history_list[-15:]}"}
                    ]
                )
                standalone = standalone_res.choices[0].message.content.strip()
            else:
                # 2. FOLLOW-UP CLASSIFICATION for fresh/follow-up queries
                intent_res = self.openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Is the user's message a 'Follow-up' (referring to previous context) or an 'Independent' new request? Respond ONLY with 'FOLLOW_UP' or 'INDEPENDENT'."},
                        {"role": "user", "content": f"LAST 2 MESSAGES: {history_list[-2:]}\n\nCURRENT QUERY: {user_query}"}
                    ]
                )
                is_follow_up = "FOLLOW_UP" in intent_res.choices[0].message.content.upper()

                if is_follow_up:
                    # 3a. OPTIMIZER-FIRST for follow-ups
                    logger.info("FOLLOW-UP MODE: Running Optimizer first to build clean standalone.")
                    h_str = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history_list[-10:]])
                    opt_res = self.openai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are a Search Query Generator. Merge follow-up with context. Return ONLY clean keywords. NO LABELS."},
                            {"role": "user", "content": f"HISTORY:\n{h_str}\n\nUSER FOLLOW-UP: {user_query}"}
                        ]
                    )
                    clarification_input = opt_res.choices[0].message.content.strip()
                else:
                    # 3b. Fresh independent query
                    clarification_input = user_query

                if travel_date:
                    clarification_input += f" (System Note: User selected dates: {travel_date})"

                # 4. Clarifier Audit
                clarification_result = self.clarifier.evaluate_query(clarification_input, sys_p_base, history)
                logger.debug(f"Clarification Result: {json.dumps(clarification_result, indent=2)}")

                if clarification_result.get("clarification_needed"):
                    meta_dump = json.dumps({"sources": [], "entities": [], "is_clarification": True})
                    yield f"METADATA|{meta_dump}\n"
                    resp = "**Help me perfect your itinerary!**\nTo create the most accurate plan, I just need a few more details from you:\n\n"
                    for i, q in enumerate(clarification_result.get("clarifications", [])):
                        resp += f"{i+1}. **{q.get('question')}**\n   *(e.g., {q.get('example_answer')})*\n\n"
                    resp += "---\n*You can answer all of these at once or one by one.*"
                    yield resp
                    return

                # 5. Final standalone formulation
                if is_follow_up:
                    standalone = clarification_input
                else:
                    h_str = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history_list[-10:]])
                    opt_sys_p = "You are a Search Query Generator. Return ONLY keywords (max 10 words). NO LABELS."
                    standalone_res = self.openai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": opt_sys_p},
                            {"role": "user", "content": f"INPUT:\n{h_str}\n\nUSER: {user_query}"}
                        ]
                    )
                    standalone = standalone_res.choices[0].message.content.strip()

            # --- SEARCH SANITIZER: Pure Keywords Only ---
            # Remove MD bolding and prompt-injected labels
            for junk in ["**", "City:", "Destination:", "Subject:", "Final Query:", "Standalone:", "Keywords:"]:
                standalone = standalone.replace(junk, "")
            
            # Take only the last line if multiple lines exist (avoiding prompt leakage)
            if "\n" in standalone:
                standalone = [line for line in standalone.split("\n") if line.strip()][-1]
            
            standalone = standalone.strip().strip('"').strip("'")
            logger.debug(f"Sanitized Standalone: {standalone}")
        else:
            standalone = user_query

        # --- EXECUTION TIER ---
        logger.info(f"EXECUTION: {standalone}")

        notion_data, web_data = {"city_info": {}, "details": {}, "sources": []}, []
        if mode in ["Notion Only", "Hybrid"]:
            notion_data = await self.discover_hierarchy(standalone)
            if notion_data.get("error"):
                yield f"METADATA|{json.dumps({'sources': [], 'is_clarification': False})}\n"
                yield f"Notion Error: {notion_data['error']}\n\nPlease check if your page is shared with the correct integration!"
                return

        has_notion = bool(notion_data.get("city_info"))
        if mode == "Notion Only" and not has_notion:
            yield f"METADATA|{json.dumps({'sources': [], 'is_clarification': False})}\n"
            yield "I couldn't find this City in your Notion. Please check your shared pages."
            return
        
        if mode == "Web Only" or (mode == "Hybrid" and not has_notion):
            try:
                # Tavily has a 400-character limit and produces errors for conversational fluff
                # --- LINK SNIPER: Optimize for booking intent ---
                search_query = standalone[:350]
                if any(k in standalone.lower() for k in ["hotel", "restaurant", "stay", "food"]):
                    search_query += " official booking reservation site"
                
                logger.info(f"FETCHING WEB DATA FOR: {standalone}")
                t_res = t_res = TavilyClient(api_key=os.getenv("TAVILY_API_KEY")).search(query=search_query[:390], search_depth="advanced", include_images=True)
                web_data = [r for r in t_res.get("results", []) if r.get("score", 0) >= 0.70][:5]
                web_images = t_res.get("images", [])
                logger.info(f"Web Search Returned: {len(web_data)} results")
                for i, res in enumerate(web_data[:2]):
                    logger.info(f"   [{i+1}] {res.get('title')} ({res.get('url')})")
            except Exception as e:
                logger.error(f"Tavily Search Error: {e}")
                web_data, web_images = [], []

        context = f"NOTION:\n{json.dumps(notion_data, indent=2)}\n\nWEB:\n{json.dumps(web_data, indent=2)}"
        
        # --- ELITE ENTITY EXTRACTION ---
        notion_entities = []
        # Extract from Notion
        for cat, items in notion_data.get("details", {}).items():
            for itm in items:
                # --- SMART IMAGE EXTRACTION ---
                primary_img = itm.get("primary_display_image") or itm.get("Primary Display Image") or itm.get("Cover") or itm.get("Image") or itm.get("Files")
                asset_list = itm.get("asset_images") or itm.get("Asset Images") or itm.get("Files_assets") or []
                
                # If primary is a list (from files parser), take first. If it's a string, use it.
                img_url = primary_img if isinstance(primary_img, str) else (primary_img[0] if isinstance(primary_img, list) and primary_img else None)
                
                # Fallback: Search all properties for a URL that looks like an image
                if not img_url:
                    for key, val in itm.items():
                        if isinstance(val, str) and (val.startswith("http") and any(ext in val.lower() for ext in [".jpg", ".png", ".jpeg", ".webp"])):
                            img_url = val; break

                # Handle amenities as either list or comma-separated string
                amenities = itm.get("Amenities", [])
                if isinstance(amenities, str):
                    amenities = [a.strip() for a in amenities.split(",")]

                # --- ULTRA-MAPPING (Deep Notion Extraction) ---
                cuisine = itm.get("Cuisine") or itm.get("Food")
                best_for = itm.get("Best for") or itm.get("Best For") or itm.get("Popular For")
                diet = itm.get("Diet Type") or itm.get("Diet")
                address = itm.get("Address") or itm.get("Location")
                status = itm.get("status") or itm.get("Status") or itm.get("Open Status")
                offer = itm.get("Offer") or itm.get("Offers") or itm.get("Deals")
                review = itm.get("Rewiews") or itm.get("Review") or itm.get("Reviews") or itm.get("Details")

                # Smart Amenity Fusion (Clinical Mapping)
                smart_tags = []
                if cuisine: 
                    tag = f"{cuisine}" if isinstance(cuisine, str) else f"{', '.join(cuisine)}"
                    smart_tags.append(tag)
                if diet:
                    tag = f"{diet}" if isinstance(diet, str) else f"{', '.join(diet)}"
                    smart_tags.append(tag)
                if best_for:
                    tag = f"{best_for}" if isinstance(best_for, str) else f"{', '.join(best_for)}"
                    smart_tags.append(tag)
                
                # Use general amenities as fallback
                if not smart_tags: smart_tags = amenities[:3]

                notion_entities.append({
                    "name": itm.get("Name", "Untitled"),
                    "type": cat.rstrip("s"), # Hotel, Restaurant
                    "price": itm.get("Price Range") or itm.get("Budget") or "N/A",
                    "rating": itm.get("Rating") or "N/A",
                    "address": address or "N/A",
                    "status": status,
                    "offer": offer,
                    "review": review,
                    "image": img_url,
                    "asset_images": asset_list if isinstance(asset_list, list) else [asset_list],
                    "url": next((s["url"] for s in notion_data["sources"] if s["title"] == itm.get("Name")), "#"),
                    "booking_url": self._sanitize_link(itm.get("Booking") or itm.get("Booking URL") or itm.get("Website")),
                    "maps_url": self._sanitize_link(itm.get("Location (Map URL)") or itm.get("Map URL") or itm.get("Google Maps") or itm.get("Maps")),
                    "amenities": smart_tags,
                    "source": "Notion"
                })
        
        web_entities = []
        # Extract from Web (Heuristic)
        for i, w in enumerate(web_data):
            w_url = w.get("url", "").lower()
            w_title = w.get("title", "").lower()
            
            # Prioritize entities that look like booking sites, official venues, or major attractions
            is_booking = any(k in w_url for k in ["booking.com", "tripadvisor.com", "hotels.com", "expedia", "opentable", "resy"])
            is_venue = any(k in w_title for k in ["hotel", "resort", "stay", "restaurant", "dining", "food", "cafe", "museum", "palace", "park", "tower", "bridge", "market", "square"])
            
            if is_booking or is_venue:
                # --- SMART IMAGE MATCHING ---
                # Attempt to find the best image in the returned set that matches the entity name
                img_url = None
                if web_images:
                    best_img_score = 0
                    for img in web_images:
                        # Extract core name for matching
                        core_name = w["title"].lower().split()[0] # Take first word (often the brand name)
                        if core_name in img.lower():
                            img_url = img
                            break
                    # Fallback to index if no direct match
                    if not img_url and i < len(web_images):
                        img_url = web_images[i]
                
                # --- RATING SNIPER: Attempt to extract rating from snippet ---
                snippet = (w.get("content", "") + " " + w.get("title", "")).lower()
                rating_match = re.search(r'(\d\.\d|\d)\s?(?:star|stars|/5|/10)', snippet)
                found_rating = rating_match.group(1) if rating_match else None
                
                # If rating is out of 10, normalize to 5
                if found_rating and "/10" in snippet:
                    try: found_rating = str(round(float(found_rating) / 2, 1))
                    except: pass

                suggested_rating = found_rating or ("4.5" if is_booking else "N/A")
                
                web_entities.append({
                    "name": w["title"],
                    "type": "Hotel/Venue" if "hotel" in w_title else "Restaurant/Venue",
                    "price": "N/A",
                    "rating": suggested_rating,
                    "image": img_url,
                    "url": w["url"],
                    "booking_url": w["url"],
                    "maps_url": None, # Will be sniped later
                    "amenities": ["Direct Web Link" if is_booking else "Official Site"],
                    "source": "Web"
                })

        # --- HYBRID DATA WEAVER (ENRICHMENT & DEDUPLICATION) ---
        final_entities = []
        used_web_indices = set()

        # Step 1: Enrich Notion entities with Web metadata
        for n_ent in notion_entities:
            best_match_idx = -1
            best_score = 0
            
            # Simple fuzzy matcher
            for i, w_ent in enumerate(web_entities):
                score = difflib.SequenceMatcher(None, n_ent["name"].lower(), w_ent["name"].lower()).ratio()
                if score > 0.6 and score > best_score:
                    best_score = score
                    best_match_idx = i
            
            if best_match_idx != -1:
                w_match = web_entities[best_match_idx]
                # Enrich: Prioritize Web images/links if Notion ones are missing or generic
                if not n_ent.get("image"): n_ent["image"] = w_match.get("image")
                if n_ent.get("url") == "#" or "notion.so" in n_ent.get("url", ""):
                    # In Hybrid mode, if we have a real booking site URL, consider showing it or keeping Notion URL
                    # Let's keep Notion URL for now but ensure we have a valid link
                    if n_ent["url"] == "#": n_ent["url"] = w_match["url"]
                
                n_ent["source"] = "Notion + Web"
                used_web_indices.add(best_match_idx)
            final_entities.append(n_ent)

        # Step 2: Add remaining unique Web entities
        for i, w_ent in enumerate(web_entities):
            if i not in used_web_indices:
                final_entities.append(w_ent)

        # --- INTENT-AWARE STRUCTURAL SWITCHING ---
        is_trip_plan = any(k in standalone.lower() for k in ["plan", "trip", "itinerary", "itinery", "guide", "7-day", "3-day", "day-by-day"])
        is_hotel_lookup = any(k in standalone.lower() for k in ["hotel", "stay", "accommodation", "resort"])
        is_restaurant_lookup = any(k in standalone.lower() for k in ["restaurant", "food", "dining", "cafe", "biryani"])
        cat_name = "Hotels" if is_hotel_lookup else "Restaurants" if is_restaurant_lookup else "Venues"

        # --- INTENT-STRICT CARD FILTERING ---
        if not is_trip_plan:
            if is_hotel_lookup:
                final_entities = [e for e in final_entities if "hotel" in (e.get("type") or "").lower() or "hotel" in e.get("name", "").lower()]
            elif is_restaurant_lookup:
                final_entities = [e for e in final_entities if any(k in (e.get("type") or "").lower() or k in e.get("name", "").lower() for k in ["restaurant", "food", "cafe", "dining"])]

        # Limit to prevent metadata bloat
        final_entities = final_entities[:12]

        # --- MAP SNIPER: Concurrently fetch Google Maps links for top results ---
        async def fetch_maps_link(ent):
            if ent.get("maps_url"): return ent["maps_url"]
            try:
                # Use Tavily to find the exact Google Maps URL - Targeted Search
                location_context = standalone.split("in ")[-1] if "in " in standalone else ""
                m_query = f"{ent['name']} {location_context} google maps"
                m_res = self.tavily.search(query=m_query, search_depth="basic", max_results=1)
                for r in m_res.get("results", []):
                    if "google.com/maps" in r.get("url", "") or "maps.google.com" in r.get("url", ""):
                        return r["url"]
            except: pass
            return None

        # Snipe maps for FILTERED entities only
        map_tasks = [fetch_maps_link(ent) for ent in final_entities]
        map_urls = await asyncio.gather(*map_tasks)
        for i, m_url in enumerate(map_urls):
            if m_url: final_entities[i]["maps_url"] = m_url

        # --- FINAL SYNTHESIS PREP ---
        is_hotel_lookup = any(k in standalone.lower() for k in ["hotel", "stay", "accommodation", "resort"])
        is_restaurant_lookup = any(k in standalone.lower() for k in ["restaurant", "food", "dining", "cafe", "biryani"])
        is_trip_plan = any(k in standalone.lower() for k in ["itinerary", "plan", "days", "trip", "suggest", "visit"])
        cat_name = "Hotels" if is_hotel_lookup else "Restaurants" if is_restaurant_lookup else "Venues"

        metadata = {
            "sources": notion_data.get("sources", []) + [{"title": w["title"], "url": w["url"], "type": "Web"} for w in web_data],
            "entities": final_entities,
            "is_clarification": False
        }

        print("\n" + "="*50)
        logger.info("INTENT-STRICT ENTITY EXTRACTION")
        logger.info(f"   Target: {standalone} | Intent: {cat_name if not is_trip_plan else 'Trip'}")
        logger.info(f"   Total Displayed Entities: {len(final_entities)}")
        for e in final_entities[:5]:
            logger.info(f"   - {e.get('name')} | Type: {e.get('type')}")
        logger.info("="*50)

        yield f"METADATA|{json.dumps(metadata)}\n"

        if mode == "Web Only":
            if is_trip_plan:
                sys_p = (
                    f"Current Time: {self._get_now_str()}\n"
                    "You are an Elite Travel Experience Architect. Create a PREMIUM, HIGH-ENGAGEMENT itinerary. \n"
                    "STRUCTURE:\n"
                    f"1. [Title] for {standalone} (Professional)\n"
                    "2. Accommodation Strategy: (If exact budget matches are missing for this location, prioritize the CLOSEST value options. NEVER say 'no data available'.)\n"
                    f"3. Recommended Districts in {standalone}\n"
                    f"4. Day-by-Day Structure for {standalone}: (Themes + Specific Venues)\n"
                    "5. Must-Try Foods / Budget Realities / Transportation\n"
                    f"\nRULES: Bold headers. SKIP conversational filler. NO EMOJIS. You are restricted to talking ONLY about {standalone}."
                )
            else:
                sys_p = (
                    f"Current Date: {self._get_now_str()}\n"
                    f"You are a Expert {cat_name} Specialist for {standalone}.\n"
                    "STRUCTURE:\n"
                    f"1. {standalone} {cat_name} Guide\n"
                    f"2. Proximity Pricing: (Alternatives for {standalone} in the results)\n"
                    f"3. Top Specific {cat_name} in {standalone}: (List names, areas)\n"
                    f"4. Local Context for {standalone} (High-value areas)\n"
                    f"\nRULES: Be clinical and specific. Name exact venues. SKIP all greetings. NO EMOJIS. TALK ONLY ABOUT {standalone}."
                )
        elif mode == "Notion Only":
            sys_p = (
                f"Current Date: {self._get_now_str()}\n"
                f"You are a Clinical Data Interface for Notion regarding {standalone}. \n"
                "CRITICAL MANDATE: Provide only the facts. DO NOT use conversational filler. \n"
                f"Answer the query directly using ONLY the provided NOTION DATA for {standalone}. No speculation. NO EMOJIS."
            )
        else: # Hybrid
            sys_p = (
                f"Current Date: {self._get_now_str()}\n"
                f"You are a Premium Travel Intelligence Engine for {standalone}. Synthesize NOTION and WEB data. \n"
                f"ADHERE to the specific intent for {standalone}.\n"
                f"DATA SCARCITY RULES: If search results are empty for {standalone}, provide 'Best-Effort Proximity' recommendations for {standalone}.\n"
                f"Provide the Professional Experience for {standalone} (Themes, Budget Tiers). NO EMOJIS."
            )
        
        # Shared rules for all modes
        sys_p += "\nRULES: USE BOLD HEADERS. SKIP ALL GREETINGS AND SELF-REFERENCES. ANSWER THE QUERY DIRECTLY. NO SPECULATION. NO FILLER."
        # Prepare final context for the AI
        context = f"NOTION DATA:\n{json.dumps(notion_data.get('details', {}))}\n\nWEB SEARCH DATA:\n{json.dumps(web_data)}"
        
        # Final LLM construction: Prioritize User Intent from history over Search Keywords
        messages = [{"role": "system", "content": sys_p}]
        for h in history[-10:]: messages.append(h) # Increased history window for better context
        
        # Always answer the CLARIFIED STANDALONE INTENT, not the raw last word (e.g. "Yes")
        # This ensures affirmative responses like "Yes" still produce a full travel answer
        messages.append({"role": "user", "content": f"DATA SOURCE (RESULTS):\n{context}\n\nINSTRUCTION: Based on these search results and the conversation history, answer this clarified user request: '{standalone}'. Focus strictly on the '{cat_name if not is_trip_plan else 'Trip Plan'}' intent."})
        
        response = self.openai.chat.completions.create(model=self.model, messages=messages, stream=True)
        for chunk in response:
            if chunk.choices[0].delta.content: yield chunk.choices[0].delta.content

    def _get_title(self, obj: Dict[str, Any]) -> str:
        if obj.get("object") == "database":
            titles = obj.get("title", [])
            return "".join([t.get("plain_text", "") for t in titles]) if titles else "Untitled"
        props = obj.get("properties", {})
        for p in props.values():
            if p.get("type") == "title" and p.get("title"): return p["title"][0].get("plain_text", "Untitled")
        return "Untitled"
