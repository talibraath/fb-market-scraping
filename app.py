import streamlit as st
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
from fuzzywuzzy import fuzz
from datetime import datetime
from selenium.webdriver.chrome.options import Options
import zipfile
import io
import os
import packaging.version


# Function to run the web scraping for exact matches
def scrape_facebook_marketplace_exact(city, product, min_price, max_price, city_code_fb):
    return scrape_facebook_marketplace(city, product, min_price, max_price, city_code_fb, exact=True)

# Function to run the web scraping for partial matches
def scrape_facebook_marketplace_partial(city, product, min_price, max_price, city_code_fb):
    return scrape_facebook_marketplace(city, product, min_price, max_price, city_code_fb, exact=False)

# Main scraping function with an exact match flag
def scrape_facebook_marketplace(city, product, min_price, max_price, city_code_fb, exact, sleep_time=3):
    chrome_options = uc.ChromeOptions()
    chrome_options.headless = False
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--start-maximized")
    
    try:
        browser = uc.Chrome(options=chrome_options)
        st.info("Browser initialized successfully")
        
        exact_param = 'true' if exact else 'false'
        
        # Try different URL format
        url = f"https://www.facebook.com/marketplace/category/search/?query={product}&exact={exact_param}&minPrice={min_price}&maxPrice={max_price}&region_id={city_code_fb}"
        st.info(f"Attempting to access URL: {url}")
        browser.get(url)
        
        # Wait longer for initial load
        time.sleep(15)
        
        st.info("Page loaded, checking for elements...")
        
        # Update the selectors to better target marketplace items
        selectors = [
            "div[class*='x3ct3a4'] a[role='link']",  # Main container with link
            "div[class*='x1xmf6yo']",  # Product card container
            "div[role='main'] div[style*='border-radius: 8px']"  # Product cards by style
        ]
        
        items = []
        for selector in selectors:
            items = browser.find_elements(By.CSS_SELECTOR, selector)
            if len(items) > 0:
                st.info(f"Found {len(items)} items using selector: {selector}")
                break
        
        # Scroll with more time between iterations
        count = 0
        last_height = browser.execute_script("return document.body.scrollHeight")
        while count < 5:
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(5)
            new_height = browser.execute_script("return document.body.scrollHeight")
            count += 1
            st.info(f"Scroll iteration {count}/5")
            if new_height == last_height:
                break
            last_height = new_height
            
        # Try to find items again after scrolling
        for selector in selectors:
            items = browser.find_elements(By.CSS_SELECTOR, selector)
            if len(items) > 0:
                st.info(f"Found {len(items)} total items after scrolling using selector: {selector}")
                break
        
        # Update the title selectors
        title_selectors = [
            "span[class*='x1lliihq']:not([class*='x193iq5w'])",  # Title text, excluding price
            "div[class*='x1gslohp'] span",  # Alternative title container
            "span[class*='xt0psk2']"  # Another common title class
        ]

        # Update the price selectors
        price_selectors = [
            "span[class*='x193iq5w']",  # Main price class
            "span[class*='x1s928wv']",  # Alternative price class
            "span[class*='x1lliihq'][class*='x193iq5w']"  # Combined price classes
        ]

        # Extract data from items
        extracted_data = []
        for item in items:
            try:
                # Get title
                title = None
                for selector in title_selectors:
                    try:
                        title_elem = item.find_element(By.CSS_SELECTOR, selector)
                        title = title_elem.text.strip()
                        if title and not title.startswith('$') and not title.lower() == 'free':
                            break
                    except:
                        continue

                # Get price
                price = None
                price_text = None
                for selector in price_selectors:
                    try:
                        price_elem = item.find_element(By.CSS_SELECTOR, selector)
                        price_text = price_elem.text.strip()
                        if price_text:
                            if price_text.lower() == 'free':
                                price = 0
                            else:
                                price = float(price_text.replace('$', '').replace(',', ''))
                            break
                    except:
                        continue

                # Get URL
                url = item.get_attribute('href')
                if not url:
                    try:
                        url = item.find_element(By.CSS_SELECTOR, "a").get_attribute('href')
                    except:
                        continue

                if title and url:  # Only add items with at least title and URL
                    extracted_data.append({
                        'title': title,
                        'price': price,
                        'price_text': price_text,  # Keep original price text
                        'location': city,
                        'url': url
                    })
                    st.info(f"Found item: {title} - {price_text}")  # Debug info

            except Exception as e:
                st.warning(f"Failed to extract item data: {str(e)}")
                continue
        
        st.info(f"Successfully extracted {len(extracted_data)} items")
        
        # Create DataFrame with better column ordering
        items_df = pd.DataFrame(extracted_data)
        if not items_df.empty:
            items_df = items_df[['title', 'price', 'price_text', 'location', 'url']]
            
        return items_df, len(items)
        
    except Exception as e:
        st.error(f"Error during scraping: {str(e)}")
        return pd.DataFrame(), 0
    finally:
        try:
            browser.quit()
            st.info("Browser closed successfully")
        except:
            st.warning("Could not close browser properly")

# Streamlit UI
st.set_page_config(page_title="Facebook Marketplace Scraper", layout="wide")
st.title("🏷 Facebook Marketplace Scraper")
st.markdown("""Welcome to the Facebook Marketplace Scraper!  
Easily find products in your city and filter by price.""")

# Initialize session state for storing marketplaces and results
if "marketplaces" not in st.session_state:
    st.session_state["marketplaces"] = []

if "scraped_data" not in st.session_state:
    st.session_state["scraped_data"] = None

# Input fields with better layout and styling
with st.form(key='input_form'):
    col1, col2 = st.columns(2)
    
    with col1:
        city = st.text_input("City", placeholder="Enter city name...")
        product = st.text_input("Product", placeholder="What are you looking for?")
    
    with col2:
        min_price = st.number_input("Minimum Price", min_value=0, value=0, step=1)
        max_price = st.number_input("Maximum Price", min_value=0, value=1000, step=1)
    
    city_code_fb = st.text_input("City Code for Facebook Marketplace", placeholder="Enter city code...")

    col3, col4 = st.columns([3, 1])
    with col3:
        submit_button = st.form_submit_button(label="🔍 Scrape Data")
    with col4:
        add_button = st.form_submit_button(label="🟢 Add")

# Handle adding a new marketplace
if add_button:
    if city and product and min_price <= max_price and city_code_fb:
        st.session_state["marketplaces"].append({
            "city": city,
            "product": product,
            "min_price": min_price,
            "max_price": max_price,
            "city_code_fb": city_code_fb,
        })
        st.success("Marketplace added successfully!")
    else:
        st.error("Please fill all fields correctly.")

# Show the current list of marketplaces
if st.session_state["marketplaces"]:
    st.write("### Current Marketplaces:")
    for i, entry in enumerate(st.session_state["marketplaces"]):
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.write(entry["city"])
        col2.write(entry["product"])
        col3.write(entry["min_price"])
        col4.write(entry["max_price"])
        col5.write(entry["city_code_fb"])
        if col6.button("❌ Remove", key=f"remove_{i}"):
            st.session_state["marketplaces"].pop(i)

# Handle scraping data
if submit_button:
    st.session_state["scraped_data"] = None
    individual_files = []

    if not st.session_state["marketplaces"]:
        st.error("Please add at least one marketplace to scrape data.")
    else:
        combined_df = pd.DataFrame()
        for marketplace in st.session_state["marketplaces"]:
            with st.spinner(f"Scraping data for {marketplace['city']}..."):
                items_df, total_links = scrape_facebook_marketplace_exact(
                    marketplace["city"],
                    marketplace["product"],
                    marketplace["min_price"],
                    marketplace["max_price"],
                    marketplace["city_code_fb"]
                )

            if not items_df.empty:
                if "scraped_data" not in st.session_state:
                    st.session_state["scraped_data"] = pd.DataFrame()

                st.session_state["scraped_data"] = pd.concat([st.session_state["scraped_data"], items_df], ignore_index=True)

                # Save individual result for each marketplace
                individual_file = io.StringIO()
                items_df.to_csv(individual_file, index=False)
                individual_file.seek(0)
                individual_files.append({
                    'name': f"{marketplace['city']}_{marketplace['product']}_result.csv",
                    'file': individual_file
                })

        if st.session_state["scraped_data"] is not None and not st.session_state["scraped_data"].empty:
            st.write("### Combined Match Results:")
            st.dataframe(st.session_state["scraped_data"])

            # Save combined CSV file
            combined_file = io.StringIO()
            st.session_state["scraped_data"].to_csv(combined_file, index=False)
            combined_file.seek(0)

            # Zip all individual and combined files into one package
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_data in individual_files:
                    zip_file.writestr(file_data['name'], file_data['file'].getvalue())
                zip_file.writestr("combined_results.csv", combined_file.getvalue())

            zip_buffer.seek(0)

            # Add download button
            st.download_button(
                label="Download All Results",
                data=zip_buffer,
                file_name="scraped_results.zip",
                mime="application/zip"
            )