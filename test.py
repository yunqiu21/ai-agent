import requests
from bs4 import BeautifulSoup
import validators

def fetch_website_info(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an error for HTTP issues

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract key content (e.g., paragraphs, headlines)
        headlines = [h.get_text() for h in soup.find_all(['h1', 'h2'])]
        paragraphs = [p.get_text() for p in soup.find_all('p')]

        # Join extracted text
        extracted_text = "\n".join(paragraphs)

        return extracted_text if extracted_text else "No meaningful content found."

    except requests.exceptions.RequestException as e:
        return f"Error fetching website: {e}"

# Example usage
url = "https://bloomberg.avature.net/careers/JobDetail/2025-Software-Engineer-New-York/6961"
if validators.url(url):
    print(fetch_website_info(url))
else:
    print("invalid")


@bot.command(name="advise", help="Summarizes the conversation and suggests which offer to choose.")
async def advise(ctx):
    user_id = ctx.author.id
    
    # Ensure the user has participated in a debate
    if user_id not in user_debate_histories or not user_debate_histories[user_id]:
        await ctx.send("You haven't discussed any offers yet. Start a discussion before asking for advice!")
        return

    # Build full debate context
    context = build_debate_context(user_id)

    # System prompt for decision-making
    system_prompt = (
        "You are an expert career advisor helping a candidate choose between multiple job offers. "
        "Based on the given offers, discussion history, and priorities of the user, "
        "provide a thoughtful recommendation on which offer they should take. "
        "Consider salary, job responsibilities, career growth, and company culture."
    )

    # User prompt to summarize and decide
    user_prompt = (
        "Summarize the discussion so far and recommend the best job offer based on the candidate's interests and debate history. No more than 400 characters."
    )

    # Generate advice using Mistral
    advice = await agent.generate_custom_response(system_prompt, user_prompt)

    await ctx.send(f"**Career Advice:**\n{advice}")