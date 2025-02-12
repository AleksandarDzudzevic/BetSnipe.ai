import asyncio
import sys
from pathlib import Path
from datetime import datetime
import time
import csv


# ajmo kvotara
def save_arbitrage(text):
    """Save arbitrage opportunity to file if it's unique and meets profit criteria"""
    match_name = text.split("!")[0].split("for ")[-1]
    profit_lines = [line for line in text.split("\n") if "Profit:" in line]
    if not profit_lines:
        return

    profit = float(profit_lines[0].split("$")[1].strip())
    if profit < 1.4 or profit > 4.0:
        return

    try:
        with open("arbitrageopps.txt", "r", encoding="utf-8") as f:
            content = f.read()
        arb_count = content.count("Arbitrage #")
        if match_name in content:
            print(f"Arbitrage for {match_name} already recorded")
            return
    except FileNotFoundError:
        content = ""
        arb_count = 0

    with open("arbitrageopps.txt", "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 50 + "\n")
        f.write(f"Arbitrage #{arb_count + 1}\n")
        f.write(f"Found at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(text + "\n")


async def run_script(script):
    """Run a Python script with the correct path"""
    # Get absolute path to the script directly - no need to handle bookmaker separately
    script_path = Path(__file__).parent / script

    try:
        if not script_path.exists():
            print(f"❌ Script not found: {script_path}")
            return False

        process = await asyncio.create_subprocess_exec(
            sys.executable,  # Use sys.executable instead of "python"
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        success = process.returncode == 0
        if success:
            print(f"✅ {script} completed successfully")
        else:
            print(f"❌ {script} failed")
            if stderr:
                print(f"Error: {stderr.decode()}")
        return success
    except Exception as e:
        print(f"❌ {script} failed with error: {str(e)}")
        return False


async def run_combine_script():
    """Run the combine_games.py script and process its output"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "combine_games.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if process.stdout is None:
        print("Error: Failed to capture stdout")
        return

    current_arb = []
    capturing = False

    while True:
        line = await process.stdout.readline()
        if not line:
            break

        output = line.decode().strip()
        print(output)

        if "ARBITRAGE OPPORTUNITY FOUND" in output:
            capturing = True
            current_arb = [output]
        elif capturing and "Profit:" in output:
            current_arb.append(output)
            save_arbitrage("\n".join(current_arb))
            capturing = False
            current_arb = []
        elif capturing:
            current_arb.append(output)


def create_missing_csv_files():
    """Create CSV files in PythonScrapper folder only"""
    # Get the PythonScrapper directory path
    base_path = Path(__file__).parent
    if base_path.name != "betsnipe.ai":
        print("Warning: Script is not in PythonScrapper directory")
        return

    csv_files = {
        "Tennis": [
            "admiral_tennis_matches.csv",
            "maxbet_tennis_matches.csv",
            "meridian_tennis_matches.csv",
            "mozzart_tennis_matches.csv",
            "soccerbet_tennis_matches.csv",
        ],
        "Football": [
            "admiral_football_matches.csv",
            "maxbet_football_matches.csv",
            "meridian_football_matches.csv",
            "mozzart_football_matches.csv",
            "soccerbet_football_matches.csv",
        ],
        "Basketball": [
            "admiral_basketball_matches.csv",
            "maxbet_basketball_matches.csv",
            "meridian_basketball_matches.csv",
            "mozzart_basketball_matches.csv",
            "soccerbet_basketball_matches.csv",
        ],
        "Hockey": [
            "admiral_hockey_matches.csv",
            "maxbet_hockey_matches.csv",
            "meridian_hockey_matches.csv",
            "mozzart_hockey_matches.csv",
            "soccerbet_hockey_matches.csv",
        ],
        "Table Tennis": [
            "admiral_tabletennis_matches.csv",
            "maxbet_tabletennis_matches.csv",
            "meridian_tabletennis_matches.csv",
            "mozzart_tabletennis_matches.csv",
            "soccerbet_tabletennis_matches.csv",
        ],
    }

    for sport, files in csv_files.items():
        print(f"\nChecking {sport} CSV files:")
        for filename in files:
            file_path = base_path / filename
            # Only create if we're in PythonScrapper directory
            if not file_path.exists():
                print(f"Creating {file_path}")
                with open(file_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Match", "Type", "Odds 1", "Odds 2", "Odds 3"])
            else:
                print(f"✅ {file_path} exists")


async def main():
    start_time = time.time()

    create_missing_csv_files()

    # Get the base path for scripts
    base_path = Path(__file__).parent

    # Run all scripts in parallel
    scripts = [
        # Tennis
        "Mozzart/mozzartTenis.py",
        "Admiral/admiralTenis.py",
        "Maxbet/maxbetTenis.py",
        "Meridian/meridianTenis.py",
        "Soccerbet/soccerbetTenis.py",
        # "Superbet/superbetTenis.py",
        # Table Tennis
        "Mozzart/mozzartStoniTenis.py",
        "Admiral/admiralStoniTenis.py",
        "Maxbet/maxbetStoniTenis.py",
        "Meridian/meridianStoniTenis.py",
        "Soccerbet/soccerbetStoniTenis.py",
        # "Superbet/superbetStoniTenis.py",
        # Football
        "Mozzart/mozzartFudbal.py",
        "Admiral/admiralFudbal.py",
        "Maxbet/maxbetFudbal.py",
        "Meridian/meridianFudbal.py",
        "Soccerbet/soccerbetFudbal.py",
        # "Superbet/superbetFudbal.py",
        # Basketball
        "Mozzart/mozzartKosarka.py",
        "Admiral/admiralKosarka.py",
        "Maxbet/maxbetKosarka.py",
        "Meridian/meridianKosarka.py",
        "Soccerbet/soccerbetKosarka.py",
        # "Superbet/superbetKosarka.py",
        # Hockey
        "Mozzart/mozzartHokej.py",
        "Admiral/admiralHokej.py",
        "Maxbet/maxbetHokej.py",
        "Meridian/meridianHokej.py",
        "Soccerbet/soccerbetHokej.py",
        # "Superbet/superbetHokej.py",
    ]

    # Filter only existing scripts and print status
    existing_scripts = []
    print("\nChecking for scripts:")
    for script in scripts:
        script_path = base_path / script
        if script_path.exists():
            existing_scripts.append(script)
            print(f"✅ Found {script}")
        else:
            print(f"❌ Missing {script}")

    if not existing_scripts:
        print("\nNo scripts found to execute!")
        return

    # Run all scripts in parallel
    tasks = [run_script(script) for script in existing_scripts]
    results = await asyncio.gather(*tasks)

    # Print summary
    successful = sum(1 for r in results if r)
    total = len(results)
    print(f"\nCompleted: {successful}/{total} scripts successful")

    if successful < total:
        print("\nFailed scripts:")
        for script, result in zip(existing_scripts, results):
            if not result:
                print(f"❌ {script}")

    # Calculate and print total runtime
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    print(f"\nTotal runtime: {minutes} minutes and {seconds} seconds")


async def run_full_scrape():
    """Run the full scraping process"""
    print(
        f"\nStarting scheduled scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await main()
    print(
        f"Completed scheduled scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )


if __name__ == "__main__":
    # Run immediately on start
    asyncio.run(run_full_scrape())
