# skill: syshealth
# description: Show system health dashboard — CPU, RAM, disk, load, top processes
# tags: system, monitoring, admin
# version: 1.1
# created: 2026-04-28

def run(**kwargs) -> str:
    import psutil, time
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    load = psutil.getloadavg()
    net = psutil.net_io_counters()

    out = f"""System Health
{'─'*44}
CPU   {cpu:5.1f}%  Load: {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}
RAM   {mem.percent:5.1f}%  {mem.used//1024**3:.1f}GB / {mem.total//1024**3:.1f}GB
Disk  {disk.percent:5.1f}%  {disk.used//1024**3:.1f}GB used  {disk.free//1024**3:.1f}GB free
Net   ↑{net.bytes_sent//1024**2}MB  ↓{net.bytes_recv//1024**2}MB
{'─'*44}
Top Processes:"""
    procs = sorted(
        psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
        key=lambda p: p.info.get('cpu_percent') or 0, reverse=True
    )[:6]
    for p in procs:
        out += f"\n  {p.info['pid']:>6}  {p.info['name'][:20]:<20}  CPU {p.info['cpu_percent']:5.1f}%  MEM {p.info.get('memory_percent', 0):4.1f}%"
    return out
