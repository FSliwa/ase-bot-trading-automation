"""Claude-centric AI Market Analysis Module.

The analyzer now uses Claude Opus 4.1 as the primary reasoning engine and
enriches each prompt with Tavily Search intelligence before producing trading
recommendations. Downstream validation will be handled by Gemini in a separate
step.
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional, List
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import re
import logging

from anthropic import AsyncAnthropic
try:  # Optional dependency; validation gracefully degrades if unavailable
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
except ImportError:  # pragma: no cover - optional dependency on runtime
    genai = None
    HarmCategory = HarmBlockThreshold = None

from bot.db import DatabaseManager
from bot.tavily_web_search import TavilyWebSearch

logger = logging.getLogger(__name__)

# In production, this would use openai library or direct API calls

class MarketAnalyzer:
    """Handles AI-powered market analysis with Claude Opus and Tavily context."""

    def __init__(
        self,
        claude_api_key: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
    ) -> None:
        load_dotenv()

        self.claude_api_key = claude_api_key or os.getenv("CLAUDE_API_KEY")
        if not self.claude_api_key:
            raise ValueError("CLAUDE_API_KEY is not set.")

        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-3-opus-latest")
        self.claude_max_tokens = int(os.getenv("CLAUDE_MAX_TOKENS", "4096"))
        self.claude_temperature = float(os.getenv("CLAUDE_TEMPERATURE", "0.2"))

        self.claude_client = AsyncAnthropic(api_key=self.claude_api_key)

        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-pro-latest")
        self.gemini_max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))
        self.gemini_temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
        self.gemini_effective_model = self.gemini_model
        self.gemini_client = None

        if not self.gemini_api_key:
            logger.warning("GEMINI_API_KEY not configured; validation fallback disabled")
        elif not genai:
            logger.warning(
                "google-generativeai not installed; install google-generativeai to enable Gemini validation"
            )
        else:
            try:
                genai.configure(api_key=self.gemini_api_key)

                safety_settings = {
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                }

                generation_config = genai.types.GenerationConfig(
                    temperature=self.gemini_temperature,
                    max_output_tokens=self.gemini_max_tokens,
                    top_p=0.9,
                    top_k=40,
                )

                self.gemini_client = genai.GenerativeModel(
                    model_name=self.gemini_effective_model,
                    safety_settings=safety_settings,
                    generation_config=generation_config,
                )
            except Exception as exc:  # pragma: no cover - service optional
                logger.warning("Gemini validation disabled: %s", exc)
                self.gemini_client = None

        self.prompts_dir = Path(__file__).parent / "prompts"
        self.market_analysis_prompt = self._load_prompt("market_analysis_prompt.txt")
        self.trade_execution_prompt = self._load_prompt("trade_execution_prompt.txt")

        try:
            self.tavily = TavilyWebSearch(api_key=tavily_api_key)
        except ValueError as exc:
            logger.warning("Tavily Search disabled: %s", exc)
            self.tavily = None

        self.system_prompt = """You are an elite quantitative crypto strategist. Produce rigorous, data-backed
recommendations in valid JSON only. Always include reasoning, risk controls, and
clear suggested actions. If information is missing, note the gap explicitly."""
    
    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file"""
        prompt_path = self.prompts_dir / filename
        if prompt_path.exists():
            return prompt_path.read_text(encoding='utf-8')
        return ""

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from Claude response, supporting raw or fenced formats."""
        cleaned = text.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"```json\s*([\s\S]+?)\s*```", cleaned)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None

        match = re.search(r"\{[\s\S]*\}$", cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        return None

    async def _gather_market_intel(self, parameters: Dict) -> str:
        """Fetch contextual market intelligence via Tavily search."""
        if not self.tavily:
            return "Tavily search not configured."

        symbol = parameters.get("symbol") or parameters.get("pair") or parameters.get("instrument")
        try:
            if symbol:
                results = await self.tavily.search_crypto_news(symbol=symbol, max_results=8)
            else:
                results = await self.tavily.search_crypto_news(max_results=8)

            formatted = self.tavily.format_results_for_ai(results)
            return formatted or "No relevant web intelligence found."
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Tavily search failed: %s", exc)
            return f"Tavily search failed: {exc}"

    async def analyze_market(self, parameters: Dict) -> Dict:
        """Perform comprehensive market analysis using Claude Opus."""
        if not self.market_analysis_prompt:
            return {"error": "Market analysis prompt not found."}

        prompt = self.market_analysis_prompt
        for key, value in parameters.items():
            prompt = prompt.replace(f"[[{key}]]", str(value))

        market_intel = await self._gather_market_intel(parameters)

        user_prompt = "\n".join(
            [
                "[Market Parameters]",
                json.dumps(parameters, indent=2, ensure_ascii=False),
                "",
                "[Recent Market Intelligence]",
                market_intel,
                "",
                "[Analysis Instructions]",
                prompt,
            ]
        )

        try:
            response = await self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=self.claude_max_tokens,
                temperature=self.claude_temperature,
                system=self.system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt,
                            }
                        ],
                    }
                ],
            )

            text = "".join(block.text for block in response.content if hasattr(block, "text"))
            json_response = self._extract_json(text)

            if not json_response:
                return {"error": "Failed to parse JSON from AI response", "raw_content": text}

            json_response.setdefault("model_used", self.claude_model)
            json_response.setdefault("context_sources", {})
            json_response["context_sources"]["tavily_search"] = market_intel
            json_response["timestamp"] = datetime.now().isoformat()

            validation = await self._validate_with_gemini(json_response)
            json_response["validation"] = validation

            primary_symbol = (
                json_response.get("top_pick", {}) or {}
            ).get("symbol") or parameters.get("symbol", "UNKNOWN")

            with DatabaseManager() as db:
                db.record_ai_analysis(
                    symbol=str(primary_symbol),
                    model_used=json_response["model_used"],
                    recommendation=json_response.get("recommendation")
                    or json_response.get("top_pick", {}).get("action"),
                    confidence=json_response.get("confidence")
                    or (
                        json_response.get("top_pick", {}).get("confidence")
                        if isinstance(json_response.get("top_pick"), dict)
                        else None
                    ),
                    payload=json_response,
                    validation_model=validation.get("model"),
                    validation_status=validation.get("status"),
                    validation_reason=validation.get("reasoning"),
                )

            return json_response

        except Exception as exc:  # pragma: no cover - network/API failure
            logger.error("Claude market analysis failed: %s", exc)
            return {"error": f"Claude market analysis failed: {exc}"}

    async def analyze_trade_execution(self, symbol: str, side: str, parameters: Dict) -> Dict:
        """Analyze trade execution parameters using Claude Opus."""
        if not self.trade_execution_prompt:
            return {"error": "Trade execution prompt not found."}

        all_params = {
            "symbol": symbol,
            "side": side,
            **parameters,
        }

        prompt = self.trade_execution_prompt
        for key, value in all_params.items():
            prompt = prompt.replace(f"[[{key}]]", str(value))

        try:
            response = await self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=self.claude_max_tokens,
                temperature=self.claude_temperature,
                system=self.system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "\n".join(
                                    [
                                        "[Trade Parameters]",
                                        json.dumps(all_params, indent=2, ensure_ascii=False),
                                        "",
                                        "[Execution Guidance]",
                                        prompt,
                                    ]
                                ),
                            }
                        ],
                    }
                ],
            )

            text = "".join(block.text for block in response.content if hasattr(block, "text"))
            json_response = self._extract_json(text)

            if json_response:
                json_response.setdefault("model_used", self.claude_model)
                json_response["timestamp"] = datetime.now().isoformat()
                return json_response

            return {"error": "Failed to parse JSON from AI response", "raw_content": text}

        except Exception as exc:  # pragma: no cover - network/API failure
            logger.error("Claude trade execution analysis failed: %s", exc)
            return {"error": f"Claude trade execution analysis failed: {exc}"}

    async def _validate_with_gemini(self, analysis: Dict) -> Dict:
        """Validate primary analysis with Gemini using Tavily intelligence."""

        if not self.gemini_client:
            return {
                "status": "skipped",
                "reasoning": "Gemini validation unavailable",
                "risk_flags": ["gemini_not_configured"],
                "model": None,
            }

        symbol = (
            (analysis.get("top_pick") or {}).get("symbol")
            or (analysis.get("candidates") or [{}])[0].get("symbol")
            or analysis.get("symbol")
        )

        tavily_context = await self._gather_market_intel({"symbol": symbol} if symbol else {})
        analysis_snapshot = {
            "market_regime": analysis.get("market_regime"),
            "top_pick": analysis.get("top_pick"),
            "candidates": (analysis.get("candidates") or [])[:3],
            "risk_management": analysis.get("risk_management"),
            "disclaimer": analysis.get("disclaimer"),
        }

        review_prompt = (
            "You are a senior quantitative risk officer using Google Gemini with fresh market intelligence. "
            "Assess whether the following trading analysis is internally consistent, risk aware, and actionable. "
            "Respond strictly in JSON with fields: status (approve|revise|reject), reasoning (string), "
            "risk_flags (array of strings), confidence (0-1 float), and alignment_score (0-1 float).\n\n"
            "[Primary Analysis]\n"
            f"{json.dumps(analysis_snapshot, ensure_ascii=False)}\n\n"
            "[Supplementary Tavily Intelligence]\n"
            f"{tavily_context}\n\n"
            "Focus on inconsistencies, missing risk controls, or conflicts with the external intelligence."
        )

        try:
            response = await asyncio.to_thread(
                self.gemini_client.generate_content,
                review_prompt,
            )

            validation_text = getattr(response, "text", "").strip()
            validation_payload = self._extract_json(validation_text) if validation_text else None

            if not validation_payload:
                validation_payload = {
                    "status": "review",
                    "reasoning": validation_text or "Gemini returned empty response",
                    "risk_flags": ["unstructured_response"],
                }

            return {
                "status": validation_payload.get("status", "review"),
                "reasoning": validation_payload.get("reasoning")
                or validation_payload.get("justification"),
                "risk_flags": validation_payload.get("risk_flags", []),
                "confidence": validation_payload.get("confidence"),
                "alignment_score": validation_payload.get("alignment_score"),
                "model": self.gemini_effective_model,
                "context": {
                    "tavily_summary": tavily_context,
                },
            }
        except Exception as exc:  # pragma: no cover - best effort validation
            logger.warning("Gemini validation failed: %s", exc)
            return {
                "status": "review",
                "reasoning": f"Gemini validation failed: {exc}",
                "risk_flags": ["validation_error"],
                "model": self.gemini_effective_model,
            }

    def format_analysis_html(self, analysis: Dict) -> str:
        """Format analysis results for HTML display"""
        html = f"""
        <div class="analysis-report">
            <div class="analysis-header">
                <h3>Market Analysis Report</h3>
                <span class="timestamp">{analysis['as_of']}</span>
            </div>
            
            <div class="market-regime">
                <h4>Market Regime</h4>
                <div class="regime-grid">
                    <div class="regime-item">
                        <span class="label">Trend:</span>
                        <span class="value">{analysis['market_regime']['trend']}</span>
                    </div>
                    <div class="regime-item">
                        <span class="label">Volatility:</span>
                        <span class="value">{analysis['market_regime']['volatility_state']}</span>
                    </div>
                    <div class="regime-item">
                        <span class="label">Liquidity:</span>
                        <span class="value">{analysis['market_regime']['liquidity_state']}</span>
                    </div>
                    <div class="regime-item">
                        <span class="label">Confidence:</span>
                        <span class="value">{float(analysis['market_regime']['confidence'])*100:.0f}%</span>
                    </div>
                </div>
            </div>
            
            <div class="top-candidates">
                <h4>Top Trading Candidates</h4>
                <table class="candidates-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Vol 24h</th>
                            <th>Required Move</th>
                            <th>Success Prob</th>
                            <th>Entry</th>
                            <th>Stop</th>
                            <th>Targets</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for candidate in analysis['candidates'][:3]:
            html += f"""
                        <tr>
                            <td class="symbol">{candidate['symbol']}</td>
                            <td>{candidate['stats_24h']['volatility_pct']}%</td>
                            <td>{candidate['required_move_for_x5_pct']}%</td>
                            <td>{float(candidate['probability_reaching_target_24h'])*100:.0f}%</td>
                            <td class="price">{candidate['plan']['entry']}</td>
                            <td class="price stop">{candidate['plan']['invalid']}</td>
                            <td class="targets">{', '.join(candidate['plan']['tp'])}</td>
                        </tr>
            """
        
        html += """
                    </tbody>
                </table>
            </div>
            
            <div class="top-pick">
                <h4>Top Pick</h4>
                <div class="pick-card">
                    <div class="pick-symbol">{symbol}</div>
                    <div class="pick-reason">{why}</div>
                    <div class="pick-conditions">Conditions: {conditions}</div>
                    <div class="pick-confidence">Confidence: {confidence}</div>
                </div>
            </div>
            
            <div class="stress-tests">
                <h4>Stress Test Scenarios</h4>
                <div class="scenarios-grid">
        """.format(**analysis['top_pick'])
        
        for test in analysis['stress_tests']:
            html += f"""
                    <div class="scenario-card">
                        <div class="scenario-name">{test['scenario'].replace('_', ' ').title()}</div>
                        <div class="scenario-prob">Probability: {float(test['p'])*100:.0f}%</div>
                        <div class="scenario-pnl {('positive' if test['pnl_pct'].startswith('+') else 'negative')}">
                            P&L: {test['pnl_pct']}%
                        </div>
                    </div>
            """
        
        html += f"""
                </div>
            </div>
            
            <div class="disclaimer">
                <i class="fas fa-exclamation-triangle"></i>
                {analysis['disclaimer']}
            </div>
        </div>
        """
        
        return html
