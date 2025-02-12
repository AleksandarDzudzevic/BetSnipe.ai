import asyncio
import sys
from pathlib import Path
from datetime import datetime
import time
import csv
import importlib.util




async def run_script(script_path):
    while True:
        try:
            spec = importlib.util.spec_from_file_location("module", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, 'main'):
                await module.main()
            elif hasattr(module, 'scrape_all_matches'):
                module.scrape_all_matches()
            elif hasattr(module, 'get_mozzart_sports'):
                module.get_mozzart_sports()
            elif hasattr(module, 'get_soccerbet_sports'):
                module.get_soccerbet_sports()
            elif hasattr(module, 'fetch_maxbet_matches'):
                module.fetch_maxbet_matches()
            elif hasattr(module, 'get_tennis_odds'):
                module.get_tennis_odds()
            
            # Wait 5 minutes before next run
            await asyncio.sleep(300)
        except Exception as e:
            print(f"Error running {script_path}: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error


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
        # Table Tennis
        "Mozzart/mozzartStoniTenis.py",
        "Admiral/admiralStoniTenis.py",
        "Maxbet/maxbetStoniTenis.py",
        "Meridian/meridianStoniTenis.py",
        "Soccerbet/soccerbetStoniTenis.py",
        # Football
        "Mozzart/mozzartFudbal.py",
        "Admiral/admiralFudbal.py",
        "Maxbet/maxbetFudbal.py",
        "Meridian/meridianFudbal.py",
        "Soccerbet/soccerbetFudbal.py",
        # Basketball
        "Mozzart/mozzartKosarka.py",
        "Admiral/admiralKosarka.py",
        "Maxbet/maxbetKosarka.py",
        "Meridian/meridianKosarka.py",
        "Soccerbet/soccerbetKosarka.py",
        # Hockey
        "Mozzart/mozzartHokej.py",
        "Admiral/admiralHokej.py",
        "Maxbet/maxbetHokej.py",
        "Meridian/meridianHokej.py",
        "Soccerbet/soccerbetHokej.py",
    ]

    tasks = []
    print("\nStarting scrapers:")
    for script in scripts:
        script_path = base_path / script
        if script_path.exists():
            print(f"✅ Starting {script}")
            task = asyncio.create_task(run_script(script_path))
            tasks.append(task)
        else:
            print(f"❌ Missing {script}")

    if not tasks:
        print("\nNo scripts found to execute!")
        return

    await asyncio.gather(*tasks)

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
