import time
import subprocess
import os
import signal
import sys

def main():
    while True:
        try:
            res = subprocess.run(["/home/shahab/api/.venv/bin/pip", "show", "kaleido"], capture_output=True, text=True)
            if "Version: 0.2.1" in res.stdout:
                break
        except Exception:
            pass
        time.sleep(10)
        
    print("Kaleido downgraded! Restarting telegram bot...")
    
    # Kill the existing telegram_bot
    try:
        pids = subprocess.check_output(["pgrep", "-f", "telegram_bot.py"]).decode().split()
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    except subprocess.CalledProcessError:
        pass
        
    time.sleep(2)
    
    # Run the new bot
    subprocess.Popen([sys.executable, "telegram_bot.py"], cwd="/home/shahab/api")
    print("Bot restarted successfully.")

if __name__ == "__main__":
    main()
