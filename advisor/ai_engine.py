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

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
PRIMARY_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
FALLBACK_MODEL = "openrouter/free"

def _call_api(provider: str, model: str, system_prompt: str, user_content: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,  # Forces strict, perfect JSON
        "max_tokens": 2048
    }

    if provider == "nvidia":
        headers = {
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json"
        }
        url = NVIDIA_URL
        timeout = 180  # Increased from 60 to 180 so NVIDIA doesn't crash
        
    elif provider == "openrouter":
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        url = OPENROUTER_URL
        timeout = 120
    else:
        raise ValueError("Unknown API provider.")
    
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    
    return response.json()["choices"][0]["message"]["content"]

def _extract_json(raw_text: str) -> dict:
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
            return json.loads(text[start:end + 1])
        except Exception as e:
            raise ValueError(f"Extracted block is invalid JSON: {str(e)}")

    raise ValueError("Could not parse JSON from response")

def _run_with_fallback(system_prompt: str, user_content: str) -> dict:
    try:
        print(f"Calling NVIDIA API...")
        raw_response = _call_api("nvidia", PRIMARY_MODEL, system_prompt, user_content)
        return _extract_json(raw_response)
    except Exception as e:
        print(f"NVIDIA failed ({str(e)}). Switching to OpenRouter...")
        try:
            raw_response = _call_api("openrouter", FALLBACK_MODEL, system_prompt, user_content)
            return _extract_json(raw_response)
        except Exception as fallback_e:
            return {
                "error": f"NVIDIA Error: {str(e)} | Fallback Error: {str(fallback_e)}"
            }

def analyze_stock(stock_data: dict, user_question: str = None) -> dict:
    return _run_with_fallback(build_stock_system_prompt(), build_stock_user_prompt(stock_data, user_question))

def analyze_portfolio(portfolio_data: list, user_question: str = None) -> dict:
    return _run_with_fallback(build_portfolio_system_prompt(), build_portfolio_user_prompt(portfolio_data, user_question))

def analyze_mutual_fund(mf_data: dict, user_question: str = None) -> dict:
    return _run_with_fallback(build_mf_system_prompt(), build_mf_user_prompt(mf_data, user_question))
