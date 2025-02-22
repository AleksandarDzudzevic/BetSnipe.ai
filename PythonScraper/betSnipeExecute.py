import subprocess
import time
import os
from database_utils import get_db_connection

def clear_all_matches():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM AllMatches')
        conn.commit()
        print("Successfully cleared AllMatches table")
    except Exception as e:
        print(f"Error clearing AllMatches table: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def run_scripts():
    # Get the directory where the current script is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    scripts = [
        'async_run.py',
        'separate_into_csv.py',
        'combine_csv.py'
    ]
    
    for script in scripts:
        try:
            script_path = os.path.join(current_dir, script)
            subprocess.run(['python', script_path], check=True)
            print(f"Successfully executed {script}")
        except subprocess.CalledProcessError as e:
            print(f"Error executing {script}: {e}")

def main():
    while True:
        print("\nStarting new cycle...")
        
        # Clear the database
        print("Clearing allmatches table...")
        clear_all_matches()
        
        # Run all scripts
        print("Running scripts...")
        run_scripts()
        
        print("Cycle completed. Waiting 30 seconds...")
        time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript terminated by user")
