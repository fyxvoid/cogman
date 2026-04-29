# skill: remind
# description: Set a reminder that fires after N minutes with desktop notification
# tags: productivity, reminder, utility
# version: 1.0
# created: 2026-04-28

def run(message: str = "", minutes: int = 5, **kwargs) -> str:
    if not message:
        return "Usage: skill_remind message=<text> minutes=<n>"
    import threading, subprocess, time, shutil

    def _fire():
        time.sleep(float(minutes) * 60)
        # Try desktop notification
        for cmd in [
            ["notify-send", f"cogman reminder", message],
            ["zenity", "--notification", "--text", message],
            ["osascript", "-e", f'display notification "{message}" with title "cogman"'],
        ]:
            if shutil.which(cmd[0]):
                subprocess.run(cmd, capture_output=True)
                break
        print(f"\n[REMINDER] {message}\n")

    t = threading.Thread(target=_fire, daemon=True)
    t.start()
    return f"Reminder set: '{message}' in {minutes} minute(s)"
