"""
ai_engine.py
Sends structured stock/portfolio/mutual fund data to NVIDIA NIM (Primary) 
or OpenRouter (Fallback) and returns McKinsey/Bain-style analysis as validated JSON.
"""

import os
import json
import requests
import re

from advisor.prompt_builder import (
    build_stock_system_prompt,     
    build_stock_user_prompt,         
    build_portfolio_system_prompt,
    build_portfolio_user_prompt,
    build_mf_system_prompt,       
    build_mf_user_prompt,         
)

# API Keys
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Primary: NVIDIA Free API (Requires NVIDIA_API_KEY in Railway Variables)
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
PRIMARY_MODEL = "meta/llama-3.1-70b-instruct"

# Fallback: OpenRouter Free API
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FALLBACK_MODEL = "openrouter/auto"  # Or "google/gemini-2.0-flash-exp:free"


def _call_api(provider: str, model: str, system_prompt: str, user_content: str) -> str:
    """
    Handles API calls to both NVIDIA and OpenRouter based on the specified provider.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.2, # Kept low for accurate JSON
        "max_tokens": 1024
    }

    if provider == "nvidia":
        if not NVIDIA_API_KEY:
            raise ValueError("NVIDIA_API_KEY is not set.")
        
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }
        url = NVIDIA_URL
        
    elif provider == "openrouter":
        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is not set.")
            
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ai-stock.app",
            "X-Title": "Ai-Stock Analyzer"
        }
        url = OPENROUTER_URL
    else:
        raise ValueError("Unknown API provider.")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            print(f"{provider.capitalize()} Error: {response.status_code} - {response.text}")
            
        response.raise_for_status()
        result = response.json()
        
        if "choices" not in result:
            print(f"API Error: 'choices' missing. Full response: {result}")
            raise KeyError("'choices' not found in response")
            
        return result["choices"][0]["message"]["content"]
        
    except requests.exceptions.RequestException as e:
        print(f"Request to {provider} failed: {str(e)}")
        raise


def _extract_json(raw_text: str) -> dict:
    """
    Handles cases where the model wraps JSON in markdown fences or adds stray text.
    """
    text = raw_text.strip()
    
    if "<think>" in text and "</think>" in text:
        text = text.split("</think>")[-1].strip()
        
    text = re.sub(r'^```[a-zA-Z]*\s*', '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            clean_json_str = text[start:end + 1]
            return json.loads(clean_json_str)
        except json.JSONDecodeError as e:
            print(f"Failed to parse extracted JSON block: {clean_json_str}")
            raise ValueError(f"Extracted block is invalid JSON: {str(e)}")

    print(f"Raw text failed to parse:\n{raw_text}")
    raise ValueError("Could not parse valid JSON from model response")

def _run_with_fallback(system_prompt: str, user_content: str) -> dict:
    """
    Tries NVIDIA first. If it fails (e.g., rate limit), it safely falls back to OpenRouter.
    """
    # Try NVIDIA First
    try:
        print(f"Calling NVIDIA API with {PRIMARY_MODEL}...")
        raw_response = _call_api("nvidia", PRIMARY_MODEL, system_prompt, user_content)
        return _extract_json(raw_response)
    
    except Exception as e:
        print(f"NVIDIA API failed ({str(e)}). Switching to OpenRouter ({FALLBACK_MODEL})...")
        
        # Fallback to OpenRouter
        try:
            raw_response = _call_api("openrouter", FALLBACK_MODEL, system_prompt, user_content)
            return _extract_json(raw_response)
        
        except Exception as fallback_e:
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

def analyze_mutual_fund(mf_data: dict, user_question: str = None) -> dict:
    system_prompt = build_mf_system_prompt()
    user_content = build_mf_user_prompt(mf_data, user_question)
    return _run_with_fallback(system_prompt, user_content)
