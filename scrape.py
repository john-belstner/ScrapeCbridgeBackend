#!/usr/bin/env python3
#
# Public CallWatch scraper for AZ-TRBONET system
# Scrapes the public CallWatch interface (no authentication required)
# Limited to 200 records from the live call monitor
#
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import pandas as pd
import requests
import sys
import traceback

# CallWatch URL (public, no authentication required)
CALLWATCH_URL = 'http://184.191.128.77:42420/CallWatch'

# CSV file paths
CUR_USER_FILE = 'code_plug.csv'
ADD_USER_FILE = 'add_users.csv'
MWG_USER_FILE = 'mwg_users.csv'

# API URLs for user enrichment
CALLSIGN_URL = 'https://database.radioid.net/api/dmr/user/?callsign='
ID_URL = 'https://database.radioid.net/api/dmr/user/?id='

# Maximum rows to scrape from CallWatch table (rows 2-201)
MAX_ROWS = 200


def setup_driver():
    """Initialize and return a Selenium WebDriver instance.

    Configures Brave browser in headless mode with sandbox disabled
    for stability in automated environments.

    Returns:
        WebDriver instance configured for Brave browser
    """
    try:
        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/brave-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    except Exception as e:
        print(f"ERROR: Unable to get a webdriver instance: {e}")
        traceback.print_exc()
        sys.exit(1)


def scrape_callwatch(driver):
    """Scrape radio data from the CallWatch table.

    Navigates to CallWatch URL and extracts alias, group, and network
    information from the HTML table within the CallWatchBody frame.

    CallWatch table columns:
    - Column 1: Timestamp
    - Column 4: Alias (contains radio ID as last word)
    - Column 5: Group name (e.g., "MWave")
    - Column 7: Network (e.g., "AZ-TRBONET")

    Args:
        driver: Selenium WebDriver instance

    Returns:
        Tuple of (aliases, groups, networks) lists
    """
    aliases = []
    groups = []
    networks = []

    try:
        driver.get(CALLWATCH_URL)
        driver.switch_to.frame('CallWatchBody')

        # Scrape rows 2-201 (row 1 is header)
        for row in range(2, MAX_ROWS + 2):
            alias_xpath = f'//table/tbody/tr[{row}]/td[4]'
            group_xpath = f'//table/tbody/tr[{row}]/td[5]'
            network_xpath = f'//table/tbody/tr[{row}]/td[7]'

            try:
                alias = driver.find_element("xpath", alias_xpath).text
                group = driver.find_element("xpath", group_xpath).text
                network = driver.find_element("xpath", network_xpath).text

                aliases.append(alias)
                groups.append(group)
                networks.append(network)

            except StaleElementReferenceException:
                # Retry once on stale element
                alias = driver.find_element("xpath", alias_xpath).text
                group = driver.find_element("xpath", group_xpath).text
                network = driver.find_element("xpath", network_xpath).text

                aliases.append(alias)
                groups.append(group)
                networks.append(network)

            except Exception:
                # End of data reached
                break

    except Exception:
        print(f'ERROR: Unable to access {CALLWATCH_URL}')
        sys.exit(1)

    return aliases, groups, networks


def load_csv_files():
    """Load existing CSV database files.

    Returns:
        Tuple of (code_plug, add_users, mwg_users) DataFrames
    """
    try:
        code_plug = pd.read_csv(CUR_USER_FILE)
    except Exception as e:
        print(f'ERROR: Unable to access {CUR_USER_FILE}: {e}')
        sys.exit(1)

    try:
        add_users = pd.read_csv(ADD_USER_FILE)
    except Exception as e:
        print(f'ERROR: Unable to access {ADD_USER_FILE}: {e}')
        sys.exit(1)

    try:
        mwg_users = pd.read_csv(MWG_USER_FILE)
    except Exception as e:
        print(f'ERROR: Unable to access {MWG_USER_FILE}: {e}')
        sys.exit(1)

    return code_plug, add_users, mwg_users


def process_scraped_data(aliases, groups, networks, code_plug):
    """Process scraped data to identify new and MWave group users.

    Extracts radio IDs from alias strings and filters for:
    - MWave talk group members
    - AZ-TRBONET network users not in existing code plug

    Args:
        aliases: List of alias strings (radio ID is last word)
        groups: List of group names
        networks: List of network names
        code_plug: Existing code plug DataFrame

    Returns:
        Tuple of (new_ids, mwg_ids) lists of radio IDs
    """
    new_ids = []
    mwg_ids = []

    for i, alias in enumerate(aliases):
        info = alias.split()
        if not info:
            continue

        network = networks[i]
        group = groups[i]

        # Extract radio ID from last word of alias
        try:
            radio_id = int(info[-1])
        except ValueError:
            continue

        # Track MWave group users
        if 'MWave' in group:
            mwg_ids.append(radio_id)
            if len(code_plug[code_plug['RADIO_ID'] == radio_id]) == 0:
                if radio_id not in new_ids:
                    new_ids.append(radio_id)

        # Track AZ-TRBONET network users
        if network == 'AZ-TRBONET':
            if len(code_plug[code_plug['RADIO_ID'] == radio_id]) == 0:
                if radio_id not in new_ids:
                    new_ids.append(radio_id)

    return list(set(new_ids)), list(set(mwg_ids))


def enrich_new_users(new_ids):
    """Fetch user info from radioid.net API for new radio IDs.

    Queries the DMR database API to retrieve callsign, name, and state
    information for each new radio ID discovered.

    Args:
        new_ids: List of radio IDs to look up

    Returns:
        DataFrame with columns: RADIO_ID, CALLSIGN, FIRST_NAME, STATE
    """
    new_users = pd.DataFrame(columns=['RADIO_ID', 'CALLSIGN', 'FIRST_NAME', 'STATE'])

    for radio_id in new_ids:
        try:
            # Get callsign for this radio ID
            user_json = requests.get(f'{ID_URL}{radio_id}', timeout=10)
            callsign = user_json.json()['results'][0]['callsign']

            # Get all radio IDs associated with this callsign
            users_json = requests.get(f'{CALLSIGN_URL}{callsign}', timeout=10)
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
    """Update MWave group users DataFrame with new entries.

    Queries radioid.net API for each MWave group radio ID and adds
    new users not already in the MWave users database.

    Args:
        mwg_ids: List of radio IDs from MWave group
        mwg_users: Existing MWave users DataFrame

    Returns:
        Updated mwg_users DataFrame
    """
    for radio_id in mwg_ids:
        try:
            user_json = requests.get(f'{ID_URL}{radio_id}', timeout=10)
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
    """Save updated CSV database files.

    Appends new users to code_plug and add_users CSVs, and saves
    updated MWave users to mwg_users CSV.

    Args:
        code_plug: Main code plug DataFrame
        add_users: New users audit trail DataFrame
        mwg_users: MWave group users DataFrame
        new_users: Newly discovered users DataFrame
    """
    # Save MWave users
    mwg_users = mwg_users.reset_index(drop=True)
    mwg_users.to_csv(MWG_USER_FILE, index=False)

    # Save new users to code plug and add_users if any found
    if len(new_users) > 0:
        code_plug = pd.concat([code_plug, new_users], axis=0)
        code_plug = code_plug.reset_index(drop=True)
        code_plug.to_csv(CUR_USER_FILE, index=False)

        add_users = pd.concat([add_users, new_users], axis=0)
        add_users = add_users.reset_index(drop=True)
        add_users.to_csv(ADD_USER_FILE, index=False)


def main():
    """Main entry point for public CallWatch scraper."""
    # Setup browser
    driver = setup_driver()

    try:
        # Scrape CallWatch table
        aliases, groups, networks = scrape_callwatch(driver)
    finally:
        driver.close()

    if len(aliases) == 0:
        print(f'ERROR: No data was collected from {CALLWATCH_URL}')
        sys.exit(1)

    # Load existing CSV files
    code_plug, add_users, mwg_users = load_csv_files()

    # Process scraped data to identify new users
    new_ids, mwg_ids = process_scraped_data(aliases, groups, networks, code_plug)

    # Enrich new users via radioid.net API
    new_users = enrich_new_users(new_ids)

    # Update MWave group users
    mwg_users = update_mwg_users(mwg_ids, mwg_users)

    # Save results
    save_csv_files(code_plug, add_users, mwg_users, new_users)

    # Summary
    print(f'{len(aliases)} Radio IDs examined.')
    print(f'SUCCESS: {len(new_users)} New Users discovered.')


if __name__ == '__main__':
    main()
