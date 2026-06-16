#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, pwd, grp
from pathlib import Path

def abs_path(root: Path, value: str) -> str:
    p=Path(os.path.expandvars(os.path.expanduser(value))); return str((root/p).resolve() if not p.is_absolute() else p.resolve())

def render(template: Path, values: dict[str,str]) -> str:
    text=template.read_text()
    for k,v in values.items(): text=text.replace(f'@{k}@',v)
    leftovers=[x for x in text.split() if x.startswith('@') and x.endswith('@')]
    if leftovers: raise SystemExit(f'Unresolved template values: {leftovers}')
    return text

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--role',choices=['node1','node2'],required=True); ap.add_argument('--output-dir',default='/etc/systemd/system'); ap.add_argument('--dry-run',action='store_true'); args=ap.parse_args()
    root=Path(os.getenv('AI_CAMERA_REPO_ROOT') or Path(__file__).resolve().parents[2]).resolve()
    user=os.getenv('AI_CAMERA_SERVICE_USER') or os.getenv('SUDO_USER') or os.getenv('USER')
    if not user: raise SystemExit('ERROR: cannot determine service user; set AI_CAMERA_SERVICE_USER')
    try: group=grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name
    except KeyError: raise SystemExit(f'ERROR: unknown service user {user}')
    env_file=root/'deploy/ai-camera.env'
    if not env_file.exists(): raise SystemExit(f'ERROR: missing {env_file}; copy deploy/ai-camera.env.example and edit it')
    values={
      'SERVICE_USER':user,'SERVICE_GROUP':group,'REPO_ROOT':str(root),'ENV_FILE':str(env_file),
      'PYTHON':str(root/os.getenv('AI_CAMERA_VENV_DIR','.venv')/'bin/python'),'UVICORN':str(root/os.getenv('AI_CAMERA_VENV_DIR','.venv')/'bin/uvicorn'),
      'POLICY':abs_path(root,os.getenv('AI_CAMERA_POLICY','configs/runtime/security_policy.yaml')),
      'DB_PATH':abs_path(root,os.getenv('AI_CAMERA_DB','data/events/ai_camera.db')),
      'MIGRATIONS':abs_path(root,os.getenv('AI_CAMERA_MIGRATIONS','migrations')),
      'DATA_DIR':str(root/'data'),'RESULTS_DIR':str(root/'results'),'RUNTIME_CONFIG_DIR':str(root/'configs/runtime'),
      'NODE1_IP':os.environ['AI_CAMERA_NODE1_IP'],'NODE2_IP':os.environ['AI_CAMERA_NODE2_IP'],
      'NODE1_API_PORT':os.getenv('AI_CAMERA_NODE1_API_PORT','8080'),'NODE1_METRICS_PORT':os.getenv('AI_CAMERA_NODE1_METRICS_PORT','9101'),
      'NODE2_API_PORT':os.getenv('AI_CAMERA_NODE2_API_PORT','8082'),'RTP_PORT':os.getenv('AI_CAMERA_NODE1_RTP_PORT','5000'),
      'PROFILE':os.getenv('AI_CAMERA_PROFILE','mjpeg_720p30'),'TRANSPORT':os.getenv('AI_CAMERA_TRANSPORT','rtp'),'CAMERA_ID':os.getenv('AI_CAMERA_CAMERA_ID','c922_node2_gate'),
      'DEVICE':os.getenv('AI_CAMERA_DEVICE','/dev/video0'),'EVENT_LOG':abs_path(root,os.getenv('AI_CAMERA_EVENT_LOG','results/node1/events.jsonl')),
      'LATENCY_THRESHOLD_MS':os.getenv('AI_CAMERA_LATENCY_THRESHOLD_MS','5.0'),'LATENCY_WINDOW_SAMPLES':os.getenv('AI_CAMERA_LATENCY_WINDOW_SAMPLES','120'),
    }
    units=['node1-ai-camera-api','node1-ai-camera-receiver'] if args.role=='node1' else ['node2-camera-control-agent']
    out=Path(args.output_dir)
    if not args.dry_run: out.mkdir(parents=True,exist_ok=True)
    for name in units:
      content=render(root/'systemd/templates'/f'{name}.service.in',values)
      target=out/f'{name}.service'
      if args.dry_run:
            print(f'--- {target} ---\n{content}')
      else: target.write_text(content); print(f'[OK] installed {target}')
    return 0
if __name__=='__main__': raise SystemExit(main())
