"""Compare reference replay with a JForex session; unknown outcomes stay unknown."""
import argparse
import csv
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from replay import FIELDS

def compare(left, right, tolerance=1e-7):
    with open(left,newline='',encoding='utf-8') as a, open(right,newline='',encoding='utf-8') as b:
        rows=[list(csv.DictReader(f)) for f in (a,b)]
    if len(rows[0])!=len(rows[1]): raise ValueError(f'Event count differs: {len(rows[0])} vs {len(rows[1])}')
    strings={'type','outcome','model'}
    integers={'id','time_ms','entry_ms','direction'}
    for index,(a,b) in enumerate(zip(*rows),2):
        for key in FIELDS:
            x,y=a[key],b[key]
            if x=='' or y=='' or key in strings:
                same=x==y
            elif key in integers:
                same=int(x)==int(y)
            else:
                same=math.isclose(float(x),float(y),rel_tol=0,abs_tol=tolerance)
            if not same: raise ValueError(f'Row {index}, {key}: {x!r} vs {y!r}')
    return len(rows[0])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('observed'); p.add_argument('replayed')
    a=p.parse_args()
    print(f'MATCH: {compare(a.observed,a.replayed)} events')
