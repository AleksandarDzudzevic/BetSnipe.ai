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

def clear_csv_files():
    try:
        # Get the parent directory (BetSnipe.ai)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        matches_csv_dir = os.path.join(parent_dir, 'matches_csv')
        
        print(f"Attempting to clear CSV files from: {matches_csv_dir}")
        
        # Check if directory exists
        if os.path.exists(matches_csv_dir):
            files = os.listdir(matches_csv_dir)
            print(f"Found {len(files)} files in directory")
            
            # Iterate through all files in the directory
            for file in files:
                if file.endswith('.csv'):
                    file_path = os.path.join(matches_csv_dir, file)
                    print(f"Attempting to delete: {file_path}")
                    try:
                        # Force close any open file handles (Windows specific)
                        if os.name == 'nt':  # Windows systems
                            os.system(f'taskkill /F /IM "python.exe" /FI "WINDOWTITLE eq {file}"')
                        
                        os.remove(file_path)
                        print(f"Successfully deleted: {file}")
                    except PermissionError:
                        print(f"Permission denied when trying to delete: {file}")
                        print(f"File exists: {os.path.exists(file_path)}")
                        print(f"File is writable: {os.access(file_path, os.W_OK)}")
                    except Exception as e:
                        print(f"Error deleting {file}: {e}")
            print("CSV file clearing process completed")
        else:
            print(f"Directory not found: {matches_csv_dir}")
    except Exception as e:
        print(f"Error in clear_csv_files: {e}")

def main():
    while True:
        print("\nStarting new cycle...")
        
        # Clear CSV files first
        print("Clearing CSV files...")
        clear_csv_files()
        
        # Clear the database
        print("Clearing allmatches table...")
        clear_all_matches()
        
        # Run all scripts
        print("Running scripts...")
        run_scripts()  # combine_csv.py will now handle storage and Telegram
        
        print("Cycle completed. Waiting 2 seconds...")
        time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript terminated by user")
