import asyncio
import sys
from pathlib import Path
from datetime import datetime
import os
import signal
import time

def get_all_scripts():
    """Get list of all script paths"""
    base_path = Path(__file__).parent
    scripts = [
        # Admiral scripts
       # base_path / "Admiral/admiralTenis.py",
        base_path / "Admiral/admiralStoniTenis.py",
        base_path / "Admiral/admiralFudbal.py",
        base_path / "Admiral/admiralKosarka.py",
        base_path / "Admiral/admiralHokej.py",
        # Soccerbet scripts
       # base_path / "Soccerbet/soccerbetTenis.py",
        base_path / "Soccerbet/soccerbetStoniTenis.py",
        base_path / "Soccerbet/soccerbetFudbal.py",
        base_path / "Soccerbet/soccerbetKosarka.py",
        base_path / "Soccerbet/soccerbetHokej.py",
        # Meridian scripts
        base_path / "Meridian/meridianStoniTenis.py",
        base_path / "Meridian/meridianFudbal.py",
        base_path / "Meridian/meridianKosarka.py",
        base_path / "Meridian/meridianHokej.py",
       # base_path / "Meridian/meridianTenis.py",
        # Maxbet scripts
        base_path / "Maxbet/maxbetStoniTenis.py",
        base_path / "Maxbet/maxbetFudbal.py",
        base_path / "Maxbet/maxbetKosarka.py",
        base_path / "Maxbet/maxbetHokej.py",
        #base_path / "Maxbet/maxbetTenis.py",
        # Superbet scripts
        base_path / "Superbet/superbetFudbal.py",
        base_path / "Superbet/superbetKosarka.py",
        base_path / "Superbet/superbetHokej.py",
        base_path / "Superbet/superbetStoniTenis.py",
       # base_path / "Superbet/superbetTenis.py",
        # Mozzart scripts
        base_path / "Mozzart/mozzartFudbal.py",
        base_path / "Mozzart/mozzartKosarka.py",
       # base_path / "Mozzart/mozzartTenis.py",
        base_path / "Mozzart/mozzartHokej.py",
        base_path / "Mozzart/mozzartStoniTenis.py",
        # Merkur scripts
       # base_path / "Merkur/merkurTenis.py",
        base_path / "Merkur/merkurFudbal.py",
        base_path / "Merkur/merkurKosarka.py",
        base_path / "Merkur/merkurHokej.py",
        #base_path / "Merkur/merkurStoniTenis.py",
    ]
    return [s for s in scripts if s.exists()]

async def run_script(script_path):
    """Run a single script"""
    start_time = time.time()
    try:
        print(f"Starting {script_path}")
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if stdout:
            print(stdout.decode())
        if stderr:
            print(f"[{script_path}] Error:")
            print(stderr.decode())
            
        if process.returncode != 0:
            print(f"Script {script_path} failed with return code {process.returncode}")
            
    except Exception as e:
        print(f"Error running script {script_path}: {str(e)}")
    finally:
        elapsed_time = time.time() - start_time
        print(f"Finished {script_path} in {elapsed_time:.2f} seconds")

async def run_all_scripts():
    """Run all scripts in parallel"""
    start_time = time.time()
    
    all_scripts = get_all_scripts()
    print(f"Found {len(all_scripts)} scripts to run")
    
    tasks = [asyncio.create_task(run_script(script)) for script in all_scripts]
    await asyncio.gather(*tasks)
    
    elapsed_time = time.time() - start_time
    print(f"\nTotal execution time: {elapsed_time:.2f} seconds")

async def run_full_scrape():
    """Run the full scraping process"""
    total_start_time = time.time()
    print(f"\nStarting scheduled scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await run_all_scripts()
    total_time = time.time() - total_start_time
    print(f"Completed scheduled scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total scraping time: {total_time:.2f} seconds\n")

def signal_handler(signum, frame):
    print("\nCleaning up and exiting...")
    sys.exit(0)

if __name__ == "__main__":
    # Add project root to path
    project_root = str(Path(__file__).parent.parent)
    if project_root not in sys.path:
        sys.path.append(project_root)
    
    signal.signal(signal.SIGINT, signal_handler)
    asyncio.run(run_full_scrape())