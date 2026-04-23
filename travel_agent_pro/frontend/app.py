import streamlit as st
import httpx
import json
import os
import datetime
import re
from dotenv import load_dotenv
import extra_streamlit_components as stx

load_dotenv()

st.set_page_config(
    page_title="Notion Travel Pro | Elite Assistant",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .status-green { color: #22c55e !important; font-weight: 600; font-size: 0.9rem; }
    .stApp { background: #0f172a; color: #f1f5f9; font-family: 'Inter', sans-serif; }
    [data-testid="stChatMessage"] { background-color: rgba(30, 41, 59, 0.7) !important; backdrop-filter: blur(10px); border: 1px solid rgba(71, 85, 105, 0.4) !important; border-radius: 1.5rem !important; margin-bottom: 0.5rem !important; padding: 1rem !important; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3); }
    [data-testid="stChatMessageContent"] { color: #f1f5f9 !important; font-size: 1.05rem !important; line-height: 1.6 !important; }
    [data-testid="stChatMessageContent"] b, [data-testid="stChatMessageContent"] strong { color: #60a5fa; }
    .stButton > button { border-radius: 20px !important; border: 1px solid #3b82f6 !important; background: transparent !important; color: #3b82f6 !important; font-weight: 500 !important; }
    .stButton > button:hover { background: #3b82f6 !important; color: white !important; }
    [data-testid="stSidebar"] { background-color: #0f172a; }
    .stRadio > label { font-weight: 600 !important; color: #60a5fa !important; }
    .source-tag { display: inline-block; background: rgba(59, 130, 246, 0.15); border: 1px solid rgba(59, 130, 246, 0.3); padding: 2px 8px; border-radius: 6px; margin-right: 5px; margin-top: 5px; font-size: 0.8rem; }
    
    /* --- ELITE CARDS CSS --- */
    .entity-container { display: flex; overflow-x: auto; gap: 1.2rem; padding: 1rem 0; scrollbar-width: none; }
    .entity-container::-webkit-scrollbar { display: none; }
    .entity-card { 
        min-width: 280px; max-width: 280px; 
        background: rgba(30, 41, 59, 0.4); 
        backdrop-filter: blur(16px); 
        border: 1px solid rgba(255, 255, 255, 0.1); 
        border-radius: 1.2rem; 
        overflow: hidden;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
        flex-shrink: 0;
        position: relative; /* CRITICAL: Keep badges inside the card */
    }
    .entity-card:hover { 
        transform: translateY(-8px) scale(1.02); 
        border-color: rgba(96, 165, 250, 0.6);
        box-shadow: 0 15px 50px rgba(59, 130, 246, 0.2);
    }
    .entity-img { 
        width: 100%; height: 180px; object-fit: cover; 
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        display: block;
    }
    .entity-content { 
        padding: 1.25rem; 
        display: flex; 
        flex-direction: column; 
        position: relative;
        z-index: 2; /* Sit above any image overflows */
    }
    .entity-type { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1.5px; color: #60a5fa; margin-bottom: 0.4rem; font-weight: 600; opacity: 0.9; }
    .entity-title { font-size: 1.15rem; font-weight: 800; margin-bottom: 0.5rem; color: #f8fafc; line-height: 1.3; min-height: 3.1rem; }
    .entity-meta { display: flex; justify-content: space-between; font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.75rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 0.5rem; }
    .entity-rating { color: #fbbf24; font-weight: 700; }
    .entity-amenity { font-size: 0.72rem; background: rgba(59, 130, 246, 0.1); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.2); padding: 2px 8px; border-radius: 6px; margin-right: 4px; margin-bottom: 4px; display: inline-block; font-weight: 500; }
    .book-btn { 
        display: block; width: 100%; text-align: center; 
        background: linear-gradient(135deg, #3b82f6, #1d4ed8); 
        color: white !important; font-weight: 700; 
        padding: 0.65rem; border-radius: 0.75rem; 
        text-decoration: none !important; margin-top: 0.75rem;
        transition: transform 0.2s; font-size: 0.9rem;
        position: relative; z-index: 10;
    }
    .maps-btn { 
        display: block; width: 100%; text-align: center; 
        background: rgba(30, 41, 59, 0.6); 
        border: 1px solid rgba(96, 165, 250, 0.4);
        color: #60a5fa !important; font-weight: 600; 
        padding: 0.65rem; border-radius: 0.75rem; 
        text-decoration: none !important; margin-top: 0.5rem;
        transition: all 0.2s; font-size: 0.85rem;
        position: relative; z-index: 10;
    }
    .book-btn:hover { transform: scale(1.02); box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4); }
    .maps-btn:hover { background: rgba(59, 130, 246, 0.1); border-color: #60a5fa; }
    
    /* --- ULTRA-MAPPING ELEMENTS --- */
    .entity-badge-container { position: absolute; top: 12px; right: 12px; display: flex; flex-direction: column; gap: 6px; align-items: flex-end; z-index: 5; }
    .entity-status { background: rgba(34, 197, 94, 0.85); color: white; padding: 2px 10px; border-radius: 6px; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.2); }
    .entity-offer { background: rgba(234, 179, 8, 0.9); color: #422006; padding: 2px 10px; border-radius: 6px; font-size: 0.65rem; font-weight: 800; text-transform: uppercase; border: 1px solid rgba(255,255,255,0.3); }
    .entity-address { font-size: 0.8rem; color: #64748b; margin-top: -0.3rem; margin-bottom: 0.6rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-style: italic; }
    .entity-review { background: rgba(59, 130, 246, 0.05); border-left: 3px solid #3b82f6; padding: 8px 12px; border-radius: 0 8px 8px 0; font-size: 0.8rem; color: #94a3b8; line-height: 1.4; margin: 10px 0; font-style: italic; position: relative; z-index: 1; }
    .entity-review::before { content: '"'; font-size: 2rem; color: rgba(59, 130, 246, 0.1); position: absolute; top: -10px; left: 5px; }
</style>
""", unsafe_allow_html=True)

# --- State Initialization ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "sources" not in st.session_state:
    st.session_state.sources = []
if "clarification_count" not in st.session_state:
    st.session_state.clarification_count = 0

# --- Cookie Management ---
cookie_manager = stx.CookieManager()

# --- Auth Logic ---
token = None
url_token = st.query_params.get("token")
if url_token:
    token = url_token
    expiry = datetime.datetime.now() + datetime.timedelta(days=7)
    cookie_manager.set("notion_token", url_token, expires_at=expiry)
    st.query_params.clear()
else:
    # Double-lock to prevent sticky sessions after sign-out
    if st.session_state.get("logout_triggered"):
        token = None
    else:
        token = cookie_manager.get("notion_token")

def login():
    st.markdown(f'<meta http-equiv="refresh" content="0; url={BACKEND_URL}/login">', unsafe_allow_html=True)

if not token:
    st.markdown("<h1 style='text-align: center; margin-top: 100px;'>Notion Travel Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94a3b8;'>Elite travel intelligence for your Notion workspace.</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        if st.button("Connect Notion", use_container_width=True): login()
else:
    def render_entity_cards(entities):
        if not entities: return
        # Using columns 1 just as a container
        card_html = '<div class="entity-container">'
        for itm in entities:
            # Sanitize strings to avoid breaking HTML attributes
            clean_name = itm.get("name", "Untitled").replace('"', "&quot;")
            clean_title = itm.get("title", clean_name).replace('"', "&quot;")
            
            def safe_stars(r):
                try:
                    val = float(str(r).replace("star", "").replace("stars", "").strip())
                    return f"Rating: {val} / 5"
                except: return "Recommended" if r != "N/A" else ""

            display_rating = safe_stars(itm.get("rating", "N/A"))
            rating_text = f'{display_rating}'
            price_text = f'Price: {itm["price"]}' if itm["price"] != "N/A" else "Price N/A"
            
            # Contextual high-end fallback images (as per Vijay's guidance)
            fallbacks = {
                "Hotel": "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&q=80&w=600",
                "Restaurant": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?auto=format&fit=crop&q=80&w=600",
                "Venue": "https://images.unsplash.com/photo-1533105079780-92b9be482077?auto=format&fit=crop&q=80&w=600",
                "Itinerary": "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&fit=crop&q=80&w=600"
            }
            img_src = itm.get("image") or fallbacks.get(itm.get("type"), fallbacks["Itinerary"])
            img_html = f'<img src="{img_src}" class="entity-img" alt="{clean_name}">'
            
            amenities_html = "".join([f'<span class="entity-amenity">{a}</span>' for a in itm.get("amenities", [])[:3]])
            
            item_url = itm.get("booking_url") or itm.get("url")
            maps_url = itm.get("maps_url")
            
            # Button logic: "Open in Notion" for internal links, "Visit & Book" for external
            if item_url and "notion.so" in item_url:
                book_button = f'<a href="{item_url}" target="_blank" class="book-btn" style="background: #ffffff !important; color: #000000 !important; border: 1px solid #e2e8f0 !important;">Open in Notion</a>'
            elif item_url and item_url != "#":
                book_button = f'<a href="{item_url}" target="_blank" class="book-btn">Visit & Book</a>'
            else:
                book_button = ""
            
            # Ultra-Mapping Logic
            status_html = f'<div class="entity-status">{itm["status"]}</div>' if itm.get("status") else ""
            offer_html = f'<div class="entity-offer">{itm["offer"]}</div>' if itm.get("offer") else ""
            address_html = f'<div class="entity-address">{itm["address"]}</div>' if itm.get("address") and itm.get("address") != "N/A" else ""
            review_html = f'<div class="entity-review">{itm["review"]}</div>' if itm.get("review") else ""
            
            maps_button = f'<a href="{maps_url}" target="_blank" class="maps-btn">View on Map</a>' if maps_url else ''
            
            card_html += f'<div class="entity-card"><div class="entity-badge-container">{status_html}{offer_html}</div>{img_html}<div class="entity-content"><div class="entity-type">{itm["type"]} | {itm["source"]}</div><div class="entity-title">{clean_name}</div>{address_html}<div class="entity-meta"><span class="entity-rating">{rating_text}</span><span>{price_text}</span></div><div style="min-height: 40px;">{amenities_html}</div>{review_html}{book_button}{maps_button}</div></div>'

        card_html += '</div>'
        # Crucial: Use a unique container to prevent Streamlit from escaping or double-rendering
        st.markdown(card_html, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("### Intelligence Control")
        selected_mode = st.radio(
            "Knowledge Source",
            ["Hybrid", "Notion Only", "Web Only"],
            help="Choose where the agent looks for answers."
        )
        
        st.divider()
        st.markdown("### Trip Planner")
        selected_dates = st.date_input(
            "Expected Travel Dates",
            value=[],
            help="Select your travel dates and the agent will automatically remember them!"
        )
        
        st.divider()
        st.markdown("### Explorer Tools")
        st.caption("Active Session")
        for _ in range(15): st.write("")
        st.divider()
        st.markdown('<div class="status-green">Connected: Notion Session</div>', unsafe_allow_html=True)
        if st.button("Sign Out", type="secondary", use_container_width=True):
            cookie_manager.delete("notion_token")
            st.session_state["logout_triggered"] = True
            # Nuke ALL session state variables for a clean slate
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # Predefined Queries
    st.caption("Quick Insights")
    q_col1, q_col2, q_col3, q_col4 = st.columns(4)
    quick_queries = ["Hotels in Barcelona", "Best Food in Paris", "London Itinerary", "Japan Weather"]
    actual_queries = ["What are my hotels in Barcelona?", "Show my restaurant list for Paris", "Give me my itinerary for London", "Check weather in Japan"]
    selected_query = None
    if q_col1.button(quick_queries[0]): selected_query = actual_queries[0]
    if q_col2.button(quick_queries[1]): selected_query = actual_queries[1]
    if q_col3.button(quick_queries[2]): selected_query = actual_queries[2]
    if q_col4.button(quick_queries[3]): selected_query = actual_queries[3]

    # Main Chat View
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): 
            if msg.get("type") == "sources":
                with st.expander("View Sources & References", expanded=False):
                    st.markdown(msg["content"], unsafe_allow_html=True)
            elif msg.get("type") == "entities":
                render_entity_cards(msg["data"])
            else:
                st.markdown(msg["content"], unsafe_allow_html=True)

    prompt = st.chat_input("Ask about your trip...")
    if selected_query: prompt = selected_query
    
    is_confirmed = False
    if st.session_state.get("is_consent_required") and st.session_state.get("proposed_query"):
        if st.button(f"Confirm & Search: {st.session_state.proposed_query}", type="primary", use_container_width=True):
            prompt = st.session_state.proposed_query
            is_confirmed = True
            st.session_state.is_consent_required = False
            st.session_state.proposed_query = None
        
    if prompt:
        if not st.session_state.messages: st.session_state.clarification_count = 0
        with st.chat_message("user"): st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.status(f"Consulting {selected_mode} Network...", expanded=False) as status:
            try:
                # Expand memory window to prevent amnesia during long clarification chains
                history = st.session_state.messages[-20:]
                headers = {"Authorization": f"Bearer {token}"}
                
                date_str = None
                if selected_dates:
                    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
                        date_str = f"{selected_dates[0]} to {selected_dates[1]}"
                    elif isinstance(selected_dates, tuple) and len(selected_dates) == 1:
                        date_str = f"{selected_dates[0]}"
                    else:
                        date_str = f"{selected_dates}"

                # Sanitize out any leaked METADATA from old buggy sessions so the AI doesn't learn from it!
                sanitized_history = []
                for m in history:
                    if m.get("type") != "sources":
                        clean_content = re.sub(r'METADATA\|\{.*?\}\s*', '', m.get("content", ""))
                        sanitized_history.append({"role": m["role"], "content": clean_content})

                api_data = {
                    "query": prompt, 
                    "history": sanitized_history,
                    "clarification_count": st.session_state.clarification_count,
                    "mode": selected_mode,
                    "is_confirmed": is_confirmed,
                    "travel_date": date_str
                }
                
                with httpx.stream("POST", f"{BACKEND_URL}/query/stream", json=api_data, headers=headers, timeout=60.0) as r:
                    full_answer = ""
                    with st.chat_message("assistant"): placeholder = st.empty()
                    
                    response_iter = r.iter_text()
                    buffer = ""
                    metadata_parsed = False
                    is_clarification = False
                    current_sources = []
                    
                    for chunk in response_iter:
                        if not metadata_parsed:
                            buffer += chunk
                            # Handle error messages that might be sent as plain text from the agent
                            if "Notion Error" in buffer:
                                placeholder.markdown(buffer)
                                full_answer = buffer
                                metadata_parsed = True
                                break

                            if "METADATA|" in buffer and "\n" in buffer:
                                # Find where the metadata starts and ends
                                meta_start = buffer.find("METADATA|")
                                meta_end = buffer.find("\n", meta_start)
                                
                                if meta_end != -1:
                                    meta_line = buffer[meta_start:meta_end].strip()
                                    try: 
                                        meta_data = json.loads(meta_line.replace("METADATA|", ""))
                                        current_sources = meta_data.get("sources", [])
                                        current_entities = meta_data.get("entities", [])
                                        st.session_state.sources = current_sources
                                        st.session_state.entities = current_entities
                                        is_clarification = meta_data.get("is_clarification", False)
                                        
                                        # Consent routing
                                        if meta_data.get("is_consent_required"):
                                            st.session_state.is_consent_required = True
                                            st.session_state.proposed_query = meta_data.get("proposed_query", "")
                                    except: pass
                                    
                                    # Keep everything EXCEPT the metadata line
                                    full_answer = buffer[:meta_start] + buffer[meta_end+1:]
                                    metadata_parsed = True
                                    placeholder.markdown(full_answer)
                        else:
                            full_answer += chunk
                            # Violent secondary scrubber: If AI hallucinates metadata, wipe it from the screen immediately.
                            if "METADATA|" in full_answer:
                                full_answer = re.sub(r'METADATA\|\{.*?\}', '', full_answer, flags=re.DOTALL)
                                
                            placeholder.markdown(full_answer.replace("METADATA|", ""))
                    
                    # One final scrub before committing to long-term memory
                    full_answer = re.sub(r'METADATA\|\{.*?\}', '', full_answer, flags=re.DOTALL).replace("METADATA|", "").strip()
                    st.session_state.messages.append({"role": "assistant", "content": full_answer})

                    if current_sources and not is_clarification:
                        source_links = []
                        for s in current_sources:
                            source_links.append(f'<div class="source-tag"><a href="{s["url"]}" target="_blank">[{s["type"]}] {s["title"]}</a></div>')
                        source_content = " ".join(source_links)
                        with st.chat_message("assistant"):
                            with st.expander("View Sources & References", expanded=False):
                                st.markdown(source_content, unsafe_allow_html=True)
                        st.session_state.messages.append({"role": "assistant", "content": source_content, "type": "sources"})

                    if st.session_state.get("entities") and not is_clarification:
                        with st.chat_message("assistant"):
                            render_entity_cards(st.session_state.entities)
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": "Rendered Cards", 
                            "type": "entities", 
                            "data": st.session_state.entities
                        })

                    if is_clarification: st.session_state.clarification_count += 1
                    else: st.session_state.clarification_count = 0
                        
                    status.update(label=f"Elite {selected_mode} Intelligence Gathered", state="complete")
                    st.rerun()
            except Exception as e: st.error(f"Error: {e}")
