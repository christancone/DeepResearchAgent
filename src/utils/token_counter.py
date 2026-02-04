"""
Token Counter Service

Provides accurate token counting across different LLM providers.
Uses tiktoken for OpenAI models and approximations for others.
"""

import tiktoken
from typing import List, Dict, Any, Optional, Union
from functools import lru_cache

# Note: get_model_limits is imported lazily inside methods to avoid circular imports
# The circular import chain: utils -> token_counter -> config -> cfg -> logger -> utils


def _get_model_limits(model_id: str):
    """Lazy import wrapper to avoid circular imports."""
    from src.config.model_limits import get_model_limits
    return get_model_limits(model_id)


class TokenCounter:
    """
    Service for counting tokens across different LLM providers.
    Uses tiktoken for OpenAI models, approximations for others.
    """
    
    # Approximate chars per token for non-tiktoken models
    CHARS_PER_TOKEN = {
        "claude": 3.5,  # Claude tends to be more efficient
        "gemini": 4.0,
        "llama3": 4.0,
        "mistral": 4.0,
        "qwen": 3.8,
        "deepseek": 4.0,
        "default": 4.0
    }
    
    # Message formatting overhead by provider
    MESSAGE_OVERHEAD = {
        "openai": 4,  # <|im_start|>, role, \n, <|im_end|>
        "anthropic": 3,
        "google": 3,
        "default": 4
    }
    
    @classmethod
    @lru_cache(maxsize=10)
    def _get_tiktoken_encoding(cls, encoding_name: str):
        """Cached tiktoken encoder loading."""
        try:
            return tiktoken.get_encoding(encoding_name)
        except Exception:
            # Fallback to most common encoding
            return tiktoken.get_encoding("cl100k_base")
    
    @classmethod
    def _get_encoding_for_model(cls, model_id: str):
        """Get tiktoken encoding for a model."""
        limits = _get_model_limits(model_id)
        tokenizer = limits.tokenizer
        
        # Map tokenizer types to tiktoken encodings
        tiktoken_map = {
            "cl100k_base": "cl100k_base",
            "o200k_base": "o200k_base",
            "p50k_base": "p50k_base",
        }
        
        encoding_name = tiktoken_map.get(tokenizer)
        if encoding_name:
            return cls._get_tiktoken_encoding(encoding_name)
        
        # Try to get encoding for model directly
        try:
            return tiktoken.encoding_for_model(model_id)
        except Exception:
            return cls._get_tiktoken_encoding("cl100k_base")
    
    @classmethod
    def count_tokens(cls, text: str, model_id: str = "gpt-4o") -> int:
        """
        Count tokens for a given text and model.
        Uses exact counting for OpenAI models, approximation for others.
        
        Args:
            text: The text to count tokens for
            model_id: The model identifier
            
        Returns:
            Number of tokens
        """
        if not text:
            return 0
            
        limits = _get_model_limits(model_id)
        
        # Use tiktoken for OpenAI-compatible tokenizers
        if limits.tokenizer in ["cl100k_base", "o200k_base", "p50k_base"]:
            encoding = cls._get_encoding_for_model(model_id)
            return len(encoding.encode(text))
        
        # Approximation for other models
        chars_per_token = cls.CHARS_PER_TOKEN.get(
            limits.tokenizer, 
            cls.CHARS_PER_TOKEN["default"]
        )
        return int(len(text) / chars_per_token)
    
    @classmethod
    def count_messages_tokens(
        cls, 
        messages: List[Dict[str, Any]], 
        model_id: str = "gpt-4o"
    ) -> int:
        """
        Count tokens for a list of chat messages.
        Accounts for message formatting overhead.
        
        Args:
            messages: List of message dictionaries with "role" and "content"
            model_id: The model identifier
            
        Returns:
            Total token count including formatting overhead
        """
        if not messages:
            return 0
            
        limits = _get_model_limits(model_id)
        total = 0
        
        # Determine overhead based on provider
        if "gpt" in model_id.lower() or "o1" in model_id.lower():
            overhead_per_message = cls.MESSAGE_OVERHEAD["openai"]
        elif "claude" in model_id.lower():
            overhead_per_message = cls.MESSAGE_OVERHEAD["anthropic"]
        elif "gemini" in model_id.lower():
            overhead_per_message = cls.MESSAGE_OVERHEAD["google"]
        else:
            overhead_per_message = cls.MESSAGE_OVERHEAD["default"]
        
        for message in messages:
            total += overhead_per_message
            
            # Count content
            content = message.get("content", "")
            if isinstance(content, str):
                total += cls.count_tokens(content, model_id)
            elif isinstance(content, list):
                # Multi-modal content (text + images)
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            total += cls.count_tokens(part.get("text", ""), model_id)
                        elif part.get("type") == "image_url":
                            # Images are ~85 tokens for low detail, ~765 for high detail
                            detail = part.get("image_url", {}).get("detail", "auto")
                            total += 765 if detail == "high" else 85
                        elif part.get("type") == "image":
                            total += 765  # Default to high detail for generic image
                    elif isinstance(part, str):
                        total += cls.count_tokens(part, model_id)
            
            # Count role
            role = message.get("role", "user")
            total += cls.count_tokens(role, model_id)
            
            # Count name if present
            if "name" in message:
                total += cls.count_tokens(message["name"], model_id) + 1
            
            # Count tool calls if present
            if "tool_calls" in message:
                for tool_call in message.get("tool_calls", []):
                    if isinstance(tool_call, dict):
                        func = tool_call.get("function", {})
                        total += cls.count_tokens(func.get("name", ""), model_id)
                        total += cls.count_tokens(func.get("arguments", ""), model_id)
                        total += 10  # Overhead for tool call structure
        
        # Priming tokens
        total += 3
        
        return total
    
    @classmethod
    def count_tool_result_tokens(
        cls,
        tool_name: str,
        tool_output: str,
        model_id: str = "gpt-4o"
    ) -> int:
        """
        Count tokens for a tool result.
        
        Args:
            tool_name: Name of the tool
            tool_output: The tool's output
            model_id: The model identifier
            
        Returns:
            Token count for the tool result
        """
        overhead = 5  # Tool result structure overhead
        name_tokens = cls.count_tokens(tool_name, model_id)
        output_tokens = cls.count_tokens(str(tool_output), model_id)
        return overhead + name_tokens + output_tokens
    
    @classmethod
    def estimate_cost(
        cls,
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
        limits = _get_model_limits(model_id)
        input_cost = (input_tokens / 1000) * limits.cost_per_1k_input
        output_cost = (output_tokens / 1000) * limits.cost_per_1k_output
        return input_cost + output_cost
    
    @classmethod
    def check_fits_in_context(
        cls,
        messages: List[Dict[str, Any]],
        model_id: str,
        buffer: int = 0
    ) -> Dict[str, Any]:
        """
        Check if messages fit within the model's context window.
        
        Args:
            messages: List of messages to check
            model_id: The model identifier
            buffer: Additional buffer tokens to reserve
            
        Returns:
            Dictionary with fit status and details
        """
        limits = _get_model_limits(model_id)
        token_count = cls.count_messages_tokens(messages, model_id)
        available = limits.effective_input_limit - buffer
        
        return {
            "tokens": token_count,
            "limit": limits.effective_input_limit,
            "available": available,
            "fits": token_count <= available,
            "overflow": max(0, token_count - available),
            "usage_percent": (token_count / limits.effective_input_limit) * 100 if limits.effective_input_limit > 0 else 100,
            "model_id": model_id,
            "context_window": limits.context_window
        }
    
    @classmethod
    def truncate_text_to_tokens(
        cls,
        text: str,
        max_tokens: int,
        model_id: str = "gpt-4o",
        truncation_side: str = "end"
    ) -> str:
        """
        Truncate text to fit within a token limit.
        
        Args:
            text: The text to truncate
            max_tokens: Maximum allowed tokens
            model_id: The model identifier
            truncation_side: "end", "start", or "middle"
            
        Returns:
            Truncated text
        """
        current_tokens = cls.count_tokens(text, model_id)
        
        if current_tokens <= max_tokens:
            return text
        
        limits = _get_model_limits(model_id)
        
        # For tiktoken-compatible models, use exact truncation
        if limits.tokenizer in ["cl100k_base", "o200k_base", "p50k_base"]:
            encoding = cls._get_encoding_for_model(model_id)
            tokens = encoding.encode(text)
            
            if truncation_side == "end":
                truncated_tokens = tokens[:max_tokens]
                suffix = "...[truncated]"
            elif truncation_side == "start":
                truncated_tokens = tokens[-max_tokens:]
                suffix = "[truncated]..."
            else:  # middle
                half = max_tokens // 2
                truncated_tokens = tokens[:half] + tokens[-half:]
                suffix = ""  # Will add marker in the middle
            
            result = encoding.decode(truncated_tokens)
            
            if truncation_side == "middle":
                mid = len(result) // 2
                result = result[:mid] + "...[middle truncated]..." + result[mid:]
            else:
                result = result + suffix if truncation_side == "end" else suffix + result
            
            return result
        
        # Approximation for other models
        chars_per_token = cls.CHARS_PER_TOKEN.get(
            limits.tokenizer,
            cls.CHARS_PER_TOKEN["default"]
        )
        max_chars = int(max_tokens * chars_per_token)
        
        if truncation_side == "end":
            return text[:max_chars] + "...[truncated]"
        elif truncation_side == "start":
            return "[truncated]..." + text[-max_chars:]
        else:  # middle
            half = max_chars // 2
            return text[:half] + "...[middle truncated]..." + text[-half:]


# Convenience functions for backward compatibility
def count_tokens(text: str, model_id: str = "gpt-4o") -> int:
    """Count tokens in text."""
    return TokenCounter.count_tokens(text, model_id)


def count_messages_tokens(messages: List[Dict[str, Any]], model_id: str = "gpt-4o") -> int:
    """Count tokens in a list of messages."""
    return TokenCounter.count_messages_tokens(messages, model_id)


def check_context_fit(
    messages: List[Dict[str, Any]], 
    model_id: str,
    buffer: int = 0
) -> Dict[str, Any]:
    """Check if messages fit in context window."""
    return TokenCounter.check_fits_in_context(messages, model_id, buffer)
