"""
Langpify LLM Utilities
Provides framework-agnostic utilities for working with language models and dynamic prompts.
"""

import logging
from typing import Any, Callable, List, Optional, Type

from pydantic import BaseModel
from langgraph.graph import StateGraph

from langpify.entities.entities import (
    Framework,
    LangpifyTemplateLanguage,
    LangpifyLanguage,
    LangpifyLLM,
    LangpifyAgentType,
    LangpifyDynamicPrompt,
    LangpifyPlanning,
    LangpifyTemplatePlanning,
    LangpifyWorkflow,
    LangpifyRole,
    LangpifySafety,
)

logger = logging.getLogger(__name__)


def get_llm(
    framework: Framework,
    llm_settings: LangpifyTemplateLanguage,
) -> LangpifyLanguage:
    """
    Initialize a language model based on the framework and settings.
    
    The idea here is to be agnostic of the framework, so we can work with whatever we want.
    For the sake of simplicity we would only work now with Langchain and Langgraph.
    
    Args:
        framework: The AI framework to use (LANGCHAIN, LANGGRAPH, etc.)
        llm_settings: Template language settings including provider and model configuration
        
    Returns:
        LangpifyLanguage: Configured language model instance
        
    Raises:
        ValueError: If the framework is not supported
    """
    if framework == Framework.LANGCHAIN or framework == Framework.LANGGRAPH:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_groq import ChatGroq
        except ImportError:
            raise ImportError(
                "langchain_openai and langchain_groq are required for Langchain/Langgraph frameworks"
            )

        language = LangpifyLanguage(default="", llm=LangpifyLLM())
        language["default"] = llm_settings["default"]

        llm = LangpifyLLM()

        llm["model_provider"] = llm_settings["llm"]["primary_model"]["provider"]
        llm["model_name"] = llm_settings["llm"]["primary_model"]["model"]

        """ As a good practise we add a LLM fallback 
        Notice that this is just a simplification where we assumed which would be the secondary model
        At productive environments we should build a more dynamic LLM Gateway fallback system
        with circuit breakers for multiple models and providers, handling token management and cost optimization,
        
        In productive environments we should also use rate limiters.
        """

        if llm_settings["llm"]["primary_model"]["provider"] == "openai":
            openai_model = ChatOpenAI(
                model=llm_settings["llm"]["primary_model"]["model"],
                temperature=llm_settings["llm"]["primary_model"].get("temperature", 0.7),
                verbose=True,
            )
            if llm_settings["llm"].get("secondary_model"):
                groq_model = ChatGroq(
                    model=llm_settings["llm"]["secondary_model"]["model"],
                    temperature=llm_settings["llm"]["secondary_model"].get(
                        "temperature", 0.7
                    ),
                    verbose=True,
                )
                # We could use fallbacks if we want to use a secondary model
                # llm["model"] = openai_model.with_fallbacks([groq_model])
            llm["model"] = openai_model

        elif llm_settings["llm"]["primary_model"]["provider"] == "groq":
            groq_model = ChatGroq(
                model=llm_settings["llm"]["primary_model"]["model"],
                temperature=llm_settings["llm"]["primary_model"].get("temperature", 0.7),
                verbose=True,
            )
            if llm_settings["llm"].get("secondary_model"):
                openai_model = ChatOpenAI(
                    model=llm_settings["llm"]["secondary_model"]["model"],
                    temperature=llm_settings["llm"]["secondary_model"].get(
                        "temperature", 0.7
                    ),
                    verbose=True,
                )
                # We could use fallbacks if we want to use a secondary model
                # llm["model"] = groq_model.with_fallbacks([openai_model])
            llm["model"] = groq_model

        language["llm"] = llm

        return language
    else:
        raise ValueError(f"Unsupported framework: {framework}")


def to_dynamic_prompt(
    role: LangpifyRole, planning: LangpifyTemplatePlanning, safety: LangpifySafety
) -> LangpifyDynamicPrompt:
    """
    Convert role, planning, and safety configurations to a dynamic prompt structure.
    
    Args:
        role: Agent role configuration
        planning: Template planning configuration
        safety: Safety and guardrails configuration
        
    Returns:
        LangpifyDynamicPrompt: Structured dynamic prompt
    """
    return LangpifyDynamicPrompt(
        role=role["prompt"],
        goal=planning["goal"]["prompt"],
        instructions=planning["excecution_protocol"]["prompt"],
        extras=planning["goal"]["prompt_extras"],
        examples=planning["excecution_protocol"]["prompt_examples"],
        output=planning["excecution_protocol"]["prompt_output"],
        guardrails=safety["guardrails"]["prompt"],
    )


def generate_prompt_template(prompt: LangpifyDynamicPrompt) -> str:
    """
    Generate a formatted prompt template from a dynamic prompt structure.
    
    Args:
        prompt: Dynamic prompt configuration
        
    Returns:
        str: Formatted prompt template string
    """
    prompt_template = f"""
    [ROLE]
    {prompt.role}
    
    [GOAL]
    {prompt.goal}
    
    [INSTRUCTIONS]
    {prompt.instructions}
    
    {prompt.extras}
    
    [EXAMPLES]
    {prompt.examples}
    
    [OUTPUT]
    {prompt.output}
    
    [GUARDRAILS]
    {prompt.guardrails}
    """

    # Log the generated template (truncate if too long)
    if len(prompt_template) > 500:
        logger.debug(
            "Generated prompt template (truncated to 500 chars): %s...",
            prompt_template[:500],
        )
    else:
        logger.debug("Generated prompt template: %s", prompt_template)

    return prompt_template
