"""Best-effort, privacy-minimized LLM attempt estimates, not provider invoices."""
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.database import SessionLocal

logger = get_logger(__name__)


def _tokens(usage: Any, *names: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    for name in names:
        if name in usage:
            value = usage[name]
            return value if type(value) is int and 0 <= value <= 1_000_000_000 else None
    return None


def usage_estimate(runtime: dict, data: Any) -> dict:
    usage = data.get('usage') if isinstance(data, dict) else None
    inputs = _tokens(usage, 'prompt_tokens', 'input_tokens')
    outputs = _tokens(usage, 'completion_tokens', 'output_tokens')
    prices = []
    for key in ('input_price_per_million_usd', 'output_price_per_million_usd'):
        raw = runtime.get(key)
        try:
            price = Decimal(str(raw)) if raw is not None else None
            if price is not None and (not price.is_finite() or price < 0 or price > 1000000):
                price = None
        except (InvalidOperation, ValueError):
            price = None
        prices.append(price)
    cost = None
    returned_model = data.get('model') if isinstance(data, dict) else None
    same_model = returned_model is None or (isinstance(returned_model, str) and returned_model == runtime.get('model_name'))
    if same_model and inputs is not None and outputs is not None and all(price is not None for price in prices):
        cost = (Decimal(inputs) * prices[0] + Decimal(outputs) * prices[1]) / Decimal(1_000_000)
    return {'input_tokens': inputs, 'output_tokens': outputs,
            'input_price_per_million_usd': prices[0], 'output_price_per_million_usd': prices[1],
            'estimated_cost_usd': cost}


def record_attempt(runtime: dict, task_name: str, success: bool, data: Any = None) -> None:
    """Record one HTTP attempt; failures here must never alter LLM behavior.

    Timeouts and errors without usage are deliberately unknown, not free.
    Crash or DB failures can omit attempts, so totals are always incomplete.
    """
    db = None
    try:
        values = usage_estimate(runtime, data)
        values.update({'config_id': runtime.get('config_id'), 'provider': runtime.get('provider') or 'unknown',
                       'model_name': runtime.get('model_name') or 'unknown',
                       'task_name': task_name[:200], 'http_success': success})
        db = SessionLocal()
        db.execute(text("""
            INSERT INTO app_private.llm_usage_attempts
                (config_id, provider, model_name, task_name, http_success, input_tokens, output_tokens,
                 input_price_per_million_usd, output_price_per_million_usd, estimated_cost_usd)
            VALUES (:config_id, :provider, :model_name, :task_name, :http_success, :input_tokens, :output_tokens,
                    :input_price_per_million_usd, :output_price_per_million_usd, :estimated_cost_usd)
        """), values)
        db.commit()
    except Exception as exc:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        logger.warning('LLM usage telemetry unavailable', error_type=type(exc).__name__)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
