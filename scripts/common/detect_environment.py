#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, platform, shutil, socket, subprocess, sys
from pathlib import Path


def run(*cmd: str) -> str:
    try: return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
    except Exception: return ""

def primary_ipv4(interface: str | None = None) -> str:
    if interface:
        out=run("ip","-4","-o","addr","show","dev",interface,"scope","global")
        for line in out.splitlines():
            parts=line.split()
            if len(parts)>3: return parts[3].split('/')[0]
    out=run("ip","-4","route","get","1.1.1.1")
    p=out.split()
    if "src" in p: return p[p.index("src")+1]
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("1.1.1.1",80)); ip=s.getsockname()[0]; s.close(); return ip
    except OSError: return ""

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--interface'); ap.add_argument('--json', action='store_true'); args=ap.parse_args()
    repo=Path(os.getenv('AI_CAMERA_REPO_ROOT', Path(__file__).resolve().parents[2])).resolve()
    info={
      'hostname': socket.gethostname(), 'user': os.getenv('USER',''), 'home': str(Path.home()),
      'repo_root': str(repo), 'primary_ipv4': primary_ipv4(args.interface or os.getenv('AI_CAMERA_INTERFACE')),
      'platform': platform.platform(), 'machine': platform.machine(), 'python': sys.version.split()[0],
      'commands': {x: bool(shutil.which(x)) for x in ['ip','gst-launch-1.0','v4l2-ctl','ffmpeg','sqlite3','systemctl','rsync','ssh']},
      'video_devices': sorted(str(p) for p in Path('/dev').glob('video*')),
      'nvidia_smi': run('nvidia-smi','--query-gpu=name,driver_version,memory.total','--format=csv,noheader'),
      'jetpack': run('dpkg-query','--show','nvidia-jetpack'),
    }
    if args.json: print(json.dumps(info, indent=2))
    else:
      for k,v in info.items(): print(f'{k}: {v}')
    return 0
if __name__=='__main__': raise SystemExit(main())
