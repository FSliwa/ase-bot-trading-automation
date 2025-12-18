#!/usr/bin/env python3
"""
Start trading bots for selected users.
Runs each bot as a background process with log streaming.
"""

import asyncio
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).parent))

# Selected user IDs to run bots for
SELECTED_USERS = [
    "4177e228-e38e-4a64-b34a-2005a959fcf2",
    "e4f7f9e4-1664-4419-aaa2-592f12dc2f2a",
    "b812b608-3bdc-4afe-9dbd-9857e65a3bfe",
    "1aa87e38-f100-49d1-85dc-292bc58e25f1",
    "43e88b0b-d34f-4795-8efa-5507f40426e8",
]

# Bot script to run
BOT_SCRIPT = Path(__file__).parent / "run_single_user.py"

def kill_existing_bots():
    """Kill any existing bot processes."""
    print("🛑 Killing existing bot processes...")
    os.system("pkill -f 'run_single_user.py' 2>/dev/null")
    os.system("pkill -f 'run_multi_user_bot.py' 2>/dev/null")
    os.system("pkill -f 'auto_trader.py' 2>/dev/null")
    import time
    time.sleep(2)
    print("✅ Old processes cleared")

def start_bots():
    """Start bots for all selected users."""
    processes = []
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    print(f"\n🚀 Starting bots for {len(SELECTED_USERS)} users...")
    print("=" * 60)
    
    for user_id in SELECTED_USERS:
        short_id = user_id[:8]
        log_file = log_dir / f"bot_{short_id}.log"
        
        print(f"   👤 User: {user_id}")
        print(f"      📄 Log: {log_file}")
        
        # Start bot process
        cmd = [
            sys.executable,
            str(BOT_SCRIPT),
            user_id  # Just pass user_id as positional argument
        ]
        
        with open(log_file, "w") as log:
            log.write(f"=== Bot started at {datetime.now()} ===\n")
            log.write(f"User ID: {user_id}\n\n")
        
        # Start in background with log file
        with open(log_file, "a") as log:
            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).parent)
            )
            processes.append((user_id, proc, log_file))
            print(f"      ✅ Started (PID: {proc.pid})")
    
    print("\n" + "=" * 60)
    print(f"✅ All {len(processes)} bots started!")
    print("\n📋 Process IDs:")
    for user_id, proc, _ in processes:
        print(f"   {user_id[:8]}... → PID {proc.pid}")
    
    # Save PIDs to file for later management
    pid_file = Path(__file__).parent / ".bot_pids"
    with open(pid_file, "w") as f:
        for user_id, proc, log_file in processes:
            f.write(f"{proc.pid}:{user_id}:{log_file}\n")
    
    return processes

def stream_logs(processes):
    """Stream logs from all bot processes."""
    import select
    import time
    
    print("\n" + "=" * 60)
    print("📺 STREAMING LOGS FROM ALL BOTS (Ctrl+C to stop)")
    print("=" * 60 + "\n")
    
    # Open all log files for reading
    log_files = {}
    for user_id, proc, log_path in processes:
        try:
            f = open(log_path, "r")
            f.seek(0, 2)  # Go to end of file
            log_files[user_id[:8]] = f
        except Exception as e:
            print(f"⚠️ Could not open log for {user_id[:8]}: {e}")
    
    try:
        while True:
            for short_id, f in log_files.items():
                try:
                    line = f.readline()
                    if line:
                        # Color code by user
                        print(f"[{short_id}] {line.rstrip()}")
                except Exception:
                    pass
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n🛑 Log streaming stopped.")
        for f in log_files.values():
            f.close()

def main():
    print("=" * 60)
    print("  🤖 ASE BOT - Multi-User Launcher")
    print("  📅 " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    # Kill existing processes
    kill_existing_bots()
    
    # Start new bots
    processes = start_bots()
    
    # Ask if user wants to stream logs
    print("\n❓ Stream logs in terminal? (y/n): ", end="")
    try:
        choice = input().strip().lower()
        if choice == 'y':
            stream_logs(processes)
    except:
        pass
    
    print("\n✅ Bots are running in background.")
    print(f"📄 Check logs in: {Path(__file__).parent / 'logs'}")
    print("🛑 To stop: pkill -f 'run_single_user.py'")

if __name__ == "__main__":
    main()
