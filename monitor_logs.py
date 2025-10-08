#!/usr/bin/env python
"""
Real-time log viewer for Delta Strategy monitoring
Shows API calls every 30 seconds
"""
import time
import os
import sys
from datetime import datetime

def tail_log_file(file_path, lines=50):
    """Read the last N lines from a file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Get all lines and return the last N
            all_lines = f.readlines()
            return all_lines[-lines:] if len(all_lines) > lines else all_lines
    except FileNotFoundError:
        return [f"Log file not found: {file_path}\n"]
    except Exception as e:
        return [f"Error reading log file: {e}\n"]

def monitor_logs():
    """Monitor logs in real-time"""
    log_file = os.path.join(os.getcwd(), 'logs', 'deltastrategy.log')
    
    print("🔍 Delta Strategy API Monitoring Log Viewer")
    print("=" * 60)
    print(f"📁 Monitoring log file: {log_file}")
    print("🔄 Updates every 5 seconds. Press Ctrl+C to exit.")
    print("=" * 60)
    
    last_size = 0
    
    while True:
        try:
            # Check if file exists and get current size
            if os.path.exists(log_file):
                current_size = os.path.getsize(log_file)
                
                # If file has grown, show new content
                if current_size > last_size:
                    print(f"\n🆕 [{datetime.now().strftime('%H:%M:%S')}] New log entries:")
                    print("-" * 40)
                    
                    # Show recent logs
                    recent_logs = tail_log_file(log_file, 20)
                    
                    # Filter for API monitoring related logs
                    api_logs = [
                        line for line in recent_logs 
                        if any(keyword in line.lower() for keyword in [
                            'periodic_api_check', 'target check', 'pnl summary', 
                            'api check', 'connection test', '30 seconds'
                        ])
                    ]
                    
                    if api_logs:
                        for log_line in api_logs[-10:]:  # Show last 10 relevant logs
                            # Add color coding
                            if 'error' in log_line.lower():
                                print(f"❌ {log_line.strip()}")
                            elif 'target achieved' in log_line.lower():
                                print(f"🎯 {log_line.strip()}")
                            elif 'periodic api check' in log_line.lower():
                                print(f"🔄 {log_line.strip()}")
                            elif 'pnl summary' in log_line.lower():
                                print(f"📊 {log_line.strip()}")
                            else:
                                print(f"ℹ️  {log_line.strip()}")
                    else:
                        # Show general recent activity
                        print("📋 Recent activity:")
                        for log_line in recent_logs[-5:]:
                            print(f"   {log_line.strip()}")
                    
                    last_size = current_size
                
                else:
                    print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] Waiting for new logs... (File size: {current_size} bytes)")
            
            else:
                print(f"⚠️  [{datetime.now().strftime('%H:%M:%S')}] Log file not found: {log_file}")
                print("   Make sure Django server is running and logging is enabled.")
            
            # Wait 5 seconds before checking again
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("\n\n👋 Log monitoring stopped. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error monitoring logs: {e}")
            time.sleep(5)

def show_current_status():
    """Show current monitoring status"""
    print("📊 Current Monitoring Status")
    print("=" * 40)
    
    # Check if services are running (simple check)
    import subprocess
    
    try:
        # Check if Django is running
        result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
        if ':8000' in result.stdout:
            print("✅ Django server is running (port 8000)")
        else:
            print("❌ Django server not detected")
    except:
        print("❓ Could not check Django server status")
    
    # Check log file
    log_file = os.path.join(os.getcwd(), 'logs', 'deltastrategy.log')
    if os.path.exists(log_file):
        print(f"✅ Log file exists: {log_file}")
        file_size = os.path.getsize(log_file)
        print(f"📁 File size: {file_size} bytes")
        
        # Show last few lines
        recent_logs = tail_log_file(log_file, 5)
        print("\n📋 Last 5 log entries:")
        for i, line in enumerate(recent_logs, 1):
            print(f"   {i}. {line.strip()}")
    else:
        print(f"❌ Log file not found: {log_file}")
    
    print("\n" + "=" * 40)

if __name__ == '__main__':
    print("🚀 Delta Strategy Log Monitor")
    print()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--status':
        show_current_status()
    else:
        print("Options:")
        print("  python monitor_logs.py         - Real-time log monitoring")
        print("  python monitor_logs.py --status - Show current status")
        print()
        
        choice = input("Choose [m]onitor or [s]tatus (default: monitor): ").lower()
        
        if choice == 's' or choice == 'status':
            show_current_status()
        else:
            monitor_logs()