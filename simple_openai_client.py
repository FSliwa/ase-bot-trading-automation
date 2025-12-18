#!/usr/bin/env python3
"""
Simple OpenAI API Client using only requests library
Compatible with GPT-5 API
"""

import json
import os
import requests
from typing import Dict, List, Optional


class SimpleOpenAIClient:
    """Simple OpenAI API client using requests library"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def chat_completion(self, 
                       model: str = "gpt-5",
                       messages: List[Dict] = None,
                       temperature: float = 0.3,
                       max_tokens: int = 1000,
                       top_p: float = 0.9,
                       frequency_penalty: float = 0.0,
                       presence_penalty: float = 0.0) -> Dict:
        """
        Send chat completion request to OpenAI API
        """
        if messages is None:
            messages = []
        
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            # Fallback to GPT-4o if GPT-5 not available
            if "model" in str(e).lower() or response.status_code in [400, 404]:
                payload["model"] = "gpt-4o"
                try:
                    response = requests.post(url, headers=self.headers, json=payload, timeout=30)
                    response.raise_for_status()
                    result = response.json()
                    # Mark that we used fallback model
                    result["fallback_used"] = True
                    result["original_model"] = "gpt-5"
                    return result
                except Exception as fallback_error:
                    return {
                        "error": {
                            "message": f"OpenAI API Error (both GPT-5 and GPT-4o failed): {str(fallback_error)}",
                            "type": "api_error"
                        }
                    }
            
            return {
                "error": {
                    "message": f"OpenAI API Error: {str(e)}",
                    "type": "api_error"
                }
            }


def test_gpt5_integration():
    """Test GPT-5 integration"""
    print("🧪 Testing GPT-5 Integration...")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("❌ OPENAI_API_KEY not configured")
        return False
    
    client = SimpleOpenAIClient(api_key)
    
    # Test message
    messages = [
        {"role": "system", "content": "You are an AI trading assistant powered by GPT-5."},
        {"role": "user", "content": "Analyze Bitcoin market conditions briefly."}
    ]
    
    print("📡 Sending request to GPT-5 API...")
    response = client.chat_completion(
        model="gpt-5",
        messages=messages,
        temperature=0.3,
        max_tokens=200
    )
    
    if "error" in response:
        print(f"❌ Error: {response['error']['message']}")
        return False
    
    if "choices" in response and response["choices"]:
        content = response["choices"][0]["message"]["content"]
        model_used = response.get("model", "unknown")
        print(f"✅ Success! Model: {model_used}")
        print(f"📈 Response: {content[:100]}...")
        return True
    
    print("❌ Unexpected response format")
    return False


if __name__ == "__main__":
    test_gpt5_integration()
