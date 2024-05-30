# 1. Import necessary libraries
import requests
from bs4 import BeautifulSoup

# 2. Define the URL
url = 'https://web.archive.org/web/20230810012537/https://www.bonappetit.com/recipe/grilled-brisket-with-scallion-peanut-salsa'

# 3. Fetch the HTML content from the URL
response = requests.get(url)
if response.status_code == 200:
    html_content = response.text
else:
    raise Exception(f"Failed to fetch the page. Status code: {response.status_code}")

# 4. Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(html_content, 'html.parser')

# 5. Find the div containing the preparation steps using a wildcard match
preparation_div = soup.select_one('div[class*="InstructionsWrapper"]')

# Check if the parent div was found
if preparation_div is None:
    raise Exception("Could not find the preparation steps container.")


groups = soup.find_all('div[class*="InstructionGroupHed"]')
    #preparation_steps.append(prep_group)

# 6. Extract all the steps within the <ol> tag
steps = preparation_div.find_all('p')

# 7. Iterate over each step and collect the text
preparation_steps = []
for step in steps:
		
    step_text = step.get_text(strip=True)
    preparation_steps.append(step_text)

# 8. Print the extracted preparation steps
for idx, step in enumerate(preparation_steps, start=1):
    print(f"Step {idx}: {step}")
