# Notion Travel Pro | Elite Assistant

An AI-powered travel intelligence engine that seamlessly blends your personal Notion travel data with real-time web discovery. Designed for travelers who want a high-IQ assistant that remembers their preferences while staying updated with the latest travel trends, availability, and local insights.

## 🚀 Overview

Notion Travel Pro is a full-stack agentic system that transforms your static Notion workspace into a dynamic travel command center.

- **Dual-Track Discovery**: Automatically scans your Notion databases (Cities, Hotels, Restaurants, Itineraries) while simultaneously fetching live data from the web via Tavily.
- **Intelligent Clarification**: Doesn't settle for vague queries. If you ask to "plan a trip," the agent proactively gathers missing details like budget, dietary preferences, and travel style.
- **Elite UI/UX**: A sleek, dark-mode Streamlit interface featuring interactive "Elite Cards" with live booking links, map integrations, and high-fidelity imagery.
- **Hybrid Intelligence**: Combines private Notion data (your curated lists) with public web data (ratings, reviews, live booking status).

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.9+)
- **Frontend**: Streamlit
- **LLM**: GPT-4o (via OpenAI)
- **Search**: Tavily Search API
- **Workspace**: Notion API (Official SDK)
- **Styling**: Vanilla CSS with Glassmorphism effects

## 📋 Prerequisites

- Python 3.9 or higher
- [OpenAI API Key](https://platform.openai.com/)
- [Tavily API Key](https://tavily.com/)
- [Notion Integration Token](https://www.notion.so/my-integrations) (and shared pages/databases)

## ⚙️ Setup Instructions

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/tweenylabs/chat-automation-suite.git
   cd Notion_MCP/travel_agent_pro
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the `travel_agent_pro/` directory:
   ```env
   OPENAI_API_KEY=your_openai_key
   TAVILY_API_KEY=your_tavily_key
   
   # Optional: Hardcode DB IDs if auto-discovery is skipped
   NOTION_CITIES_DB_ID=your_db_id
   NOTION_HOTELS_DB_ID=your_db_id
   NOTION_RESTAURANTS_DB_ID=your_db_id
   NOTION_ITINERARY_DB_ID=your_db_id
   ```

3. **Install Dependencies**:
   ```bash
   pip install fastapi uvicorn streamlit httpx notion-client tavily-python openai python-dotenv extra-streamlit-components
   ```

## 🏃 Running the System

You need to run both the backend and the frontend simultaneously.

### 1. Start the Backend
```bash
cd travel_agent_pro
python -m backend.main
```
The API will be available at `http://localhost:8000`.

### 2. Start the Frontend
```bash
cd travel_agent_pro
streamlit run frontend/app.py
```
The application will open in your browser (usually at `http://localhost:8501`).

## 🧪 How to Test

To verify the system is working correctly, follow these steps:

1. **OAuth Connection**: Open the Streamlit app and click **"Connect Notion"**. Log in and authorize the pages you want the agent to see.
2. **Connectivity Check**: Once redirected back, you should see "Connected: Notion Session" in the sidebar.
3. **Notion Search**: Try asking about something in your Notion (e.g., "What are my hotels in Barcelona?"). The agent should pull data directly from your database.
4. **Web Hybrid Search**: Ask for something new (e.g., "Find me highly-rated seafood in Paris"). The agent will use Tavily to fetch live results and present them as interactive cards.
5. **Clarification Flow**: Ask a vague question like "Plan a trip for me." The agent should respond with a numbered checklist asking for your destination, budget, and dates.

---
Built with ❤️ by the Tweeny Labs team.
