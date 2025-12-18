"""
AI Portfolio Evaluator Service - AI-powered portfolio evaluation for signal suitability.

This service uses AI (Grok 4.1 via xAI) to evaluate whether a given trading signal
is suitable for a specific user based on their portfolio state, margin, exposure, etc.

Key features:
1. Evaluates if a global signal (user_id=NULL) should be executed for a specific user
2. Considers margin levels, current positions, exposure, and risk profile
3. Returns detailed reasoning for the decision
"""

import logging
import json
import os
import httpx
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# xAI Grok API Configuration
XAI_API_KEY = "xai-vwcXoY07OZJeMUYY4yrR6p5fJszDoGh2PWEFAIEH3u6zZOnRT9tRNYEI6vOwPqx30wZrfckeA2ijyxCw"
XAI_API_URL = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-3-fast"  # Fast reasoning model


@dataclass
class PortfolioState:
    """Current state of user's portfolio."""
    user_id: str
    exchange: str
    total_balance_usd: float
    available_balance_usd: float
    margin_used_usd: float
    margin_level_percent: float  # 100% = healthy, <100% = margin call risk
    positions: List[Dict]  # List of open positions
    position_count: int
    largest_position_percent: float  # % of portfolio in largest position
    category_exposures: Dict[str, float]  # Category -> % exposure
    stable_reserve_percent: float  # % in stablecoins
    daily_pnl_percent: float
    weekly_pnl_percent: float
    risk_level: int  # 1-5 from user settings


@dataclass
class SignalEvaluation:
    """Result of AI signal evaluation."""
    signal_id: str
    symbol: str
    action: str
    should_execute: bool
    confidence: float  # 0.0-1.0
    position_size_multiplier: float  # 0.0-1.5 (reduce, normal, or increase)
    reasons: List[str]
    ai_reasoning: str
    risk_assessment: str  # "low", "medium", "high", "critical"
    warnings: List[str]
    evaluated_at: datetime = field(default_factory=datetime.now)


class AIPortfolioEvaluator:
    """
    AI-powered service to evaluate if a trading signal is suitable for a user.
    Uses xAI Grok 4.1 Fast Reasoning to analyze portfolio state and make recommendations.
    """
    
    # Risk thresholds
    MARGIN_CRITICAL_LEVEL = 120.0  # Below this = critical risk
    MARGIN_WARNING_LEVEL = 150.0   # Below this = warning
    MAX_POSITION_COUNT = 10        # Max concurrent positions
    MAX_SINGLE_EXPOSURE = 40.0     # Max 40% in single position
    MIN_STABLE_RESERVE = 5.0       # Min 5% in stables (relaxed)
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or XAI_API_KEY
        self.api_url = XAI_API_URL
        self.model = GROK_MODEL
        
        if not self.api_key:
            logger.warning("No xAI API key - AI evaluation will use rule-based fallback")
        else:
            logger.info(f"✅ AI Portfolio Evaluator initialized with Grok ({self.model})")
    
    async def _call_grok_api(self, messages: List[Dict]) -> Optional[Dict]:
        """Call xAI Grok API."""
        try:
            import aiohttp
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "messages": messages,
                "model": self.model,
                "stream": False,
                "temperature": 0.3,  # Low for consistent decisions
                "max_tokens": 500
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data['choices'][0]['message']['content']
                        
                        # Try to parse as JSON
                        try:
                            # Clean up potential markdown formatting
                            if '```json' in content:
                                content = content.split('```json')[1].split('```')[0]
                            elif '```' in content:
                                content = content.split('```')[1].split('```')[0]
                            
                            return json.loads(content.strip())
                        except json.JSONDecodeError:
                            # Try to extract JSON from response
                            import re
                            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                            if json_match:
                                return json.loads(json_match.group())
                            logger.warning(f"Could not parse Grok response as JSON: {content[:200]}")
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(f"Grok API error {response.status}: {error_text}")
                        return None
                        
        except ImportError:
            # Fallback to requests if aiohttp not available
            import requests
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "messages": messages,
                "model": self.model,
                "stream": False,
                "temperature": 0.3,
                "max_tokens": 500
            }
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                try:
                    if '```json' in content:
                        content = content.split('```json')[1].split('```')[0]
                    elif '```' in content:
                        content = content.split('```')[1].split('```')[0]
                    return json.loads(content.strip())
                except json.JSONDecodeError:
                    import re
                    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                    return None
            else:
                logger.error(f"Grok API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Grok API call failed: {e}")
            return None
    
    async def evaluate_signal_for_user(
        self,
        signal: Dict,
        portfolio_state: PortfolioState,
        market_conditions: Optional[Dict] = None
    ) -> SignalEvaluation:
        """
        Evaluate if a trading signal should be executed for a specific user.
        
        Uses AI (Grok 4.1) to analyze:
        1. Current portfolio composition and exposure
        2. Margin level and available capital
        3. Risk profile of the user
        4. Market conditions
        5. Signal characteristics (symbol, action, confidence)
        
        Returns detailed evaluation with recommendation.
        """
        symbol = signal.get('symbol', '')
        action = signal.get('action', '').upper()
        signal_confidence = signal.get('confidence', 0.5)
        signal_id = signal.get('signal_id', '')
        
        # First, apply quick rule-based checks
        quick_result = self._quick_rule_check(signal, portfolio_state)
        if quick_result is not None:
            return quick_result
        
        # Use AI for detailed evaluation
        if self.api_key:
            try:
                return await self._ai_evaluate(signal, portfolio_state, market_conditions)
            except Exception as e:
                logger.warning(f"AI evaluation failed, using rule-based: {e}")
        
        # Fallback to rule-based evaluation
        return self._rule_based_evaluate(signal, portfolio_state)
    
    def _quick_rule_check(
        self,
        signal: Dict,
        state: PortfolioState
    ) -> Optional[SignalEvaluation]:
        """
        Quick rule-based checks that don't require AI.
        Returns evaluation if signal should be immediately rejected.
        """
        symbol = signal.get('symbol', '')
        action = signal.get('action', '').upper()
        signal_id = signal.get('signal_id', '')
        
        warnings = []
        
        # Check 1: Critical margin level
        if state.margin_level_percent < self.MARGIN_CRITICAL_LEVEL:
            return SignalEvaluation(
                signal_id=signal_id,
                symbol=symbol,
                action=action,
                should_execute=False,
                confidence=0.0,
                position_size_multiplier=0.0,
                reasons=["❌ CRITICAL: Margin level too low for new positions"],
                ai_reasoning=f"Margin level at {state.margin_level_percent:.1f}% is below critical threshold of {self.MARGIN_CRITICAL_LEVEL}%",
                risk_assessment="critical",
                warnings=["Margin call risk - consider closing positions"]
            )
        
        # Check 2: No available balance for BUY
        if action == "BUY" and state.available_balance_usd < 10:
            return SignalEvaluation(
                signal_id=signal_id,
                symbol=symbol,
                action=action,
                should_execute=False,
                confidence=0.0,
                position_size_multiplier=0.0,
                reasons=["❌ Insufficient balance for new BUY position"],
                ai_reasoning=f"Available balance ${state.available_balance_usd:.2f} is too low",
                risk_assessment="high",
                warnings=["No available capital"]
            )
        
        # Check 3: Too many positions
        if state.position_count >= self.MAX_POSITION_COUNT and action == "BUY":
            return SignalEvaluation(
                signal_id=signal_id,
                symbol=symbol,
                action=action,
                should_execute=False,
                confidence=0.0,
                position_size_multiplier=0.0,
                reasons=[f"❌ Max positions ({self.MAX_POSITION_COUNT}) reached"],
                ai_reasoning="Portfolio already has maximum number of positions. Close some before opening new ones.",
                risk_assessment="medium",
                warnings=["Consider consolidating positions"]
            )
        
        # Check 4: Already have large position in this symbol
        base_symbol = symbol.split('/')[0] if '/' in symbol else symbol
        for pos in state.positions:
            pos_symbol = pos.get('symbol', '').split('/')[0]
            if pos_symbol == base_symbol:
                pos_value = pos.get('value_usd', 0)
                pos_percent = (pos_value / state.total_balance_usd * 100) if state.total_balance_usd > 0 else 0
                
                if pos_percent > self.MAX_SINGLE_EXPOSURE:
                    if action == "BUY":
                        return SignalEvaluation(
                            signal_id=signal_id,
                            symbol=symbol,
                            action=action,
                            should_execute=False,
                            confidence=0.0,
                            position_size_multiplier=0.0,
                            reasons=[f"❌ Already over-exposed to {base_symbol} ({pos_percent:.1f}%)"],
                            ai_reasoning=f"Position in {base_symbol} is {pos_percent:.1f}% of portfolio, exceeds {self.MAX_SINGLE_EXPOSURE}% limit",
                            risk_assessment="high",
                            warnings=[f"Consider reducing {base_symbol} exposure"]
                        )
        
        return None  # No immediate rejection, proceed with detailed evaluation
    
    async def _ai_evaluate(
        self,
        signal: Dict,
        state: PortfolioState,
        market_conditions: Optional[Dict]
    ) -> SignalEvaluation:
        """Use Grok 4.1 for detailed signal evaluation."""
        
        # Build prompt with portfolio context
        prompt = self._build_evaluation_prompt(signal, state, market_conditions)
        
        system_prompt = """You are an expert crypto trading risk analyst. 
Evaluate trading signals based on portfolio state and provide actionable recommendations.
Always respond ONLY with valid JSON (no markdown, no explanation outside JSON) with these fields:
- should_execute: boolean
- confidence: float 0.0-1.0
- position_size_multiplier: float 0.0-1.5 (0.5=half size, 1.0=normal, 1.5=increase)
- risk_assessment: "low"|"medium"|"high"|"critical"
- reasoning: string (detailed analysis)
- warnings: array of strings
- reasons: array of strings (key decision factors)"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        try:
            result = await self._call_grok_api(messages)
            
            if result is None:
                logger.warning("Grok API returned None, using rule-based evaluation")
                return self._rule_based_evaluate(signal, state)
            
            return SignalEvaluation(
                signal_id=signal.get('signal_id', ''),
                symbol=signal.get('symbol', ''),
                action=signal.get('action', '').upper(),
                should_execute=result.get('should_execute', False),
                confidence=result.get('confidence', 0.5),
                position_size_multiplier=result.get('position_size_multiplier', 1.0),
                reasons=result.get('reasons', []),
                ai_reasoning=result.get('reasoning', ''),
                risk_assessment=result.get('risk_assessment', 'medium'),
                warnings=result.get('warnings', [])
            )
            
        except Exception as e:
            logger.error(f"Grok AI evaluation error: {e}")
            return self._rule_based_evaluate(signal, state)
    
    def _build_evaluation_prompt(
        self,
        signal: Dict,
        state: PortfolioState,
        market_conditions: Optional[Dict]
    ) -> str:
        """Build detailed prompt for AI evaluation."""
        
        # Format positions
        positions_str = ""
        for pos in state.positions[:5]:  # Limit to 5 for token efficiency
            positions_str += f"  - {pos.get('symbol')}: ${pos.get('value_usd', 0):.2f} ({pos.get('pnl_percent', 0):.1f}% P&L)\n"
        
        # Format exposures
        exposures_str = ", ".join([f"{k}: {v:.1f}%" for k, v in state.category_exposures.items()])
        
        prompt = f"""
## Trading Signal Evaluation Request

### Signal Details:
- Symbol: {signal.get('symbol')}
- Action: {signal.get('action')}
- Signal Confidence: {signal.get('confidence', 0.5):.0%}
- Entry Price: {signal.get('entry_price', 'N/A')}
- Stop Loss: {signal.get('stop_loss', 'N/A')}
- Take Profit: {signal.get('take_profit', 'N/A')}
- Source: {signal.get('source', 'unknown')}
- Reasoning: {signal.get('reasoning', 'N/A')[:200]}

### User Portfolio State:
- Exchange: {state.exchange}
- Total Balance: ${state.total_balance_usd:.2f}
- Available Balance: ${state.available_balance_usd:.2f}
- Margin Used: ${state.margin_used_usd:.2f}
- Margin Level: {state.margin_level_percent:.1f}%
- Open Positions: {state.position_count}
- Largest Position: {state.largest_position_percent:.1f}% of portfolio
- Stable Reserve: {state.stable_reserve_percent:.1f}%
- Daily P&L: {state.daily_pnl_percent:+.2f}%
- User Risk Level: {state.risk_level}/5

### Current Positions:
{positions_str if positions_str else "  (No positions)"}

### Category Exposures:
{exposures_str if exposures_str else "  (No exposures)"}

### Evaluation Criteria:
1. Is the signal suitable for this user's risk profile?
2. Does the user have sufficient capital/margin?
3. Would this trade over-concentrate the portfolio?
4. What position size is appropriate (0.5x-1.5x)?
5. What are the key risks to consider?

Please evaluate and provide JSON recommendation.
"""
        return prompt
    
    def _rule_based_evaluate(
        self,
        signal: Dict,
        state: PortfolioState
    ) -> SignalEvaluation:
        """Fallback rule-based evaluation when AI is not available."""
        symbol = signal.get('symbol', '')
        action = signal.get('action', '').upper()
        signal_id = signal.get('signal_id', '')
        signal_confidence = signal.get('confidence', 0.5)
        
        reasons = []
        warnings = []
        should_execute = True
        multiplier = 1.0
        risk_assessment = "medium"
        
        # Rule 1: Margin level adjustments
        if state.margin_level_percent < self.MARGIN_WARNING_LEVEL:
            multiplier *= 0.5
            warnings.append(f"⚠️ Low margin ({state.margin_level_percent:.0f}%) - reduced size")
            risk_assessment = "high"
        
        # Rule 2: Position count adjustments
        if state.position_count >= 5:
            multiplier *= 0.7
            warnings.append(f"⚠️ Many positions ({state.position_count}) - reduced size")
        
        # Rule 3: Available balance check
        balance_pct = (state.available_balance_usd / state.total_balance_usd * 100) if state.total_balance_usd > 0 else 0
        if balance_pct < 20:
            multiplier *= 0.6
            warnings.append(f"⚠️ Low available balance ({balance_pct:.0f}%) - reduced size")
        
        # Rule 4: Risk level adjustments
        if state.risk_level <= 2:  # Conservative
            multiplier *= 0.7
            reasons.append("Conservative risk profile - smaller position")
        elif state.risk_level >= 4:  # Aggressive
            multiplier *= 1.2
            reasons.append("Aggressive risk profile - larger position allowed")
        
        # Rule 5: High confidence signals
        if signal_confidence > 0.8:
            multiplier *= 1.1
            reasons.append(f"High confidence signal ({signal_confidence:.0%})")
        elif signal_confidence < 0.5:
            multiplier *= 0.8
            reasons.append(f"Low confidence signal ({signal_confidence:.0%}) - reduced size")
        
        # Rule 6: Daily P&L consideration
        if state.daily_pnl_percent < -5:
            multiplier *= 0.7
            warnings.append(f"⚠️ Bad day ({state.daily_pnl_percent:+.1f}% P&L) - reduced exposure")
            risk_assessment = "high"
        
        # Clamp multiplier
        multiplier = max(0.3, min(1.5, multiplier))
        
        # Final decision
        if multiplier < 0.5:
            should_execute = False
            reasons.append("Position size too small after adjustments")
        else:
            reasons.append(f"✅ Signal approved with {multiplier:.0%} size")
        
        return SignalEvaluation(
            signal_id=signal_id,
            symbol=symbol,
            action=action,
            should_execute=should_execute,
            confidence=signal_confidence * multiplier,
            position_size_multiplier=multiplier,
            reasons=reasons,
            ai_reasoning="Rule-based evaluation (AI fallback)",
            risk_assessment=risk_assessment,
            warnings=warnings
        )
    
    async def get_portfolio_state(
        self,
        user_id: str,
        exchange_adapter,
        user_settings: Optional[Dict] = None
    ) -> PortfolioState:
        """
        Build PortfolioState from exchange data.
        """
        try:
            # Fetch balance
            balance = await exchange_adapter.get_all_balances()
            
            # Calculate totals
            total_usd = 0.0
            available_usd = 0.0
            stable_usd = 0.0
            
            for asset, amount in balance.items():
                if isinstance(amount, dict):
                    free = amount.get('free', 0) or 0
                    total = amount.get('total', free) or free
                else:
                    free = amount
                    total = amount
                
                # For stablecoins, 1:1 USD value
                if asset in ('USDT', 'USDC', 'USD', 'DAI', 'BUSD'):
                    total_usd += total
                    available_usd += free
                    stable_usd += total
            
            # Fetch positions
            positions = []
            try:
                raw_positions = await exchange_adapter.get_positions()
                for pos in raw_positions:
                    if hasattr(pos, '__dict__'):
                        positions.append({
                            'symbol': getattr(pos, 'symbol', ''),
                            'value_usd': getattr(pos, 'notional', 0) or 0,
                            'pnl_percent': getattr(pos, 'unrealized_pnl_percent', 0) or 0,
                            'quantity': getattr(pos, 'quantity', 0) or 0
                        })
                    elif isinstance(pos, dict):
                        positions.append(pos)
            except Exception as e:
                logger.warning(f"Could not fetch positions: {e}")
            
            # Calculate position metrics
            position_values = [p.get('value_usd', 0) for p in positions]
            largest_position_pct = (max(position_values) / total_usd * 100) if total_usd > 0 and position_values else 0
            
            # Build category exposures (simplified)
            category_exposures = {}
            
            # Margin level (default healthy if no margin used)
            margin_used = sum(position_values)
            margin_level = (total_usd / margin_used * 100) if margin_used > 0 else 999.0
            
            # User risk level
            risk_level = user_settings.get('risk_level', 3) if user_settings else 3
            
            return PortfolioState(
                user_id=user_id,
                exchange=getattr(exchange_adapter, 'exchange_id', 'unknown'),
                total_balance_usd=total_usd,
                available_balance_usd=available_usd,
                margin_used_usd=margin_used,
                margin_level_percent=margin_level,
                positions=positions,
                position_count=len(positions),
                largest_position_percent=largest_position_pct,
                category_exposures=category_exposures,
                stable_reserve_percent=(stable_usd / total_usd * 100) if total_usd > 0 else 0,
                daily_pnl_percent=0.0,  # Would need historical data
                weekly_pnl_percent=0.0,
                risk_level=risk_level
            )
            
        except Exception as e:
            logger.error(f"Failed to get portfolio state: {e}")
            # Return default state
            return PortfolioState(
                user_id=user_id,
                exchange="unknown",
                total_balance_usd=0,
                available_balance_usd=0,
                margin_used_usd=0,
                margin_level_percent=100,
                positions=[],
                position_count=0,
                largest_position_percent=0,
                category_exposures={},
                stable_reserve_percent=0,
                daily_pnl_percent=0,
                weekly_pnl_percent=0,
                risk_level=3
            )


# Singleton instance
_evaluator_instance: Optional[AIPortfolioEvaluator] = None

def get_ai_portfolio_evaluator() -> AIPortfolioEvaluator:
    """Get singleton AI Portfolio Evaluator instance."""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = AIPortfolioEvaluator()
    return _evaluator_instance
