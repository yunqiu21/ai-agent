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