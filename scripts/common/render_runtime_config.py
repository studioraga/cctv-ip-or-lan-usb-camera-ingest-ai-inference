#!/usr/bin/env python3
from __future__ import annotations
import argparse, ipaddress, os, socket, subprocess
from pathlib import Path
from urllib.parse import urlparse
import yaml

def primary_ipv4(interface: str='') -> str:
    cmd=['ip','-4','-o','addr','show']
    if interface: cmd += ['dev',interface]
    cmd += ['scope','global']
    try:
        out=subprocess.check_output(cmd,text=True,stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            ip=line.split()[3].split('/')[0]
            if not ipaddress.ip_address(ip).is_loopback: return ip
    except Exception: pass
    try:
        out=subprocess.check_output(['ip','-4','route','get','1.1.1.1'],text=True).split()
        return out[out.index('src')+1]
    except Exception: return ''

def require_ip(name: str, value: str) -> str:
    try: return str(ipaddress.ip_address(value))
    except ValueError as exc: raise SystemExit(f'ERROR: {name} must be a valid IP address, got {value!r}') from exc

def csv(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name,default).split(',') if x.strip()]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--role',choices=['node1','node2'],required=True); ap.add_argument('--repo-root'); args=ap.parse_args()
    root=Path(args.repo_root or os.getenv('AI_CAMERA_REPO_ROOT') or Path(__file__).resolve().parents[2]).resolve()
    local=primary_ipv4(os.getenv('AI_CAMERA_INTERFACE',''))
    n1=os.getenv('AI_CAMERA_NODE1_IP','').strip()
    n2=os.getenv('AI_CAMERA_NODE2_IP','').strip()
    if args.role=='node1' and not n1: n1=local
    if args.role=='node2' and not n2: n2=local
    if not n1: raise SystemExit('ERROR: set AI_CAMERA_NODE1_IP on Node2, or provide it in deploy/ai-camera.env')
    if not n2: raise SystemExit('ERROR: set AI_CAMERA_NODE2_IP on Node1, or provide it in deploy/ai-camera.env')
    n1=require_ip('AI_CAMERA_NODE1_IP',n1); n2=require_ip('AI_CAMERA_NODE2_IP',n2)
    rtp=int(os.getenv('AI_CAMERA_NODE1_RTP_PORT','5000')); n2port=int(os.getenv('AI_CAMERA_NODE2_API_PORT','8082'))
    camera=os.getenv('AI_CAMERA_CAMERA_ID','c922_node2_gate'); device=os.getenv('AI_CAMERA_DEVICE','/dev/video0')
    profiles=csv('AI_CAMERA_ALLOWED_PROFILES','mjpeg_480p30,mjpeg_720p30,mjpeg_720p60')
    devices=csv('AI_CAMERA_ALLOWED_DEVICES',device)
    runtime=root/'configs/runtime'; runtime.mkdir(parents=True,exist_ok=True)
    policy={
      'version':2,'name':'generated_local_lan_camera_policy',
      'cameras':[{'camera_id':camera,'source_ip':n2,'node2_url':f'http://{n2}:{n2port}',
                  'allowed_node1_ips':[n1],'allowed_ports':[rtp],'allowed_profiles':profiles,'allowed_devices':devices}],
      'media':{'clip_root':os.getenv('AI_CAMERA_CLIP_ROOT','data/clips'),'keyframe_root':os.getenv('AI_CAMERA_KEYFRAME_ROOT','data/keyframes')},
      'node2_control':{'trusted_client_ips':[n1,'127.0.0.1','::1']},
      'network_rules':[{'id':'allow_node2_camera_to_node1','source_ip':n2,'destination_ip':n1,'protocol':'udp','destination_port':rtp,'action':'allow'},
                       {'id':'deny_untrusted_camera_sources','source_ip':'*','destination_ip':n1,'protocol':'udp','destination_port':rtp,'action':'deny'}],
      'observability':{'require_metrics':True,'require_jsonl_event_log':True,'require_tegrastats_on_node2':True}}
    nodes={'node1':{'role':'receiver_ai_orchestrator','ip':n1,'udp_port':rtp,'api_port':int(os.getenv('AI_CAMERA_NODE1_API_PORT','8080')),'metrics_port':int(os.getenv('AI_CAMERA_NODE1_METRICS_PORT','9101'))},
           'node2':{'role':'camera_streamer','ip':n2,'api_port':n2port,'camera_device':device,'default_mode':os.getenv('AI_CAMERA_PROFILE','mjpeg_720p30'),'supported_modes':profiles},
           'network':{'transport':'UDP/RTP','rtp_caps':'application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26','low_latency':True}}
    (runtime/'security_policy.yaml').write_text(yaml.safe_dump(policy,sort_keys=False))
    (runtime/'nodes.yaml').write_text(yaml.safe_dump(nodes,sort_keys=False))
    print(f'[OK] generated {runtime / "security_policy.yaml"}')
    print(f'[OK] generated {runtime / "nodes.yaml"}')
    print(f'NODE1_IP={n1} NODE2_IP={n2}')
    return 0
if __name__=='__main__': raise SystemExit(main())
