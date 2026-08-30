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
PRIMARY_MODEL = "meta/llama-3.2-90b-vision-instruct"

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

    # Step 1: Strip ALL <think>...</think> blocks (Nemotron reasoning traces)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Step 2: Try to grab clean ```json ... ``` block first
    json_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass

    # Step 3: Strip all remaining ``` markers
    text = re.sub(r'```[a-zA-Z]*', '', text).replace('```', '').strip()

    # Step 4: Direct parse attempt
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ✅ Step 4b: Repair common NVIDIA response issues
    try:
        # Fix unescaped newlines inside string values
        repaired = re.sub(r'(?<!\\)\n', ' ', text)
        # Fix unescaped double quotes inside values (e.g. he said "hello")
        repaired = re.sub(r'(?<=[a-zA-Z])"(?=[a-zA-Z])', '\\"', repaired)
        # Fix trailing commas before } or ]
        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Step 5: Find the LARGEST valid { } block in the text
    best = None
    start = 0
    while True:
        s = text.find('{', start)
        if s == -1:
            break
        depth = 0
        for i in range(s, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[s:i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if best is None or len(candidate) > len(str(best)):
                            best = parsed
                    except json.JSONDecodeError:
                        pass
                    break
        start = s + 1

    if best:
        return best

    # ✅ Step 6: Last resort — apply repair on each candidate block too
    start = 0
    while True:
        s = text.find('{', start)
        if s == -1:
            break
        depth = 0
        for i in range(s, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[s:i+1]
                    try:
                        repaired = re.sub(r'(?<!\\)\n', ' ', candidate)
                        repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
                        parsed = json.loads(repaired)
                        if best is None or len(candidate) > len(str(best)):
                            best = parsed
                    except json.JSONDecodeError:
                        pass
                    break
        start = s + 1

    if best:
        return best

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

def chat_market_advisor(messages: list) -> dict:
    """
    Conversational market advisor — takes full message history,
    returns { message: str, stocks: [] }
    """
    system_prompt = """You are an expert Indian Stock Market Analyst with 20 years of experience.
Your job is to guide users to find the best stocks through natural conversation.

CONVERSATION RULES:
1. Ask ONE smart question at a time to narrow down their investment profile
2. Cover: investment goal, sector interest, risk appetite, budget, time horizon
3. After 3-5 exchanges you have enough info — give recommendations
4. NEVER recommend before asking at least 2-3 questions

OUTPUT FORMAT — follow this EXACTLY, no exceptions:

When you are NOT ready to recommend yet, reply with plain conversational text only.
Example:
  That sounds great! What is your risk appetite — Low, Medium, or High?

When you ARE ready to recommend, reply in this EXACT structure:
  [Your friendly summary message here — plain text, NO JSON here]
  <RECOMMENDATIONS>
  {"stocks":[{"symbol":"HAL","name":"Hindustan Aeronautics Limited","reason":"Strong order book"},{"symbol":"BEL","name":"Bharat Electronics Limited","reason":"Defence electronics leader"}]}
  </RECOMMENDATIONS>

STRICT RULES FOR RECOMMENDATIONS:
- The text BEFORE <RECOMMENDATIONS> must be plain conversational English — NO JSON, NO brackets, NO quotes
- ALL stock data goes INSIDE <RECOMMENDATIONS> tags — nowhere else
- Only NSE-listed Indian stocks
- Maximum 6 stocks
- Do NOT write the JSON anywhere outside the <RECOMMENDATIONS> block"""
   
    # ── Build base payload ────────────────────────────────
    base_messages = [
        {"role": "system", "content": system_prompt},
        *messages
    ]

    raw_reply = None

    # ── Try NVIDIA first ──────────────────────────────────
    if NVIDIA_API_KEY:
        try:
            print("Calling NVIDIA for market advisor...")
            nvidia_payload = {
                "model": PRIMARY_MODEL,
                "messages": base_messages,
                "temperature": 0.7,
                "max_tokens": 1024,
                "stream": False
            }
            headers = {
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
                "Content-Type": "application/json"
            }
            response = requests.post(
                NVIDIA_URL,
                headers=headers,
                json=nvidia_payload,
                timeout=25
            )
            if response.ok:
                raw_reply = response.json()["choices"][0]["message"]["content"]
                print("NVIDIA advisor success")
            else:
                print(f"NVIDIA advisor failed ({response.status_code}), trying OpenRouter...")
        except Exception as e:
            print(f"NVIDIA advisor exception: {str(e)}, trying OpenRouter...")

    # ── Fallback to OpenRouter ────────────────────────────
    if raw_reply is None and OPENROUTER_API_KEY:
        try:
            print("Calling OpenRouter for market advisor...")
            openrouter_payload = {
                "model": FALLBACK_MODEL,
                "messages": base_messages,
                "temperature": 0.7,
                "max_tokens": 1024,
                "stream": False
            }
            headers2 = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ai-financial-production.up.railway.app",
                "X-Title": "AI Financial Advisor"
            }
            response = requests.post(
                OPENROUTER_URL,
                headers=headers2,
                json=openrouter_payload,
                timeout=60
            )
            response.raise_for_status()
            raw_reply = response.json()["choices"][0]["message"]["content"]
            print("OpenRouter advisor success")
        except Exception as e:
            raise Exception(f"Both APIs failed. Last error: {str(e)}")

    if not raw_reply:
        raise Exception("No response from any API")

    # ── Parse out stock recommendations ──────────────────
    stocks = []
    clean_message = raw_reply.strip()

    # Strip <think> blocks if present
    clean_message = re.sub(r'<think>.*?</think>', '', clean_message, flags=re.DOTALL).strip()

    if "<RECOMMENDATIONS>" in clean_message and "</RECOMMENDATIONS>" in clean_message:
        # Split on the tag
        before = clean_message.split("<RECOMMENDATIONS>")[0].strip()
        inside = clean_message.split("<RECOMMENDATIONS>")[1].split("</RECOMMENDATIONS>")[0].strip()

        # Clean message is everything BEFORE the tag
        clean_message = before

        # Parse the JSON inside the tag
        try:
            # Handle both compact and pretty-printed JSON
            rec_data = json.loads(inside)
            stocks = rec_data.get("stocks", [])
        except json.JSONDecodeError:
            # Try to find { } block inside
            s = inside.find("{")
            e = inside.rfind("}")
            if s != -1 and e != -1:
                try:
                    rec_data = json.loads(inside[s:e+1])
                    stocks = rec_data.get("stocks", [])
                except Exception as pe:
                    print(f"Stock JSON parse failed: {str(pe)}")

    # Final cleanup — if clean_message still has JSON-like content, strip it
    # This catches cases where model leaks JSON into the message
    if clean_message.strip().startswith("{") or clean_message.strip().startswith("["):
        clean_message = "Here are my top stock recommendations based on your profile:"

    return {
        "message": clean_message,
        "stocks": stocks
    }

def analyze_stock(stock_data: dict, user_question: str = None) -> dict:
    return _run_with_fallback(build_stock_system_prompt(), build_stock_user_prompt(stock_data, user_question))

def analyze_portfolio(portfolio_data: list, user_question: str = None) -> dict:
    return _run_with_fallback(build_portfolio_system_prompt(), build_portfolio_user_prompt(portfolio_data, user_question))

def analyze_mutual_fund(mf_data: dict, user_question: str = None) -> dict:
    return _run_with_fallback(build_mf_system_prompt(), build_mf_user_prompt(mf_data, user_question))
