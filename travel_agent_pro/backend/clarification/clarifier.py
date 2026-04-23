import json
from openai import OpenAI

class QueryClarifier:
    def __init__(self):
        self.openai = OpenAI()
        
    def evaluate_query(self, query: str, system_prompt: str, history: list) -> dict:
        """
        Evaluates a query to check if it's self-contained and fully answerable.
        Returns a dictionary representing the JSON output required.
        """
        clarifier_system_prompt = """You are a Generic Query Clarification Agent.
You will receive:
1. A system_prompt (describes the task/domain)
2. A user query
3. Full Chat History (Essential for context)
Your job is to determine whether the query is self-contained and fully answerable.

### Step 1: Output Schema (STRICT)
You MUST return a JSON object with:
- "clarification_needed": (boolean)
- "query": (string) This MUST be an EXACT 1:1 copy of the user's input. Do NOT add context to it.
- "clarifications": (list of {question, example_answer}) IF needed.

### Step 2: Strict Logic Rules
1. **DYNAMIC ENGAGEMENT**: Do NOT use hardcoded or robotic phrases. Your questions MUST be highly relevant to the specific user intent. If they ask about a "romantic dinner," ask about "vibe and view." If they ask about "adventure," ask about "pace and intensity."
2. **AUTHORITY AUDIT**: A variable is ONLY 'Approved' if explicitly mentioned by the USER in the session history.
3. **STATE PERSISTENCE (STATE LOCK)**: If a value (e.g., 'Goa') was provided by the USER previously, it is LOCKED. You are FORBIDDEN from asking for it again.
4. **QUERY FIDELITY**: The 'query' field in JSON MUST match the raw input exactly.
5. **BATCH CLARIFICATION**: Identify ALL missing gaps simultaneously. Return them as a list of engaging, context-specific questions.
6. **STYLE**: Use the provided Few-Shot examples in the domain prompt as a guide for brevity and impact, but adapt your language to the User Assistant persona.

### Example Case:
History: 
- USER: Tell me about Tokyo
- ASSISTANT: Tokyo is great! For a budget of $3000, it's amazing.
- USER: Give me a plan
Analysis: Location 東京 is from history (Lookup turn). Intent is now Plan. Location needs verification. Budget $3000 is from ASSISTANT, so it is MISSING.
Result: Return clarification_needed: true, and ask about the Location first (or Budget).
"""

        import datetime
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Stateless clarification: No history context. Pure functional validation of the query.
        context_input = f"Current Date/Time: {current_time}\nDomain System Prompt:\n{system_prompt}\n\nCurrent User Query:\n{query}"

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": clarifier_system_prompt},
                    {"role": "user", "content": context_input}
                ],
                response_format={"type": "json_object"}
            )
            raw_response = response.choices[0].message.content.strip()
            return json.loads(raw_response)
        except Exception as e:
            print(f"⚠️ Clarifier Error: {e}")
            return {"clarification_needed": False, "query": query, "standalone": query}
