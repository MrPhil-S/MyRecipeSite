import csv

import requests
from recipe_scrapers import scrape_html

#SELECT r.recipe_id  , source_url
#FROM recipe r
#left join `recipe__instruction`  ri
#on  r.recipe_id = ri.recipe_id
#WHERE ri.recipe_id is null
#and length(source_url) > 1


urls = []

name = 'bob'
x = []
with open("output.csv", "w", newline="") as file:

    for i, url in enumerate(urls):
        try:
            html = requests.get(url, headers={"User-Agent": f"Pie eater {name}"}).content

            print(f'{round(i/len(urls)*100,2)}% trying {url}...')
            scraper = scrape_html(html, org_url=url, wild_mode=False)
            instructions_list = scraper.instructions_list()
        except Exception as e:
            instructions_list = e
            print(e)

        x.append((url,instructions_list))
print('DONE scraping')
print(x)
    # Write to a CSV file
with open("output.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.writer(file)
    writer.writerows(x)
print('file done')
