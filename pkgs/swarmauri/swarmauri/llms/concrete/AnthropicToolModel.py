import json
import asyncio
from typing import AsyncIterator, Iterator
from typing import List, Dict, Literal, Any
import logging
import anthropic
from swarmauri_core.typing import SubclassUnion

from swarmauri.messages.base.MessageBase import MessageBase
from swarmauri.messages.concrete.AgentMessage import AgentMessage
from swarmauri.messages.concrete.FunctionMessage import FunctionMessage
from swarmauri.llms.base.LLMBase import LLMBase
from swarmauri.schema_converters.concrete.AnthropicSchemaConverter import (
    AnthropicSchemaConverter,
)


class AnthropicToolModel(LLMBase):
    """
    Provider resources: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
    """

    api_key: str
    allowed_models: List[str] = [
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
        "claude-3-5-sonnet-20240620",
        "claude-3-sonnet-20240229",
    ]
    name: str = "claude-3-haiku-20240307"
    type: Literal["AnthropicToolModel"] = "AnthropicToolModel"

    def _schema_convert_tools(self, tools) -> List[Dict[str, Any]]:
        schema_result = [
            AnthropicSchemaConverter().convert(tools[tool]) for tool in tools
        ]
        logging.info(schema_result)
        return schema_result

    def _format_messages(
        self, messages: List[SubclassUnion[MessageBase]]
    ) -> List[Dict[str, str]]:
        message_properties = ["content", "role", "tool_call_id", "tool_calls"]
        formatted_messages = [
            message.model_dump(include=message_properties, exclude_none=True)
            for message in messages
        ]
        return formatted_messages

    def predict(
        self,
        conversation,
        toolkit=None,
        tool_choice=None,
        temperature=0.7,
        max_tokens=1024,
    ):

        formatted_messages = self._format_messages(conversation.history)

        client = anthropic.Anthropic(api_key=self.api_key)
        if toolkit and not tool_choice:
            tool_choice = {"type": "auto"}

        tool_response = client.messages.create(
            model=self.name,
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self._schema_convert_tools(toolkit.tools),
            tool_choice=tool_choice,
        )

        logging.info(f"tool_response: {tool_response}")
        tool_text_response = None
        if tool_response.content[0].type == "text":
            tool_text_response = tool_response.content[0].text
            logging.info(f"tool_text_response: {tool_text_response}")

        for tool_call in tool_response.content:
            if tool_call.type == "tool_use":
                func_name = tool_call.name
                func_call = toolkit.get_tool_by_name(func_name)
                func_args = tool_call.input
                func_result = func_call(**func_args)

        if tool_text_response:
            agent_response = f"{tool_text_response} {func_result}"
        else:
            agent_response = f"{func_result}"

        agent_message = AgentMessage(content=agent_response)
        conversation.add_message(agent_message)
        logging.info(f"conversation: {conversation}")
        return conversation

    async def apredict(
        self,
        conversation,
        toolkit=None,
        tool_choice=None,
        temperature=0.7,
        max_tokens=1024,
    ):
        client = anthropic.Anthropic(api_key=self.api_key)
        formatted_messages = self._format_messages(conversation.history)

        if toolkit and not tool_choice:
            tool_choice = {"type": "auto"}

        tool_response = await client.messages.create(
            model=self.name,
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self._schema_convert_tools(toolkit.tools) if toolkit else None,
            tool_choice=tool_choice,
        )

        logging.info(f"tool_response: {tool_response}")
        tool_text_response = None
        if tool_response.content[0].type == "text":
            tool_text_response = tool_response.content[0].text
            logging.info(f"tool_text_response: {tool_text_response}")

        func_result = None
        for tool_call in tool_response.content:
            if tool_call.type == "tool_use":
                func_name = tool_call.name
                func_call = toolkit.get_tool_by_name(func_name)
                func_args = tool_call.input
                func_result = func_call(**func_args)

        if tool_text_response:
            agent_response = f"{tool_text_response} {func_result}"
        else:
            agent_response = f"{func_result}"

        agent_message = AgentMessage(content=agent_response)
        conversation.add_message(agent_message)
        return conversation

    def stream(
        self,
        conversation,
        toolkit=None,
        tool_choice=None,
        temperature=0.7,
        max_tokens=1024,
    ) -> Iterator[str]:
        client = anthropic.Anthropic(api_key=self.api_key)
        formatted_messages = self._format_messages(conversation.history)

        if toolkit and not tool_choice:
            tool_choice = {"type": "auto"}

        stream = client.messages.create(
            model=self.name,
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self._schema_convert_tools(toolkit.tools) if toolkit else None,
            tool_choice=tool_choice,
            stream=True,
        )

        collected_content = []
        for chunk in stream:
            if chunk.type == "content_block_delta":
                if chunk.delta.type == "text":
                    collected_content.append(chunk.delta.text)
                    yield chunk.delta.text

        full_content = "".join(collected_content)
        conversation.add_message(AgentMessage(content=full_content))

    async def astream(
        self,
        conversation,
        toolkit=None,
        tool_choice=None,
        temperature=0.7,
        max_tokens=1024,
    ) -> AsyncIterator[str]:
        client = anthropic.Anthropic(api_key=self.api_key)
        formatted_messages = self._format_messages(conversation.history)

        if toolkit and not tool_choice:
            tool_choice = {"type": "auto"}

        stream = await client.messages.create(
            model=self.name,
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=self._schema_convert_tools(toolkit.tools) if toolkit else None,
            tool_choice=tool_choice,
            stream=True,
        )

        collected_content = []
        async for chunk in stream:
            if chunk.type == "content_block_delta":
                if chunk.delta.type == "text":
                    collected_content.append(chunk.delta.text)
                    yield chunk.delta.text

        full_content = "".join(collected_content)
        conversation.add_message(AgentMessage(content=full_content))

    def batch(
        self,
        conversations: List,
        toolkit=None,
        tool_choice=None,
        temperature=0.7,
        max_tokens=1024,
    ) -> List:
        results = []
        for conv in conversations:
            result = self.predict(
                conversation=conv,
                toolkit=toolkit,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            results.append(result)
        return results

    async def abatch(
        self,
        conversations: List,
        toolkit=None,
        tool_choice=None,
        temperature=0.7,
        max_tokens=1024,
        max_concurrent=5,
    ) -> List:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_conversation(conv):
            async with semaphore:
                return await self.apredict(
                    conv,
                    toolkit=toolkit,
                    tool_choice=tool_choice,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

        tasks = [process_conversation(conv) for conv in conversations]
        return await asyncio.gather(*tasks)
