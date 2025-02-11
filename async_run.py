import asyncio
import sys
from pathlib import Path
from datetime import datetime
import time
import csv

def save_arbitrage(text):
    """Save arbitrage opportunity to file if it's unique and meets profit criteria"""
    match_name = text.split('!')[0].split('for ')[-1]
    profit_lines = [line for line in text.split('\n') if 'Profit:' in line]
    if not profit_lines:
        return
        
    profit = float(profit_lines[0].split('$')[1].strip())
    if profit < 1.4 or profit > 4.0:
        return
    
    try:
        with open('arbitrageopps.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        arb_count = content.count('Arbitrage #')
        if match_name in content:
            print(f"Arbitrage for {match_name} already recorded")
            return
    except FileNotFoundError:
        content = ""
        arb_count = 0
    
    with open('arbitrageopps.txt', 'a', encoding='utf-8') as f:
        f.write('\n' + '='*50 + '\n')
        f.write(f"Arbitrage #{arb_count + 1}\n")
        f.write(f"Found at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(text + '\n')

async def run_script(script):
    try:
        process = await asyncio.create_subprocess_exec(
            'python', script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
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
        stderr=asyncio.subprocess.PIPE
    )
    
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
            save_arbitrage('\n'.join(current_arb))
            capturing = False
            current_arb = []
        elif capturing:
            current_arb.append(output)

def create_missing_csv_files():
    """Create CSV files if they don't exist"""
    csv_files = {
        'Tennis': ['admiral_tennis_matches.csv', 'maxbet_tennis_matches.csv', 'meridian_tennis_matches.csv', 
                  'mozzart_tennis_matches.csv', 'soccerbet_tennis_matches.csv'],
        'Football': ['admiral_football_matches.csv', 'maxbet_football_matches.csv', 'meridian_football_matches.csv',
                    'mozzart_football_matches.csv', 'soccerbet_football_matches.csv'],
        'Basketball': ['admiral_basketball_matches.csv', 'maxbet_basketball_matches.csv', 'meridian_basketball_matches.csv',
                      'mozzart_basketball_matches.csv', 'soccerbet_basketball_matches.csv'],
        'Hockey': ['admiral_hockey_matches.csv', 'maxbet_hockey_matches.csv', 'meridian_hockey_matches.csv',
                  'mozzart_hockey_matches.csv', 'soccerbet_hockey_matches.csv'],
        'Table Tennis': ['admiral_tabletennis_matches.csv', 'maxbet_tabletennis_matches.csv', 'meridian_tabletennis_matches.csv',
                        'mozzart_tabletennis_matches.csv', 'soccerbet_tabletennis_matches.csv']
    }
    
    for sport, files in csv_files.items():
        print(f"\nChecking {sport} CSV files:")
        for file in files:
            if not Path(file).exists():
                print(f"Creating {file}")
                with open(file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Match', 'Type', 'Odds 1', 'Odds 2', 'Odds 3'])
            else:
                print(f"✅ {file} exists")

async def main():
    start_time = time.time()
    
    create_missing_csv_files()
    
    # Run all scripts in parallel
    scripts = [
        # Tennis
        'mozzartTenis.py', 'admiralTenis.py', 'maxbetTenis.py', 
        'meridianTenis.py', 'soccerbetTenis.py',
        
        # Table Tennis
        'mozzartStoniTenis.py', 'admiralStoniTenis.py', 'maxbetStoniTenis.py',
        'meridianStoniTenis.py', 'soccerbetStoniTenis.py',
        
        # Football
        'mozzartFudbal.py', 'admiralFudbal.py', 'maxbetFudbal.py',
        'meridianFudbal.py', 'soccerbetFudbal.py',
        
        # Basketball
        'mozzartKosarka.py', 'admiralKosarka.py', 'maxbetKosarka.py',
        'meridianKosarka.py', 'soccerbetKosarka.py',
        
        # Hockey
        'mozzartHokej.py', 'admiralHokej.py', 'maxbetHokej.py',
        'meridianHokej.py', 'soccerbetHokej.py'
    ]
    
    # Filter only existing scripts
    existing_scripts = [s for s in scripts if Path(s).exists()]
    
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
    
    # Run combine_games.py after all other scripts
    if successful > 0:
        print("\nRunning combine_games.py to analyze results...")
        await run_script('combine_games.py')
    
    # Calculate and print total runtime
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    print(f"\nTotal runtime: {minutes} minutes and {seconds} seconds")

async def run_full_scrape():
    """Run the full scraping process"""
    print(f"\nStarting scheduled scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await main()
    print(f"Completed scheduled scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    # Run immediately on start
    asyncio.run(run_full_scrape())