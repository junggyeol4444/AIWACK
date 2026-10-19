import json, os, subprocess, sys, time
from pathlib import Path
p=Path(__file__).resolve().parent
root=p.parent.parent
groups=json.loads((p/'test_groups.json').read_text())
for i in range(2,len(groups)):
    cmd=[sys.executable,'-m','pytest','-q',*groups[i]]
    with (p/f'group_{i+1:02}.log').open('wb') as log:
        try:
            returncode=subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT,
                                     env=dict(os.environ,PYTHONPATH=str(root)),timeout=90).returncode
        except subprocess.TimeoutExpired:
            returncode=124
            log.write(b'\nTIMEOUT after 90s\n')
    (p/f'group_{i+1:02}.exit').write_text(str(returncode))
    with (p/'group_status.txt').open('a') as status:
        status.write(f'{i+1}: exit {returncode}\n')
        status.flush()
