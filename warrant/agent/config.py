"""Which model answers, and how to reach it.

Both platforms are reached through the Anthropic SDK, which gives them the same `messages.create`,
so switching between them is this configuration block and nothing else. The model identifier is
whatever the named platform calls it: Bedrock prefixes the Anthropic identifier, the Anthropic API
does not. Credentials come from a local AWS profile or environment variables, never from the repo.
"""

import re
from dataclasses import dataclass
from typing import Any, Mapping

BEDROCK = "bedrock"
ANTHROPIC = "anthropic"

# A region reaches Bedrock through the host name, so a typo or a leftover placeholder would only
# show up as a connection failure on every call. Refuse it here instead.
REGION = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d+$")


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    region: str = ""
    max_tokens: int = 4096
    effort: str = ""
    temperature: float | None = None
    attempts: int = 2
    max_tool_calls: int = 8


def load_model_config(raw: Mapping[str, Any]) -> ModelConfig:
    """Read the `model` block of a configuration."""
    return ModelConfig(
        provider=raw["provider"],
        model=raw["model"],
        region=raw.get("region", ""),
        max_tokens=int(raw.get("max_tokens", 4096)),
        effort=raw.get("effort", ""),
        temperature=None if raw.get("temperature") is None else float(raw["temperature"]),
        attempts=int(raw.get("attempts", 2)),
        max_tool_calls=int(raw.get("max_tool_calls", 8)),
    )


def client(config: ModelConfig):
    """The SDK client for the configured platform. Constructing one makes no request."""
    if config.provider == BEDROCK:
        from anthropic import AnthropicBedrockMantle

        if not REGION.match(config.region):
            raise ValueError(f"not an AWS region: {config.region!r}")
        return AnthropicBedrockMantle(aws_region=config.region)
    if config.provider == ANTHROPIC:
        from anthropic import Anthropic

        return Anthropic()
    raise ValueError(f"unknown provider: {config.provider!r}")
