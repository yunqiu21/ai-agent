import os
import discord
import logging

from discord.ext import commands
from dotenv import load_dotenv
from agent import MistralAgent

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
offers = {}

# Stores the entire "debate history" so that we can feed it to Mistral
# Example structure: [("username", "message text"), ("Bot", "message text"), ...]
debate_history = []

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

def build_debate_context() -> str:
    """
    Constructs a single string that includes:
      1) All current offers (with name, job_description, package, and any extra info).
      2) The entire debate history of user/bot messages so far.
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

    # 2) Debate history
    debate_lines = ["Conversation history (user comments, prior arguments):"]
    if not debate_history:
        debate_lines.append("  (No conversation so far.)")
    else:
        for speaker, text in debate_history:
            debate_lines.append(f"{speaker}: {text}")
    debate_text = "\n".join(debate_lines)

    # Combine them
    context_str = f"{offers_summary}\n\n{debate_text}"
    return context_str


async def generate_company_argument(offer_id: int) -> str:
    """
    Uses the MistralAgent to produce a custom argument from a specific company's perspective,
    given the entire debate context so far.
    """
    # Step 1: Build the complete context as a system prompt
    context = build_debate_context()
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

    # Otherwise, this is a normal user message; let's forward it to Mistral
    logger.info(f"Processing normal message from {message.author}: {message.content}")
    debate_history.append((message.author.display_name, message.content))
    ai_response = await agent.run(message)
    debate_history.append(("Bot", ai_response))

    await message.reply(ai_response)


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
    job_description_lines = []
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


@bot.command(name="list_offers", help="List all currently available offers.")
async def list_all_offers(ctx: commands.Context):
    """
    !list_offers
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


@bot.command(name="y", help="Continue the debate for one round (all companies speak).")
async def continue_debate(ctx: commands.Context, offer_id: int = None):
    """
    !y
    Allows each company in the offers dictionary to speak in turn,
    generating an AI-based argument from each company's perspective.
    !y <offer_id> - Ask a specific company to speak
    """
    if not offers:
        await ctx.send("No offers available to debate!")
        return

    if offer_id is None:
        # For each offer in memory, generate a new argument
        for offer_id, data in offers.items():
            argument = await generate_company_argument(offer_id)
            # Optionally, store it in debate_history so future calls see it
            debate_history.append((f"Company {data['name']}", argument))

            # Send the argument to the channel
            await ctx.send(f"**{data['name']} (Offer ID {offer_id})**:\n{argument}")
        return
    
    # Company-specific logic
    if offer_id not in offers:
        await ctx.send(f"No offer found with ID {offer_id}.")
        return
    
    company_data = offers[offer_id]
    argument = await generate_company_argument(offer_id)

    # Store this argument in debate_history
    debate_history.append((f"Company {company_data['name']}", argument))

    # Send the new argument to the channel
    await ctx.send(f"**{company_data['name']} (Offer ID {offer_id})**:\n{argument}")



if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
