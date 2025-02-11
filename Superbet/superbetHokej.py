import time
from os.path import split
import csv
import logging

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Constants

WEBSITE_URL = "https://superbet.rs/sportske-opklade/hokej-na-ledu/sve"


def setup_driver():
    service = Service(ChromeDriverManager().install())
    options = Options()

    # Headless mode settings
    options.add_argument("--headless=new")  # New headless mode for Chrome
    options.add_argument("--disable-gpu")  # Required for Windows
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")  # Set window size in headless mode

    # Additional options for stability
    options.add_argument("--start-maximized")
    options.add_argument("--remote-debugging-port=9222")

    driver = webdriver.Chrome(service=service, options=options)
    return driver


def scroll_and_get_matches(driver):
    teamNames = []
    odds = []
    processed_matches = set()
    scroll_attempts = 0
    max_attempts = 10
    MAX_MATCHES = 200
    total_matches_expected = None

    try:
        # Wait for the matches container
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "event-row-container"))
        )

        while scroll_attempts < max_attempts:
            print("Starting scroll iteration...")
            if len(processed_matches) >= MAX_MATCHES:
                print(f"Reached {MAX_MATCHES} matches limit. Stopping...")
                break

            # Get current matches
            matches = driver.find_elements(By.CLASS_NAME, "event-row-container")
            current_count = len(matches)
            print(f"Current visible matches: {current_count}")

            for match in matches:
                try:
                    # Get team names
                    competitors = match.find_elements(
                        By.CLASS_NAME, "event-competitor__name"
                    )
                    if len(competitors) < 2:
                        continue

                    team1 = competitors[0].text.strip()
                    team2 = competitors[1].text.strip()
                    team_names = f"{team1}\n{team2}"

                    if team_names in processed_matches:
                        continue

                    # Get odds - for football we need 3 odds (1, X, 2)
                    try:
                        odd_values = match.find_elements(
                            By.CLASS_NAME, "odd-button__odd-value-new"
                        )
                        if len(odd_values) >= 3:  # Changed from 2 to 3
                            odds1 = odd_values[0].text.strip()
                            oddsx = odd_values[1].text.strip()  # Draw odds
                            odds2 = odd_values[2].text.strip()

                            teamNames.append(team_names)
                            odds.append([odds1, oddsx, odds2])  # Added draw odds
                            processed_matches.add(team_names)
                            print(
                                f"Added match: {team_names} with odds {[odds1, oddsx, odds2]}"
                            )

                    except Exception as e:
                        print(f"Error getting odds for match {team_names}: {e}")
                        continue

                except Exception as e:
                    print(f"Error processing match: {e}")
                    continue

            # Scroll down
            try:
                driver.execute_script("window.scrollBy(0, 2000);")

            except Exception as e:
                print(f"Error scrolling: {e}")
                scroll_attempts += 1
                continue

            # Check for new matches
            new_matches = driver.find_elements(By.CLASS_NAME, "event-row-container")
            if len(new_matches) <= current_count:
                scroll_attempts += 1
                print(f"No new matches found, attempt {scroll_attempts}/{max_attempts}")
            else:
                scroll_attempts = 0
                print(f"Found {len(new_matches) - current_count} new matches!")

            print(f"Total unique matches processed so far: {len(processed_matches)}")

        print(f"Final number of matches processed: {len(teamNames)}")
        return teamNames, odds

    except Exception as e:
        print(f"Fatal error in scroll_and_get_matches: {str(e)}")
        raise


def process_player_names(player_names):
    """Convert full player names to combined format"""
    try:
        teams = player_names.split("\n")
        if len(teams) != 2:
            return None

        processed_names = []
        for team in teams:
            team = team.strip()
            words = team.split()
            if not words:
                return None

            # If team name has only one word and it's 3 characters, use it
            if len(words) == 1 and len(words[0]) == 3:
                processed_name = words[0][0].upper() + words[0][1:]
            else:
                # Find first word longer than 3 characters
                first_long_word = next((word for word in words if len(word) > 3), None)
                if not first_long_word:
                    return None
                processed_name = first_long_word[0].upper() + first_long_word[1:]

            processed_names.append(processed_name)

        if len(processed_names) == 2:
            return f"{processed_names[0]}{processed_names[1]}"
        return None

    except Exception as e:
        print(f"Error processing names {player_names}: {e}")
        return None


def handle_popups(driver):
    try:
        # Wait for and click cookie consent button
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()
        print("Accepted cookies")

        # Wait for and click close button
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "sds-icon-navigation-close"))
        ).click()
        print("Closed popup")

    except Exception as e:
        print(f"Error handling popups: {e}")


def main():
    driver = setup_driver()
    try:
        driver.get(WEBSITE_URL)
        handle_popups(driver)

        try:
            teamNames, odds = scroll_and_get_matches(driver)

            with open(
                "superbet_hockey_matches.csv", "w", newline="", encoding="utf-8"
            ) as file:
                writer = csv.writer(file)
                writer.writerow(
                    ["Match", "Odds 1", "Odds X", "Odds 2"]
                )  # Updated header

                for i in range(len(teamNames)):
                    match_name = process_player_names(teamNames[i])
                    if match_name and i < len(odds):
                        writer.writerow(
                            [match_name, odds[i][0], odds[i][1], odds[i][2]]
                        )  # Added draw odds

            print(
                f"Successfully processed {len(teamNames)} matches and saved to superbet_hockey_matches.csv"
            )

        except Exception as e:
            print(f"An error occurred: {e}")

    except Exception as e:
        print(f"Error in main execution: {str(e)}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
