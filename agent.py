import os
import openai
import discord
import time
import asyncio
from datetime import datetime, timedelta

GPT_MODEL = "gpt-4o-2024-11-20"
SYSTEM_PROMPT = "You are a helpful assistant."

class GPTAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = openai.AsyncOpenAI(api_key=self.api_key)
        # Add rate limiting attributes
        self.request_queue = asyncio.Queue()
        self.last_request_time = datetime.now()
        self.min_request_interval = 1.0  # Minimum seconds between requests
        self.is_processing = False

    async def process_queue(self):
        """Process queued requests with rate limiting"""
        if self.is_processing:
            return
        
        self.is_processing = True
        try:
            while not self.request_queue.empty():
                # Wait if needed to respect rate limit
                time_since_last = (datetime.now() - self.last_request_time).total_seconds()
                if time_since_last < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_since_last)

                # Process next request
                request = await self.request_queue.get()
                messages, future = request
                
                try:
                    response = await self.client.chat.completions.create(
                        model=GPT_MODEL,
                        messages=messages,
                    )
                    future.set_result(response.choices[0].message.content)
                except Exception as e:
                    future.set_exception(e)
                
                self.last_request_time = datetime.now()
                self.request_queue.task_done()
        finally:
            self.is_processing = False

    async def queue_request(self, messages):
        """Queue a request and return a future for the result"""
        future = asyncio.Future()
        await self.request_queue.put((messages, future))
        
        # Start processing if not already running
        asyncio.create_task(self.process_queue())
        
        return await future

    async def run(self, message: discord.Message):
        """Default method: sends user message to GPT-4o and returns the response."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message.content},
        ]
        return await self.queue_request(messages)

    async def generate_custom_response(self, system_prompt: str, user_prompt: str) -> str:
        """Helper method to generate a custom GPT-4o response"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self.queue_request(messages)
