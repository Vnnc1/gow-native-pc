"""Check a private gameplay pause smoke's guest-frame and audio evidence (not an FPS benchmark)."""
import argparse, json, re
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--resumed',action='store_true');a=p.parse_args()
log=(a.run/'session/runtime.log').read_text(encoding='utf-8');meta=json.loads((a.run/'session/session.json').read_text())
assert meta['state']=='completed' and meta['exit_code']==0
rows=[json.loads(x) for x in (a.run/'session/metrics.jsonl').read_text().splitlines()]
paused=[x for x in rows if x.get('tag')=='gow-perf' and x['values'].get('guest_flip_hz')==0 and x['values'].get('host_hz',0)>30]
assert len(paused)>=2,'No sustained pause with responsive host'
result={'paused_windows':len(paused),'normal_exit':True}
if a.resumed:
 marker=re.search(r'\[(\d+) ms\] \[menu:test\] resumed',log);assert marker,'No resume marker'
 at=int(marker[1]);players=[tuple(map(int,m)) for m in re.findall(r'\[(\d+) ms\] \[gow-player\].*? frame=(\d+)',log)]
 before=[x for x in players if x[0]<at][-1];after=[x for x in players if x[0]>at]
 assert after and after[0][0]-before[0]>=8000
 assert 0<after[0][1]-before[1]<=90,'Guest caught up across the pause'
 assert after[-1][1]-after[0][1]>=120,'No sustained guest progress after resume'
 audio=[tuple(map(int,m)) for m in re.findall(r'\[(\d+) ms\] \[audio-stats\] requested=\d+ missing=(\d+) dropped=(\d+)',log)]
 stable=[x for x in audio if x[0]>at+5000];assert len(stable)>=2 and all(m==0 and d==0 for _,m,d in stable)
 result.update(resume_ms=at,trace_gap_ms=after[0][0]-before[0],guest_frame_delta_across_gap=after[0][1]-before[1],post_resume_guest_frames=after[-1][1]-after[0][1],clean_audio_windows=len(stable))
(a.run/'pause-validation.json').write_text(json.dumps(result,indent=2));print('PASS:',json.dumps(result))
