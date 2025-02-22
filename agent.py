# agent.py
import os
from mistralai import Mistral
import discord

MISTRAL_MODEL = "mistral-large-latest"
SYSTEM_PROMPT = "You are a helpful assistant."

class MistralAgent:
    def __init__(self):
        MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
        self.client = Mistral(api_key=MISTRAL_API_KEY)

    async def run(self, message: discord.Message):
        """
        Default method: sends user message to Mistral and returns the response.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message.content},
        ]

        response = await self.client.chat.complete_async(
            model=MISTRAL_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content

    async def generate_custom_response(self, system_prompt: str, user_prompt: str) -> str:
        """
        Helper method to generate a custom Mistral response with
        your own system prompt and user prompt.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        response = await self.client.chat.complete_async(
            model=MISTRAL_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content
