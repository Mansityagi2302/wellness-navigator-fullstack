from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# 1. Initialize the FastAPI app FIRST
app = FastAPI(title="Wellness Navigator AI")

# 2. Add Middleware IMMEDIATELY after initializing app
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", # Local React testing
        "https://rococo-crumble-54594e.netlify.app", # Your live frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Imports and Config ---
try:
    from supabase import Client, create_client
except Exception:
    Client = None
    create_client = None

try:
    from langgraph.graph import END, StateGraph, START
except Exception as exc:
    raise RuntimeError("LangGraph is required. Install with `pip install langgraph`.") from exc

# --- Models ---
class CoachRequest(BaseModel):
    user_name: str
    message: str
    goal: Optional[str] = None
    activity_level: Optional[str] = None
    primary_metric: Optional[str] = None
    focus_area: Optional[str] = None

class CoachResponse(BaseModel):
    focus_area: str
    ready_to_sync: bool
    missing_field: Optional[str]
    next_question: Optional[str]
    recommended_actions: List[str]
    safety_flag: Optional[str]

class SyncRequest(BaseModel):
    user_name: str
    focus_area: str
    health_metric: str
    primary_goal: str
    timestamp: Optional[str] = None

class CoachState(TypedDict, total=False):
    user_name: str
    message: str
    goal: Optional[str]
    activity_level: Optional[str]
    primary_metric: Optional[str]
    focus_area: Optional[str]
    next_question: Optional[str]
    missing_field: Optional[str]
    ready_to_sync: bool
    recommended_actions: List[str]
    safety_flag: Optional[str]

# --- Constants & Clients ---
SAFETY_KEYWORDS = {"chest pain", "shortness of breath", "suicidal", "faint", "fainted"}
FITNESS_KEYWORDS = {"workout", "steps", "muscle", "run", "cardio", "strength"}
NUTRITION_KEYWORDS = {"calories", "meal", "water", "protein", "fiber", "hydration"}
RESILIENCE_KEYWORDS = {"anxiety", "sleep", "meditation", "stress", "burnout"}

WEBHOOK_URL = os.getenv("WELLNESS_WEBHOOK_URL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase_client: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Logic Functions ---
def classify_intent(message: str) -> str:
    lowered = message.lower()
    if any(k in lowered for k in FITNESS_KEYWORDS): return "fitness"
    if any(k in lowered for k in NUTRITION_KEYWORDS): return "nutrition"
    if any(k in lowered for k in RESILIENCE_KEYWORDS): return "resilience"
    return "fitness"

def detect_safety(message: str) -> Optional[str]:
    lowered = message.lower()
    for word in SAFETY_KEYWORDS:
        if word in lowered:
            return "Possible distress detected. Please contact emergency services immediately."
    return None

def missing_field(state: CoachState) -> Optional[str]:
    for field in ("goal", "activity_level", "primary_metric"):
        if not state.get(field): return field
    return None

def clarification_prompt(field: str) -> str:
    prompts = {
        "goal": "What's your primary wellness goal right now?",
        "activity_level": "How active have you been this week?",
        "primary_metric": "What metric should we track? (e.g., steps, sleep hours)",
    }
    return prompts.get(field, "Could you share more detail?")

def recommendations_for_focus(focus: str) -> List[str]:
    recs = {
        "fitness": ["Plan 3-4 sessions this week.", "Log steps daily."],
        "nutrition": ["Aim for protein in each meal.", "Hydrate steadily."],
        "resilience": ["Schedule a sleep window.", "Add a 5-min breathing break."]
    }
    return recs.get(focus, recs["fitness"])

def log_to_supabase(state: CoachState) -> None:
    if not supabase_client: return
    payload = {
        "user_name": state.get("user_name"),
        "focus_area": state.get("focus_area"),
        "primary_goal": state.get("goal"),
        "activity_level": state.get("activity_level"),
        "health_metric": state.get("primary_metric"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        supabase_client.table("health_logs").insert(payload).execute()
    except:
        return

# --- Graph Nodes ---
def start_node(state: CoachState) -> CoachState:
    state["safety_flag"] = detect_safety(state.get("message", ""))
    state["ready_to_sync"] = False
    return state

def intent_classifier_node(state: CoachState) -> CoachState:
    if not state.get("focus_area"):
        state["focus_area"] = classify_intent(state.get("message", ""))
    return state

def wellness_node(state: CoachState) -> CoachState:
    missing = missing_field(state)
    state["missing_field"] = missing
    state["recommended_actions"] = recommendations_for_focus(state.get("focus_area", "fitness"))
    if missing:
        state["next_question"] = clarification_prompt(missing)
        state["ready_to_sync"] = False
    else:
        state["next_question"] = None
        state["ready_to_sync"] = True
        log_to_supabase(state)
    return state

def router(state: CoachState) -> str:
    focus = state.get("focus_area") or "fitness"
    return f"{focus}_node"

# --- Build LangGraph ---
workflow = StateGraph(CoachState)
workflow.add_node("initial_node", start_node)
workflow.add_node("intent_classifier_node", intent_classifier_node)
workflow.add_node("fitness_node", wellness_node)
workflow.add_node("nutrition_node", wellness_node)
workflow.add_node("resilience_node", wellness_node)

workflow.add_edge(START, "initial_node")
workflow.add_edge("initial_node", "intent_classifier_node")
workflow.add_conditional_edges("intent_classifier_node", router)
workflow.add_edge("fitness_node", END)
workflow.add_edge("nutrition_node", END)
workflow.add_edge("resilience_node", END)

coach_executor = workflow.compile()

# --- API Routes ---
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/coach", response_model=CoachResponse)
async def coach(request: CoachRequest):
    state: CoachState = {
        "user_name": request.user_name,
        "message": request.message,
        "goal": request.goal,
        "activity_level": request.activity_level,
        "primary_metric": request.primary_metric,
        "focus_area": request.focus_area,
    }
    result = coach_executor.invoke(state)
    
    return CoachResponse(
        focus_area=result.get("focus_area", "fitness"),
        ready_to_sync=result.get("ready_to_sync", False),
        missing_field=result.get("missing_field"),
        next_question=result.get("next_question"),
        recommended_actions=result.get("recommended_actions", []),
        safety_flag=result.get("safety_flag"),
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)