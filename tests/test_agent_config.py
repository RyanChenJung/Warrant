"""Switching between the Anthropic API and Bedrock is a configuration change.

Constructing either client reads credentials from the environment and makes no request, so these
tests never reach the network. The model identifier is whatever the named platform calls it:
Bedrock prefixes the Anthropic identifier, the Anthropic API does not.
"""

import textwrap

import pytest
import yaml
from anthropic import Anthropic, AnthropicBedrockMantle

from warrant.agent.config import ModelConfig, client, load_model_config
from warrant.write_line.config import load_config

MODEL_BLOCK = textwrap.dedent(
    """
    model:
      provider: {provider}
      model: {model}
      region: {region}
      max_tokens: 4096
      attempts: 2
    """
)


def model_config(tmp_path, provider, model, region="us-east-1"):
    path = tmp_path / f"{provider}.yaml"
    path.write_text(MODEL_BLOCK.format(provider=provider, model=model, region=region))
    return load_model_config(yaml.safe_load(path.read_text())["model"])


def test_the_same_configuration_shape_names_either_platform(tmp_path):
    bedrock = model_config(tmp_path, "bedrock", "anthropic.claude-model-placeholder")
    anthropic_api = model_config(tmp_path, "anthropic", "claude-model-placeholder")

    assert isinstance(client(bedrock), AnthropicBedrockMantle)
    assert isinstance(client(anthropic_api), Anthropic)
    assert bedrock.model == "anthropic.claude-model-placeholder"
    assert anthropic_api.model == "claude-model-placeholder"


def test_the_bedrock_client_takes_its_region_from_the_configuration(tmp_path):
    bedrock = model_config(tmp_path, "bedrock", "anthropic.m", region="eu-west-2")
    assert "eu-west-2" in str(client(bedrock).base_url)


@pytest.mark.parametrize("region", ["", "region-placeholder", "us-east", "US-EAST-1"])
def test_a_region_that_is_not_a_region_is_refused_before_any_call(region):
    """A region reaches Bedrock through the host name, so a bad one would only look like a
    connection failure, on every call of the run."""
    with pytest.raises(ValueError, match="not an AWS region"):
        client(ModelConfig(provider="bedrock", model="m", region=region))


def test_an_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="unknown provider"):
        client(ModelConfig(provider="openai", model="m"))


def test_the_write_line_configuration_carries_the_model_block(write_line_config):
    config = load_config(write_line_config)
    assert config.model.provider == "bedrock"
    assert config.model.model == "anthropic.claude-sonnet-5"
    assert config.model.region == "us-east-1"


def test_temperature_is_absent_unless_the_configuration_sets_it(tmp_path):
    assert model_config(tmp_path, "bedrock", "m").temperature is None
    assert load_model_config({"provider": "bedrock", "model": "m", "temperature": 0.0}).temperature == 0.0
