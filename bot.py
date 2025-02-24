import os
import discord
import logging


from discord.ext import commands
from dotenv import load_dotenv
from agent import MistralAgent

from discord.ui import Button, View, Modal, TextInput
from discord import ButtonStyle, TextStyle

import requests
from bs4 import BeautifulSoup
import validators

#
# Global Data Structures
#

# In-memory dictionary to store offers:
#   offers[offer_id] = {
#       "name": "Company XYZ",
#       "job_description": "...",
#       "package": "...",
#       "extra": [ ...list of appended updates... ]
#   }
offers = {
    "1": {        
        "name": "CompanyA",
        "job_description": "As a Data professional at Meta, you will shape the future of people-facing and business-facing products we build across our entire family of applications (Facebook, Instagram, Messenger, WhatsApp, Oculus). By applying your technical skills, analytical mindset, and product intuition to one of the richest data sets in the world, you will have the opportunity to work on complex and meaningful problems that have a direct impact on the lives of people around the world. You will have the chance to work with cutting-edge technology and tools to develop innovative solutions to some of the most pressing challenges facing our platform.",
        "package": "100k USD",
        "extra": []    
    },
    "2": {        
        "name": "CompanyB",
        "job_description": "Lead the development and optimization of features within TikTok Ads Manager, focusing on improving the ads creation workflow and user journey for the Creative performance ads vertical. Recommend and prioritize innovative features to enhance the usability and performance of the platform, ensuring the ad creation experience is seamless and intuitive for these verticals. Collaborate with cross-functional teams to identify challenges, define product strategies, and set objectives that align with the needs of Creative performance advertisers. Leverage customer feedback, user research, and data analytics to identify opportunities for growth and continuous improvement in the ad creation process. Stay up-to-date with ad tech trends and emerging technologies, applying this knowledge to keep TikTok at the forefront of advertising solutions. Track and analyze key product metrics to inform product decisions and drive iterative improvements to the ads platform.",
        "package": "200k USD",
        "extra": []    
    },
    "3": {        
        "name": "CompanyC",
        "job_description": "As an Account Executive, you will work with your respective set of advertisers to shape their business growth and strengthen long-term relationships. You will drive scalable product adoption and business growth. In this role, you will anticipate how decisions are made at a C-Level, you will explore and uncover the business needs of customers, and understand how our range of product offerings can grow their business. You will set the goal and strategy for how their advertising can reach users.",
        "package": "300k USD",
        "extra": []    
    },
}

# Stores the entire "debate history" so that we can feed it to Mistral
# Example structure: [("username", "message text"), ("Bot", "message text"), ...]
# Key: user_id, Value: list of (speaker, message) tuples
user_debate_histories = {}

# Track which users are currently in the middle of a create_offer_form
active_form_sessions = {}

# Setup logging
logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
logging.basicConfig()

# Load environment variables
load_dotenv()

# Create the bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Mistral agent
agent = MistralAgent()

# Fetch Discord token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


#
# Helper Functions
#

def build_debate_context(user_id: int) -> str:
    """
    Constructs a single string that includes:
      1) All current offers (with name, job_description, package, and any extra info).
      2) The debate history of user/bot messages so far for the specific user.
    """
    # 1) Summarize all job offers
    offers_summary_lines = ["Currently considered job offers:\n"]
    if not offers:
        offers_summary_lines.append("  (No offers yet.)\n")
    else:
        for oid, data in offers.items():
            extra_text = "\n       ".join(data["extra"]) if data["extra"] else "(No extra updates)"
            offers_summary_lines.append(
                f" • Offer ID: {oid}\n"
                f"   Company Name: {data['name']}\n"
                f"   Job Description: {data['job_description']}\n"
                f"   Package: {data['package']}\n"
                f"   Extra Info:\n       {extra_text}\n"
            )

    offers_summary = "\n".join(offers_summary_lines)

    # 2) User-specific debate history
    debate_lines = ["Conversation history (user comments, prior arguments):"]
    user_history = user_debate_histories.get(user_id, [])
    if not user_history:
         debate_lines.append("  (No conversation so far.)")
    else:
        for speaker, text in user_history:
            debate_lines.append(f"{speaker}: {text}")
    debate_text = "\n".join(debate_lines)

    # Combine them
    context_str = f"{offers_summary}\n\n{debate_text}"
    return context_str

async def generate_company_argument(offer_id: int, user_id: int) -> str:
    """
    Uses the MistralAgent to produce a custom argument from a specific company's perspective,
    given the entire debate context so far.
    """
    # Step 1: Build the complete context as a system prompt
    context = build_debate_context(user_id)
    system_prompt = (
        "You are simulating a debate between multiple companies that want to hire a candidate.\n"
        "Include all relevant details in your responses, but stay in-character as the 'debate organizer.'\n"
        "You have the following context:\n\n"
        f"{context}\n"
    )

    # Step 2: Identify the target company
    company_data = offers.get(offer_id)
    if not company_data:
        # Should ideally never happen if we call this function with a valid ID
        return f"No company found with ID {offer_id}."

    # Step 3: Construct user_prompt telling Mistral to produce an argument from the company's perspective
    user_prompt = (
        f"Now, produce a persuasive argument from the perspective of company '{company_data['name']}' (offer ID: {offer_id}). "
        f"Focus on why the candidate should choose this offer over others. Do not repeat your previous arguments. At most 400 characters"
    )

    # Step 4: Call MistralAgent
    response_text = await agent.generate_custom_response(system_prompt, user_prompt)
    return response_text


#
# Bot Events
#

@bot.event
async def on_ready():
    logger.info(f"{bot.user} has connected to Discord!")


@bot.event
async def on_message(message: discord.Message):
    """
    This event is triggered on every incoming message. We skip sending the user's
    message to Mistral if they are in an active form session. Otherwise, if it's
    not a command (!...), we send it to Mistral.
    """
    if message.author.bot:
        return

    # If user typed a command (starts with "!"), process it and return
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # If this user is currently in a form session, skip Mistral:
    if message.author.id in active_form_sessions:
        # We do nothing, because presumably the create_offer_form logic
        # is waiting for their input with bot.wait_for(...)
        return

     # Otherwise, this is a normal user message; add it to debate history
    # and trigger a new round of debate
    logger.info(f"Processing normal message from {message.author}: {message.content}")
    # Initialize debate history for new users
    if message.author.id not in user_debate_histories:
        user_debate_histories[message.author.id] = []
    
    # Add user's message to their personal history
    user_debate_histories[message.author.id].append((message.author.display_name, message.content))

    # Trigger a new round of debate with all companies
    if offers:
        await message.reply("**Companies respond to your message:**")
        for offer_id in offers:
            # Generate response using user-specific context
            argument = await generate_company_argument(offer_id, message.author.id)
            # Store company's response in user's personal history
            user_debate_histories[message.author.id].append((f"Company {offers[offer_id]['name']}", argument))
            await message.reply(f"**{offers[offer_id]['name']} (Offer ID {offer_id})**:\n{argument}")
    else:
        await message.reply("No offers available to debate! Use `!create` to add some offers first.")

#
# Bot Commands

@bot.command(name="ping", help="Pings the bot.")
async def ping(ctx, *, arg=None):
    if arg is None:
        await ctx.send("Pong!")
    else:
        await ctx.send(f"Pong! Your argument was {arg}")


#
# Helper: A simple function to wait for one message from the same user/channel
#
async def ask_user_for_input(ctx: commands.Context, prompt: str, timeout=120) -> (bool, str):
    """
    Sends `prompt` to the channel, waits for user's next message.
    Returns (True, <message_content>) if user responded.
    Returns (False, None) if user timed out or typed 'cancel'.
    """
    await ctx.send(prompt)

    def check(m: discord.Message):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=timeout)
    except:
        await ctx.send("**Timed out.** Aborting the creation process.")
        return False, None

    if msg.content.lower() == "cancel":
        await ctx.send("**Cancelled.** Aborting the creation process.")
        return False, None

    return True, msg.content


#
# Multi-step Create Command
#
@bot.command(name="create", help="Start an interactive form to create a new job offer.")
async def create_offer_form(ctx: commands.Context):
    """
    !create_form
    A multi-step flow to create an offer with a potentially long job description.
    """
    # 1) Mark user as in form session
    if ctx.author.id in active_form_sessions:
        await ctx.send("You are already creating an offer. Cancel or finish that first.")
        return
    active_form_sessions[ctx.author.id] = True

    # 2) Ask for Offer ID
    success, offer_id_str = await ask_user_for_input(
        ctx,
        "**Let's create a new job offer.**\nPlease enter an offer ID (integer) or type `cancel`:"
    )
    if not success:
        active_form_sessions.pop(ctx.author.id, None)
        return

    try:
        offer_id = int(offer_id_str)
    except ValueError:
        await ctx.send("Invalid integer for Offer ID. Aborting.")
        active_form_sessions.pop(ctx.author.id, None)
        return

    if offer_id in offers:
        await ctx.send(f"An offer with ID **{offer_id}** already exists. Aborting.")
        active_form_sessions.pop(ctx.author.id, None)
        return

    # 3) Ask for Company Name
    success, company_name = await ask_user_for_input(
        ctx,
        "Please enter the **Company Name** (or type `cancel`):"
    )
    if not success:
        active_form_sessions.pop(ctx.author.id, None)
        return

    # 4) Ask for multi-line Job Description
    await ctx.send(
        "Please enter the **Job Description**.\n"
        "Type as many lines as you want. When finished, type `DONE` on a separate line.\n"
        "Or type `cancel` to abort."
    )
    try:
        first_msg = await bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=300
            )
    except:
        await ctx.send("**Timed out** while waiting for the job description. Aborting.")
        active_form_sessions.pop(ctx.author.id, None)
        return
    logger.info(f"job description: {first_msg.content}")
    if validators.url(first_msg.content):  # Check if it's a valid URL
        logger.info(f"user inputs an url.")
        job_description = fetch_website_info(first_msg.content)
        logger.info(f"parsed url: {job_description[:30]}")
    else:
        job_description_lines = [first_msg.content]
        while True:
            try:
                msg = await bot.wait_for(
                    "message",
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                    timeout=300
                )
            except:
                await ctx.send("**Timed out** while waiting for the job description. Aborting.")
                active_form_sessions.pop(ctx.author.id, None)
                return

            if msg.content.lower() == "cancel":
                await ctx.send("**Cancelled.** Aborting the creation process.")
                active_form_sessions.pop(ctx.author.id, None)
                return

            if msg.content.lower() == "done":
                break

            job_description_lines.append(msg.content)

        job_description = "\n".join(job_description_lines)

    # 5) Ask for Package
    success, package_details = await ask_user_for_input(
        ctx,
        "Enter the **Package** (e.g. `100k USD + benefits`):"
    )
    if not success:
        active_form_sessions.pop(ctx.author.id, None)
        return

    # 6) Summarize + Confirmation
    summary = (
        f"**Offer ID:** {offer_id}\n"
        f"**Company Name:** {company_name}\n"
        f"**Job Description:**\n{job_description}\n"
        f"**Package:** {package_details}\n"
    )
    await ctx.send(f"**Here is what you’ve entered:**\n{summary}")

    success, confirm = await ask_user_for_input(ctx, "Type `yes` to confirm or `no` to abort:")
    if not success:
        active_form_sessions.pop(ctx.author.id, None)
        return

    if confirm.lower() != "yes":
        await ctx.send("**Aborted** creation process. No offer created.")
        active_form_sessions.pop(ctx.author.id, None)
        return

    # 7) Actually save
    offers[offer_id] = {
        "name": company_name,
        "job_description": job_description,
        "package": package_details,
        "extra": []
    }

    await ctx.send(
        f"**Success!** Created offer `{offer_id}`:\n"
        f"- Company Name: {company_name}\n"
        f"- Job Description: (see above)\n"
        f"- Package: {package_details}"
    )

    # 8) Mark session as finished
    active_form_sessions.pop(ctx.author.id, None)


@bot.command(name="update", help="Update an existing offer with more info.")
async def update_offer(ctx: commands.Context, offer_id: int, *, more_info: str):
    if offer_id not in offers:
        await ctx.send(f"No offer found with ID `{offer_id}`.")
        return

    offers[offer_id]["extra"].append(more_info)
    await ctx.send(f"**Updated** offer `{offer_id}` with new info:\n{more_info}")


@bot.command(name="remove", help="Remove an existing offer.")
async def remove_offer(ctx: commands.Context, offer_id: int):
    if offer_id not in offers:
        await ctx.send(f"No offer found with ID `{offer_id}`.")
        return

    removed_offer = offers.pop(offer_id)
    await ctx.send(
        f"**Removed** offer `{offer_id}` from consideration:\n"
        f"- Company: {removed_offer['name']}"
    )


@bot.command(name="list", help="List all currently available offers.")
async def list_all_offers(ctx: commands.Context):
    """
    !list
    Displays all offers in the 'offers' dictionary.
    """
    if not offers:
        await ctx.send("No offers are currently available.")
        return

    # Build a string listing each offer
    lines = ["**Currently Available Offers:**\n"]
    for oid, data in offers.items():
        lines.append(
            f"**Offer ID:** {oid}\n"
            f"**Company Name:** {data['name']}\n"
            f"**Job Description:**\n{data['job_description'][:50]}...\n"
            f"**Package:** {data['package']}\n"
            f"**Extra Info:** {', '.join(data['extra']) if data['extra'] else '(None)'}\n"
            "--------------------------------------\n"
        )

    message_text = "\n".join(lines)
    # If you worry about message length, you can chunk it or send multiple messages
    await ctx.send(message_text)


@bot.command(name="go", help="Continue the debate for one round (all companies speak).")
async def continue_debate(ctx: commands.Context, offer_id: int = None):
    """
    !go
    Allows each company in the offers dictionary to speak in turn,
    generating an AI-based argument from each company's perspective.
    !go <offer_id> - Ask a specific company to speak
    """
    if not offers:
        await ctx.send("No offers available to debate!")
        return

    # Initialize debate history for new users
    if ctx.author.id not in user_debate_histories:
        user_debate_histories[ctx.author.id] = []

    if offer_id is None:
        # Generate arguments from all companies
        for oid in offers:
            argument = await generate_company_argument(oid, ctx.author.id)
            # Store response in user's personal history
            user_debate_histories[ctx.author.id].append((f"Company {offers[oid]['name']}", argument))
            await ctx.send(f"**{offers[oid]['name']} (Offer ID {oid})**:\n{argument}")
        return
    
    # Logic for a specific company
    if offer_id not in offers:
        await ctx.send(f"No offer found with ID {offer_id}.")
        return
    
    company_data = offers[offer_id]
    argument = await generate_company_argument(offer_id, ctx.author.id)

    # Store the argument in user's personal history
    user_debate_histories[ctx.author.id].append((f"Company {company_data['name']}", argument))
    await ctx.send(f"**{company_data['name']} (Offer ID {offer_id})**:\n{argument}")

# helper
def fetch_website_info(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an error for HTTP issues

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract key content (e.g., paragraphs, headlines)
        # headlines = [h.get_text() for h in soup.find_all(['h1', 'h2'])]
        paragraphs = [p.get_text() for p in soup.find_all('p')]

        # Join extracted text
        extracted_text = "\n".join(paragraphs)

        return extracted_text if extracted_text else "No meaningful content found."

    except requests.exceptions.RequestException as e:
        return f"Error fetching website: {e}"


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
