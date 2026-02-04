"""
Model Token Limits Configuration

Defines context window sizes and token limits for all supported LLMs.
This enables the agent to manage context budgets and avoid overflow.
"""

from dataclasses import dataclass
from typing import Dict, Optional
from functools import lru_cache


@dataclass
class ModelLimits:
    """Token limits and configuration for an LLM model."""
    model_id: str
    context_window: int  # Total context window
    max_output_tokens: int  # Maximum response tokens
    input_reserve: int  # Reserved for system prompt + overhead
    tokenizer: str  # Tokenizer type: "cl100k_base", "o200k_base", "claude", etc.
    cost_per_1k_input: float  # USD per 1K input tokens
    cost_per_1k_output: float  # USD per 1K output tokens
    supports_vision: bool = False
    supports_function_calling: bool = True
    
    @property
    def effective_input_limit(self) -> int:
        """Max tokens available for user content after reserves."""
        return self.context_window - self.max_output_tokens - self.input_reserve


# ============================================================================
# MODEL LIMITS REGISTRY
# ============================================================================
MODEL_LIMITS: Dict[str, ModelLimits] = {
    # =========================================================================
    # OpenAI Models
    # =========================================================================
    "gpt-4-turbo": ModelLimits(
        model_id="gpt-4-turbo",
        context_window=128_000,
        max_output_tokens=4_096,
        input_reserve=2_000,
        tokenizer="cl100k_base",
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        supports_vision=True
    ),
    "gpt-4-turbo-preview": ModelLimits(
        model_id="gpt-4-turbo-preview",
        context_window=128_000,
        max_output_tokens=4_096,
        input_reserve=2_000,
        tokenizer="cl100k_base",
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        supports_vision=True
    ),
    "gpt-4.1": ModelLimits(
        model_id="gpt-4.1",
        context_window=128_000,
        max_output_tokens=16_384,
        input_reserve=2_000,
        tokenizer="cl100k_base",
        cost_per_1k_input=0.002,
        cost_per_1k_output=0.008,
        supports_vision=True
    ),
    "gpt-4o": ModelLimits(
        model_id="gpt-4o",
        context_window=128_000,
        max_output_tokens=16_384,
        input_reserve=2_000,
        tokenizer="o200k_base",
        cost_per_1k_input=0.0025,
        cost_per_1k_output=0.01,
        supports_vision=True
    ),
    "gpt-4o-mini": ModelLimits(
        model_id="gpt-4o-mini",
        context_window=128_000,
        max_output_tokens=16_384,
        input_reserve=1_000,
        tokenizer="o200k_base",
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
        supports_vision=True
    ),
    "gpt-4": ModelLimits(
        model_id="gpt-4",
        context_window=8_192,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="cl100k_base",
        cost_per_1k_input=0.03,
        cost_per_1k_output=0.06,
        supports_vision=False
    ),
    "gpt-4-32k": ModelLimits(
        model_id="gpt-4-32k",
        context_window=32_768,
        max_output_tokens=4_096,
        input_reserve=2_000,
        tokenizer="cl100k_base",
        cost_per_1k_input=0.06,
        cost_per_1k_output=0.12,
        supports_vision=False
    ),
    "gpt-3.5-turbo": ModelLimits(
        model_id="gpt-3.5-turbo",
        context_window=16_385,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="cl100k_base",
        cost_per_1k_input=0.0005,
        cost_per_1k_output=0.0015,
        supports_vision=False
    ),
    "o1-preview": ModelLimits(
        model_id="o1-preview",
        context_window=128_000,
        max_output_tokens=32_768,
        input_reserve=5_000,
        tokenizer="o200k_base",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.06,
        supports_vision=False,
        supports_function_calling=False
    ),
    "o1-mini": ModelLimits(
        model_id="o1-mini",
        context_window=128_000,
        max_output_tokens=65_536,
        input_reserve=3_000,
        tokenizer="o200k_base",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.012,
        supports_vision=False,
        supports_function_calling=False
    ),
    
    # =========================================================================
    # Anthropic Models
    # =========================================================================
    "claude-3-opus": ModelLimits(
        model_id="claude-3-opus",
        context_window=200_000,
        max_output_tokens=4_096,
        input_reserve=3_000,
        tokenizer="claude",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        supports_vision=True
    ),
    "claude-3-opus-20240229": ModelLimits(
        model_id="claude-3-opus-20240229",
        context_window=200_000,
        max_output_tokens=4_096,
        input_reserve=3_000,
        tokenizer="claude",
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        supports_vision=True
    ),
    "claude-3.5-sonnet": ModelLimits(
        model_id="claude-3.5-sonnet",
        context_window=200_000,
        max_output_tokens=8_192,
        input_reserve=2_000,
        tokenizer="claude",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_vision=True
    ),
    "claude-3-5-sonnet-20241022": ModelLimits(
        model_id="claude-3-5-sonnet-20241022",
        context_window=200_000,
        max_output_tokens=8_192,
        input_reserve=2_000,
        tokenizer="claude",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_vision=True
    ),
    "claude-3.7-sonnet": ModelLimits(
        model_id="claude-3.7-sonnet",
        context_window=200_000,
        max_output_tokens=16_000,
        input_reserve=3_000,
        tokenizer="claude",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_vision=True
    ),
    "claude-3.7-sonnet-thinking": ModelLimits(
        model_id="claude-3.7-sonnet-thinking",
        context_window=200_000,
        max_output_tokens=16_000,
        input_reserve=5_000,  # Extra reserve for thinking
        tokenizer="claude",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_vision=True
    ),
    "claude-3-sonnet": ModelLimits(
        model_id="claude-3-sonnet",
        context_window=200_000,
        max_output_tokens=4_096,
        input_reserve=2_000,
        tokenizer="claude",
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_vision=True
    ),
    "claude-3-haiku": ModelLimits(
        model_id="claude-3-haiku",
        context_window=200_000,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="claude",
        cost_per_1k_input=0.00025,
        cost_per_1k_output=0.00125,
        supports_vision=True
    ),
    
    # =========================================================================
    # Google Models
    # =========================================================================
    "gemini-1.5-pro": ModelLimits(
        model_id="gemini-1.5-pro",
        context_window=1_000_000,
        max_output_tokens=8_192,
        input_reserve=5_000,
        tokenizer="gemini",
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.005,
        supports_vision=True
    ),
    "gemini-1.5-flash": ModelLimits(
        model_id="gemini-1.5-flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        input_reserve=3_000,
        tokenizer="gemini",
        cost_per_1k_input=0.000075,
        cost_per_1k_output=0.0003,
        supports_vision=True
    ),
    "gemini-2.0-flash": ModelLimits(
        model_id="gemini-2.0-flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        input_reserve=3_000,
        tokenizer="gemini",
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0004,
        supports_vision=True
    ),
    
    # =========================================================================
    # Open Source Models (via LiteLLM/vLLM/Ollama)
    # =========================================================================
    "llama-3.1-70b": ModelLimits(
        model_id="llama-3.1-70b",
        context_window=128_000,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="llama3",
        cost_per_1k_input=0.0008,
        cost_per_1k_output=0.0008,
        supports_vision=False
    ),
    "llama-3.1-8b": ModelLimits(
        model_id="llama-3.1-8b",
        context_window=128_000,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="llama3",
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0001,
        supports_vision=False
    ),
    "llama-3.2-90b-vision": ModelLimits(
        model_id="llama-3.2-90b-vision",
        context_window=128_000,
        max_output_tokens=4_096,
        input_reserve=2_000,
        tokenizer="llama3",
        cost_per_1k_input=0.002,
        cost_per_1k_output=0.002,
        supports_vision=True
    ),
    "mistral-large": ModelLimits(
        model_id="mistral-large",
        context_window=128_000,
        max_output_tokens=8_192,
        input_reserve=1_000,
        tokenizer="mistral",
        cost_per_1k_input=0.002,
        cost_per_1k_output=0.006,
        supports_vision=False
    ),
    "mistral-medium": ModelLimits(
        model_id="mistral-medium",
        context_window=32_000,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="mistral",
        cost_per_1k_input=0.0027,
        cost_per_1k_output=0.0081,
        supports_vision=False
    ),
    "mistral-small": ModelLimits(
        model_id="mistral-small",
        context_window=32_000,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="mistral",
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.003,
        supports_vision=False
    ),
    "mixtral-8x7b": ModelLimits(
        model_id="mixtral-8x7b",
        context_window=32_000,
        max_output_tokens=4_096,
        input_reserve=1_000,
        tokenizer="mistral",
        cost_per_1k_input=0.0005,
        cost_per_1k_output=0.0005,
        supports_vision=False
    ),
    "qwen-2.5-72b": ModelLimits(
        model_id="qwen-2.5-72b",
        context_window=128_000,
        max_output_tokens=8_192,
        input_reserve=2_000,
        tokenizer="qwen",
        cost_per_1k_input=0.001,
        cost_per_1k_output=0.002,
        supports_vision=False
    ),
    "deepseek-v2.5": ModelLimits(
        model_id="deepseek-v2.5",
        context_window=128_000,
        max_output_tokens=8_192,
        input_reserve=2_000,
        tokenizer="deepseek",
        cost_per_1k_input=0.00014,
        cost_per_1k_output=0.00028,
        supports_vision=False
    ),
    "deepseek-v3": ModelLimits(
        model_id="deepseek-v3",
        context_window=128_000,
        max_output_tokens=8_192,
        input_reserve=2_000,
        tokenizer="deepseek",
        cost_per_1k_input=0.00027,
        cost_per_1k_output=0.0011,
        supports_vision=False
    ),
}

# Model aliases for common variations
MODEL_ALIASES: Dict[str, str] = {
    "gpt-4-1106-preview": "gpt-4-turbo",
    "gpt-4-0125-preview": "gpt-4-turbo",
    "gpt-4-turbo-2024-04-09": "gpt-4-turbo",
    "gpt-4o-2024-05-13": "gpt-4o",
    "gpt-4o-2024-08-06": "gpt-4o",
    "gpt-4o-mini-2024-07-18": "gpt-4o-mini",
    "claude-3-5-sonnet-latest": "claude-3.5-sonnet",
    "claude-3-opus-latest": "claude-3-opus",
    "gemini-pro": "gemini-1.5-pro",
    "gemini-flash": "gemini-1.5-flash",
}


@lru_cache(maxsize=100)
def get_model_limits(model_id: str) -> ModelLimits:
    """
    Get limits for a model, with fallback to conservative defaults.
    
    Args:
        model_id: The model identifier (e.g., "gpt-4o", "claude-3.5-sonnet")
        
    Returns:
        ModelLimits dataclass with token limits and pricing
    """
    # Check alias first
    if model_id in MODEL_ALIASES:
        model_id = MODEL_ALIASES[model_id]
    
    # Try exact match
    if model_id in MODEL_LIMITS:
        return MODEL_LIMITS[model_id]
    
    # Try prefix match (e.g., "gpt-4-turbo-2024-04-09" -> "gpt-4-turbo")
    for key in MODEL_LIMITS:
        if model_id.startswith(key):
            return MODEL_LIMITS[key]
    
    # Try suffix match for versioned models
    for key in MODEL_LIMITS:
        if model_id.endswith(key):
            return MODEL_LIMITS[key]
    
    # Infer from model name patterns
    model_lower = model_id.lower()
    
    if "gpt-4" in model_lower:
        return MODEL_LIMITS.get("gpt-4o", _get_default_limits(model_id))
    elif "gpt-3.5" in model_lower:
        return MODEL_LIMITS.get("gpt-3.5-turbo", _get_default_limits(model_id))
    elif "claude" in model_lower:
        return MODEL_LIMITS.get("claude-3.5-sonnet", _get_default_limits(model_id))
    elif "gemini" in model_lower:
        return MODEL_LIMITS.get("gemini-1.5-flash", _get_default_limits(model_id))
    elif "llama" in model_lower:
        return MODEL_LIMITS.get("llama-3.1-70b", _get_default_limits(model_id))
    elif "mistral" in model_lower or "mixtral" in model_lower:
        return MODEL_LIMITS.get("mistral-large", _get_default_limits(model_id))
    elif "qwen" in model_lower:
        return MODEL_LIMITS.get("qwen-2.5-72b", _get_default_limits(model_id))
    elif "deepseek" in model_lower:
        return MODEL_LIMITS.get("deepseek-v3", _get_default_limits(model_id))
    
    # Conservative fallback
    return _get_default_limits(model_id)


def _get_default_limits(model_id: str) -> ModelLimits:
    """Return conservative default limits for unknown models."""
    return ModelLimits(
        model_id=model_id,
        context_window=32_000,  # Conservative default
        max_output_tokens=4_096,
        input_reserve=2_000,
        tokenizer="cl100k_base",  # Most common
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
        supports_vision=False
    )


def get_tokenizer_for_model(model_id: str) -> str:
    """Get the tokenizer type for a model."""
    limits = get_model_limits(model_id)
    return limits.tokenizer


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model_id: str
) -> float:
    """
    Estimate cost in USD for a request.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model_id: The model identifier
        
    Returns:
        Estimated cost in USD
    """
    limits = get_model_limits(model_id)
    input_cost = (input_tokens / 1000) * limits.cost_per_1k_input
    output_cost = (output_tokens / 1000) * limits.cost_per_1k_output
    return input_cost + output_cost


def list_models_by_context_size(min_tokens: int = 0) -> list:
    """
    List all models with at least the specified context window.
    
    Args:
        min_tokens: Minimum context window size
        
    Returns:
        List of model IDs sorted by context window (descending)
    """
    models = [
        (model_id, limits.context_window)
        for model_id, limits in MODEL_LIMITS.items()
        if limits.context_window >= min_tokens
    ]
    models.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in models]


def list_vision_models() -> list:
    """List all models that support vision/images."""
    return [
        model_id
        for model_id, limits in MODEL_LIMITS.items()
        if limits.supports_vision
    ]
