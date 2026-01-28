#!/usr/bin/env python3
#
# Backend scraper for AZ-TRBONET CallWatch system
# Logs into the backend, navigates to call records, and scrapes all pages
#
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from datetime import datetime
import pandas as pd
import numpy as np
import requests
import json
import sys
import argparse
import traceback
import time

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Scrape AZ-TRBONET backend call records')
parser.add_argument('--user', required=True, help='Login username')
parser.add_argument('--password', required=True, help='Login password')
parser.add_argument('--headless', action='store_true', default=True, help='Run browser in headless mode (default: True)')
parser.add_argument('--no-headless', action='store_false', dest='headless', help='Run browser with visible window')
args = parser.parse_args()

# Base URL for the backend
BASE_URL = 'http://184.191.128.77:42420'

# MWave group ID in the backend table
MWAVE_GROUP_ID = '310564'

# CSV file paths
cur_user_file = 'code_plug.csv'
add_user_file = 'add_users.csv'
mwg_user_file = 'mwg_users.csv'

# API URLs for enrichment
callsign_url = 'https://database.radioid.net/api/dmr/user/?callsign='
id_url = 'https://database.radioid.net/api/dmr/user/?id='


def setup_driver(headless=True):
    """Initialize and return a Selenium WebDriver instance."""
    try:
        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/brave-browser"
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        print("ERROR: Unable to get a webdriver instance:", e)
        traceback.print_exc()
        sys.exit(1)


def login(driver, username, password):
    """Navigate to login page and authenticate."""
    print("Navigating to login page...")
    driver.get(BASE_URL)
    time.sleep(2)

    try:
        # Find login form elements by name
        username_field = driver.find_element(By.NAME, 'user')
        password_field = driver.find_element(By.NAME, 'pass')
        login_button = driver.find_element(By.NAME, 'Login')

        print("Entering credentials...")
        username_field.clear()
        username_field.send_keys(username)
        password_field.clear()
        password_field.send_keys(password)
        login_button.click()

        time.sleep(3)
        print("Login submitted.")
        return True

    except NoSuchElementException as e:
        print(f"ERROR: Could not find login form elements: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Login failed: {e}")
        traceback.print_exc()
        sys.exit(1)


def navigate_to_calls(driver):
    """Navigate to the Calls section and select AZ-TRBONET."""
    print("Navigating to Calls section...")

    try:
        # Switch to left navigation frame and click Calls
        driver.switch_to.frame('leftmainpagebar')
        calls_button = driver.find_element(By.XPATH, '//input[@value="Calls"]')
        calls_button.click()
        time.sleep(2)
        print("Clicked Calls button.")

        # Switch back to default content, then to main frame
        driver.switch_to.default_content()
        driver.switch_to.frame('main')

        # Click AZ-TRBONET button
        aztrbo_button = driver.find_element(By.XPATH, '//input[@value="AZ-TRBONET"]')
        aztrbo_button.click()
        time.sleep(2)
        print("Clicked AZ-TRBONET button.")

        return True

    except NoSuchElementException as e:
        print(f"ERROR: Could not find navigation element: {e}")
        return False
    except Exception as e:
        print(f"ERROR: Navigation failed: {e}")
        traceback.print_exc()
        return False


def set_page_size(driver, size=100):
    """Set the page size to maximum (100)."""
    print(f"Setting page size to {size}...")

    try:
        page_size_select = Select(driver.find_element(By.NAME, 'selectpagesize'))
        page_size_select.select_by_visible_text(str(size))
        time.sleep(2)
        print(f"Page size set to {size}.")
        return True

    except NoSuchElementException:
        print("WARN: Could not find page size selector.")
        return False
    except Exception as e:
        print(f"WARN: Could not set page size: {e}")
        return False


def get_total_pages(driver):
    """Get the total number of pages available."""
    try:
        page_num_select = Select(driver.find_element(By.NAME, 'selectpagenumber'))
        options = page_num_select.options
        return len(options)
    except:
        return 1


def go_to_page(driver, page_num):
    """Navigate to a specific page number (1-indexed)."""
    try:
        page_num_select = Select(driver.find_element(By.NAME, 'selectpagenumber'))
        page_num_select.select_by_visible_text(str(page_num))
        time.sleep(1)
        return True
    except Exception as e:
        print(f"WARN: Could not navigate to page {page_num}: {e}")
        return False


def scrape_table_page(driver):
    """Scrape data from current table page.

    Backend table columns:
    - Column 7 (index 6): Radio ID
    - Column 10 (index 9): Group ID (310564 = MWave)
    - Column 12 (index 11): Network

    Returns list of tuples: (radio_id, group_id, network)
    """
    data = []

    try:
        # Find the data table (first table on page)
        tables = driver.find_elements(By.TAG_NAME, 'table')
        if not tables:
            return data

        table = tables[0]
        rows = table.find_elements(By.TAG_NAME, 'tr')

        # Skip header row (index 0)
        for row in rows[1:]:
            try:
                cells = row.find_elements(By.TAG_NAME, 'td')

                if len(cells) >= 12:
                    # Column 7 (index 6): Radio ID
                    radio_id_str = cells[6].text.strip()
                    # Column 10 (index 9): Group ID
                    group_id = cells[9].text.strip()
                    # Column 12 (index 11): Network
                    network = cells[11].text.strip()

                    if radio_id_str:
                        try:
                            radio_id = int(radio_id_str)
                            data.append((radio_id, group_id, network))
                        except ValueError:
                            continue

            except StaleElementReferenceException:
                continue
            except Exception:
                continue

    except Exception as e:
        print(f"WARN: Error scraping table: {e}")

    return data


def scrape_all_pages(driver):
    """Scrape data from all available pages.

    Returns list of tuples: (radio_id, group_id, network)
    """
    all_data = []

    # Set page size to maximum
    set_page_size(driver, 100)
    time.sleep(1)

    # Get total number of pages
    total_pages = get_total_pages(driver)
    print(f"Total pages available: {total_pages}")

    for page_num in range(1, total_pages + 1):
        print(f"Scraping page {page_num}/{total_pages}...")

        if page_num > 1:
            if not go_to_page(driver, page_num):
                print(f"Could not navigate to page {page_num}, stopping.")
                break
            time.sleep(1)

        page_data = scrape_table_page(driver)

        if not page_data:
            print(f"No data on page {page_num}, stopping.")
            break

        all_data.extend(page_data)
        print(f"  Collected {len(page_data)} records from page {page_num}.")

    return all_data


def load_csv_files():
    """Load existing CSV files."""
    try:
        code_plug = pd.read_csv(cur_user_file)
    except Exception as e:
        print(f'ERROR: Unable to access {cur_user_file}: {e}')
        sys.exit(1)

    try:
        add_users = pd.read_csv(add_user_file)
    except Exception as e:
        print(f'ERROR: Unable to access {add_user_file}: {e}')
        sys.exit(1)

    try:
        mwg_users = pd.read_csv(mwg_user_file)
    except Exception as e:
        print(f'ERROR: Unable to access {mwg_user_file}: {e}')
        sys.exit(1)

    return code_plug, add_users, mwg_users


def process_scraped_data(data, code_plug):
    """Process scraped data to identify new users.

    Args:
        data: List of tuples (radio_id, group_id, network)
        code_plug: Existing code plug DataFrame

    Returns:
        Tuple of (new_ids, mwg_ids) - lists of radio IDs
    """
    new_ids = []
    mwg_ids = []

    for radio_id, group_id, network in data:
        # Check for MWave group (ID 310564)
        if group_id == MWAVE_GROUP_ID:
            mwg_ids.append(radio_id)
            if len(code_plug[code_plug['RADIO_ID'] == radio_id]) == 0:
                if radio_id not in new_ids:
                    new_ids.append(radio_id)

        # Check for AZ-TRBONET network
        if network == 'AZ-TRBONET':
            if len(code_plug[code_plug['RADIO_ID'] == radio_id]) == 0:
                if radio_id not in new_ids:
                    new_ids.append(radio_id)

    return list(set(new_ids)), list(set(mwg_ids))


def enrich_new_users(new_ids):
    """Fetch user info from radioid.net API for new radio IDs.

    Returns DataFrame with columns: RADIO_ID, CALLSIGN, FIRST_NAME, STATE
    """
    new_users = pd.DataFrame(columns=['RADIO_ID', 'CALLSIGN', 'FIRST_NAME', 'STATE'])

    for radio_id in new_ids:
        try:
            user_json = requests.get(id_url + str(radio_id), timeout=10)
            callsign = user_json.json()['results'][0]['callsign']
            users_json = requests.get(callsign_url + callsign, timeout=10)
            new_entries = users_json.json()['results']

            for entry in new_entries:
                row = [
                    entry['id'],
                    entry['callsign'],
                    entry['fname'],
                    entry['state']
                ]
                new_users.loc[len(new_users)] = row

        except Exception:
            continue

    return new_users.drop_duplicates(subset=None, keep="first", inplace=False)


def update_mwg_users(mwg_ids, mwg_users):
    """Update MWave group users CSV with new entries."""
    for radio_id in mwg_ids:
        try:
            user_json = requests.get(id_url + str(radio_id), timeout=10)
            new_entries = user_json.json()['results']

            for entry in new_entries:
                if len(mwg_users[mwg_users['RADIO_ID'] == entry['id']]) == 0:
                    row = [
                        entry['id'],
                        entry['callsign'],
                        entry['fname'],
                        entry['state']
                    ]
                    mwg_users.loc[len(mwg_users)] = row

        except Exception:
            continue

    return mwg_users


def save_csv_files(code_plug, add_users, mwg_users, new_users):
    """Save updated CSV files."""
    # Save MWave users
    mwg_users = mwg_users.reset_index(drop=True)
    mwg_users.to_csv(mwg_user_file, index=False)

    # Save new users to code plug and add_users if any found
    if len(new_users) > 0:
        code_plug = pd.concat([code_plug, new_users], axis=0)
        code_plug = code_plug.drop_duplicates(subset=['RADIO_ID'], keep='first')
        code_plug = code_plug.reset_index(drop=True)
        code_plug.to_csv(cur_user_file, index=False)

        add_users = pd.concat([add_users, new_users], axis=0)
        add_users = add_users.reset_index(drop=True)
        add_users.to_csv(add_user_file, index=False)


def main():
    """Main entry point."""
    print("=" * 60)
    print("AZ-TRBONET Backend Scraper")
    print("=" * 60)

    # Setup browser
    driver = setup_driver(headless=args.headless)

    try:
        # Login
        login(driver, args.user, args.password)

        # Navigate to calls section
        if not navigate_to_calls(driver):
            print("ERROR: Could not navigate to calls section.")
            sys.exit(1)

        # Scrape all pages
        data = scrape_all_pages(driver)

        if not data:
            print("ERROR: No data was collected.")
            sys.exit(1)

        print(f"\nTotal records collected: {len(data)}")

    finally:
        driver.close()

    # Load existing CSV files
    code_plug, add_users, mwg_users = load_csv_files()

    # Process scraped data
    new_ids, mwg_ids = process_scraped_data(data, code_plug)
    print(f"New radio IDs to process: {len(new_ids)}")
    print(f"MWave group IDs found: {len(mwg_ids)}")

    # Enrich new users via API
    print("\nEnriching new users via radioid.net API...")
    new_users = enrich_new_users(new_ids)

    # Update MWave users
    print("Updating MWave user records...")
    mwg_users = update_mwg_users(mwg_ids, mwg_users)

    # Save results
    print("\nSaving results...")
    save_csv_files(code_plug, add_users, mwg_users, new_users)

    # Summary
    print("\n" + "=" * 60)
    print(f"{len(data)} Radio IDs examined.")
    print(f"SUCCESS: {len(new_users)} New Users discovered.")
    print("=" * 60)


if __name__ == '__main__':
    main()
