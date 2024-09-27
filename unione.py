from flask import Flask, request, render_template_string
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import logging
import time
import concurrent.futures

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

chromedriver_path = r'C:\Users\fabio\OneDrive\Desktop\webdriver\chromedriver.exe'
chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

def create_driver():
    options = Options()
    options.binary_location = chrome_path
    options.add_argument('--headless')  # Run in headless mode to avoid displaying the browser
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    service = ChromeService(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# Function for searching on Amazon
def search_amazon(query):
    driver = create_driver()
    all_product_info = []
    current_page = 1
    max_pages = 7

    try:
        driver.get('https://www.amazon.it')
        logging.debug("Amazon page loaded")

        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'twotabsearchtextbox'))
        )
        logging.debug("Search box found")

        search_box.clear()
        search_box.send_keys(query)
        search_box.send_keys(Keys.RETURN)
        logging.debug(f"Search for '{query}' sent")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.s-main-slot'))
        )
        logging.debug("Search results loaded")

        def extract_product_info():
            elements = driver.find_elements(By.CSS_SELECTOR, 'div.sg-col-inner')
            product_info = []
            for element in elements:
                try:
                    name = element.find_element(By.CSS_SELECTOR, 'span.a-size-base-plus.a-color-base.a-text-normal').text
                    try:
                        price_whole = element.find_element(By.CSS_SELECTOR, 'span.a-price-whole').text
                        price_fraction = element.find_element(By.CSS_SELECTOR, 'span.a-price-fraction').text
                        price = f"{price_whole},{price_fraction} €"
                    except:
                        price = "N/A"
                    try:
                        image = element.find_element(By.CSS_SELECTOR, 'img.s-image').get_attribute('src')
                    except:
                        image = "N/A"
                    product_info.append({'name': name, 'price': price, 'image': image})
                except Exception as e:
                    logging.debug(f"Error extracting product: {e}")
                    continue
            return product_info

        while current_page <= max_pages:
            page_product_info = extract_product_info()
            all_product_info.extend(page_product_info)

            if current_page == 1:
                try:
                    privacy_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.ID, 'sp-cc-accept'))
                    )
                    privacy_button.click()
                except Exception as e:
                    logging.debug(f"Error clicking privacy button: {e}")

            try:
                next_button_svg = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'svg[aria-hidden="true"]'))
                )
                next_button_svg.click()
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.s-main-slot'))
                )
                current_page += 1
            except Exception as e:
                logging.debug(f"Error navigating to the next page: {e}")
                break

    except Exception as e:
        logging.debug(f"Request error: {e}")
        all_product_info = [{'name': f"Request error: {e}", 'price': '', 'image': ''}]

    finally:
        driver.quit()

    return all_product_info, current_page

# Function for searching on eBay
def process_ebay_page(driver, products, product_ids):
    page_content = driver.page_source
    soup = BeautifulSoup(page_content, 'html.parser')
    results_section = soup.find(class_="srp-results srp-list clearfix")

    if results_section:
        items = results_section.find_all(class_="s-item__wrapper clearfix")

        for item in items:
            title = item.find(class_="s-item__title").get_text(strip=True)
            price = item.find(class_="s-item__price").get_text(strip=True)
            link = item.find('a', class_="s-item__link")['href']
            product_id = link.split("/")[-1]

            # Avoid adding duplicates by checking the product ID
            if product_id not in product_ids:
                product_ids.add(product_id)

                img_tag = item.find('img', src=True)
                image = img_tag['src'] if img_tag and img_tag['src'].startswith('https://i.ebayimg.com') else None

                products.append({
                    'title': title,
                    'price': price,
                    'link': link,
                    'image': image
                })

    return soup

def find_last_page(soup):
    pagination = soup.find(class_="pagination__items")
    if pagination:
        pages = pagination.find_all('a')
        last_page = max([int(page.get_text()) for page in pages if page.get_text().isdigit()])
        return last_page
    return 1

def search_ebay(query):
    driver = create_driver()
    products = []
    product_ids = set()
    page_number = 1

    try:
        driver.get('https://www.ebay.com')
        search_box = driver.find_element('name', '_nkw')
        search_box.send_keys(query)
        search_box.send_keys(Keys.RETURN)
        time.sleep(5)

        # Process the first page and determine the last page
        process_ebay_page(driver, products, product_ids)
        last_page = find_last_page(BeautifulSoup(driver.page_source, 'html.parser'))

        while page_number < last_page:
            page_number += 1
            next_page_url = f'https://www.ebay.it/sch/i.html?_from=R40&_nkw={query}&_sacat=0&_pgn={page_number}'
            driver.get(next_page_url)
            time.sleep(5)
            process_ebay_page(driver, products, product_ids)

    finally:
        driver.quit()

    return products, page_number

# HTML Template
html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Amazon and eBay Search</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            color: #333;
        }
        h1 {
            color: #333;
        }
        form {
            margin: 20px 0;
            display: flex;
            justify-content: space-between;
        }
        form input[type="text"] {
            flex: 1;
            padding: 10px;
            border-radius: 5px 0 0 5px;
            border: 1px solid #ccc;
            font-size: 16px;
            outline: none;
            margin-right: 10px;
        }
        form button {
            padding: 10px 20px;
            border-radius: 0 5px 5px 0;
            border: none;
            background-color: #007bff;
            color: white;
            font-size: 16px;
            cursor: pointer;
            transition: background-color 0.3s;
        }
        form button:hover {
            background-color: #0056b3;
        }
        .results-container {
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
        }
        .results {
            width: 48%;
            display: flex;
            flex-direction: column;
        }
        .results h2 {
            text-align: center;
            margin-bottom: 10px;
        }
        .product-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        .product-item {
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            overflow: hidden;
            text-align: center;
            padding: 20px;
            transition: transform 0.3s, box-shadow 0.3s;
        }
        .product-item:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2);
        }
        .product-item img {
            max-width: 100%;
            height: auto;
            border-bottom: 1px solid #f0f0f0;
            margin-bottom: 15px;
        }
        .product-item p {
            font-size: 16px;
            margin: 10px 0;
            color: #555;
        }
    </style>
</head>
<body>
    <h1>Amazon and eBay Search</h1>
    <form method="POST" action="/search">
        <input type="text" id="query" name="query" placeholder="Enter product name" required>
        <button type="submit">Search</button>
    </form>
    <div class="results-container">
        <div class="results">
            <h2>Amazon Results ({{ amazon_count }} products found on {{ amazon_pages }} pages)</h2>
            <div class="product-container">
                {% for result in amazon_results %}
                    <div class="product-item">
                        <img src="{{ result.image }}" alt="Product Image">
                        <p>{{ result.name }}</p>
                        <p>Price: {{ result.price }}</p>
                    </div>
                {% endfor %}
            </div>
        </div>
        <div class="results">
            <h2>eBay Results ({{ ebay_count }} products found on {{ ebay_pages }} pages)</h2>
            <div class="product-container">
                {% for result in ebay_results %}
                    <div class="product-item">
                        <img src="{{ result.image }}" alt="Product Image">
                        <p>{{ result.title }}</p>
                        <p>Price: {{ result.price }}</p>
                        <p><a href="{{ result.link }}" target="_blank">View on eBay</a></p>
                    </div>
                {% endfor %}
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(html_template, amazon_results=[], ebay_results=[], amazon_count=0, ebay_count=0, amazon_pages=0, ebay_pages=0)

@app.route('/search', methods=['POST'])
def search():
    query = request.form['query']
    with concurrent.futures.ThreadPoolExecutor() as executor:
        amazon_future = executor.submit(search_amazon, query)
        ebay_future = executor.submit(search_ebay, query)
        amazon_results, amazon_pages = amazon_future.result()
        ebay_results, ebay_pages = ebay_future.result()
    amazon_count = len(amazon_results)
    ebay_count = len(ebay_results)
    return render_template_string(html_template, amazon_results=amazon_results, ebay_results=ebay_results, amazon_count=amazon_count, ebay_count=ebay_count, amazon_pages=amazon_pages, ebay_pages=ebay_pages)

if __name__ == '__main__':
    app.run(debug=True) 
