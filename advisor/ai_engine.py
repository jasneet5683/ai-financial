"""
ai_engine.py
Sends structured stock/portfolio data to OpenRouter and returns
McKinsey/Bain-style analysis as validated JSON.
"""

import os
import json
import requests

from advisor.prompt_builder import (
    build_stock_system_prompt,
    build_stock_user_prompt,
    build_portfolio_system_prompt,
    build_portfolio_user_prompt,
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PRIMARY_MODEL = "deepseek/deepseek-r1"
FALLBACK_MODEL = "mistralai/mistral-7b-instruct"


def _call_openrouter(model: str, system_prompt: str, user_content: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.4,
    }
    
    # DeepSeek R1 takes a long time to "think". Increased timeout to 180 seconds.
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"]


def _extract_json(raw_text: str) -> dict:
    """
    Handles cases where the model wraps JSON in markdown fences or adds stray text.
    """
    text = raw_text.strip()
    
    # DeepSeek R1 often puts its thinking inside <think>...</think> tags. 
    # We must remove that before parsing JSON.
    if "<think>" in text and "</think>" in text:
        text = text.split("</think>")[-1].strip()
        
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse valid JSON from model response")


def _run_with_fallback(system_prompt: str, user_content: str) -> dict:
    """
    Tries the primary model. If it fails or times out, tries the fallback model.
    """
    try:
        # Try DeepSeek first
        print(f"Calling OpenRouter with {PRIMARY_MODEL}...")
        raw_response = _call_openrouter(PRIMARY_MODEL, system_prompt, user_content)
        return _extract_json(raw_response)
    
    except Exception as e:
        print(f"{PRIMARY_MODEL} failed ({str(e)}). Switching to {FALLBACK_MODEL}...")
        
        try:
            # Fallback to Mistral (much faster, won't time out as easily)
            raw_response = _call_openrouter(FALLBACK_MODEL, system_prompt, user_content)
            return _extract_json(raw_response)
        
        except Exception as fallback_e:
            # If both fail, return a structured error so the frontend doesn't crash
            return {
                "error": f"AI Engine failed. Primary error: {str(e)}. Fallback error: {str(fallback_e)}"
            }


def analyze_stock(stock_data: dict, user_question: str = None) -> dict:
    system_prompt = build_stock_system_prompt()
    user_content = build_stock_user_prompt(stock_data, user_question)
    return _run_with_fallback(system_prompt, user_content)


def analyze_portfolio(portfolio_data: list, user_question: str = None) -> dict:
    system_prompt = build_portfolio_system_prompt()
    user_content = build_portfolio_user_prompt(portfolio_data, user_question)
    return _run_with_fallback(system_prompt, user_content)
