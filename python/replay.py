"""Independent reference observer; input timestamps are UTC Unix milliseconds."""
import argparse
import csv
import json
import math
from collections import deque
from pathlib import Path

FIELDS = 'type,outcome,id,time_ms,entry_ms,direction,bid,ask,reference,upper,lower,entry_spread_pips,mae_pips,mfe_pips,net_pips,elapsed_s,model'.split(',')
DEFAULT = dict(length=20, sigma=3., target=3., stop=10., watch_ms=900000,
               max_gap_ms=60000, additional_cost=0., max_spread=0., model='BID_ASK')

class Observer:
    def __init__(self, config=None, seed=()):
        self.c = DEFAULT | (config or {})
        c = self.c
        if (c['length'] < 2 or c['length']-1 <= c['sigma']**2 or
            any(not math.isfinite(c[k]) or c[k] <= 0 for k in ('sigma','target','stop','watch_ms','max_gap_ms')) or
            c['watch_ms'] > 900000 or any(not math.isfinite(c[k]) or c[k] < 0 for k in ('additional_cost','max_spread')) or
            c['model'] not in ('BID_REFERENCE','BID_ASK')):
            raise ValueError('Invalid configuration')
        if any(not math.isfinite(x) or x <= 0 for x in seed):
            raise ValueError('Invalid seed')
        self.closes = deque(seed, maxlen=c['length']-1)
        self.drop_first = len(self.closes) != c['length']-1
        self.bucket = self.previous_time = -1
        self.previous_bid = 0.
        self.upper = self.lower = None
        self.used = False
        self.serial = 0
        self.active = []

    def event(self, kind, code, t, bid, ask, p=None, net=None):
        p = p or dict(id=0, time=-1, d=0, ref=None, up=self.upper, low=self.lower,
                      spread=None, mae=None, mfe=None)
        return dict(zip(FIELDS, (kind, code, p['id'], t, p['time'], p['d'], bid, ask,
                    p['ref'], p['up'], p['low'], p['spread'], p['mae'], p['mfe'], net,
                    None if p['time'] < 0 else max(0,t-p['time'])/1000, self.c['model'])))

    def tick(self, t, bid, ask):
        c, events = self.c, []
        if t < 0 or not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0 or ask < bid:
            return [self.event('QUALITY','INVALID_QUOTE',t,bid,ask)]
        if self.previous_time >= 0 and t < self.previous_time:
            return [self.event('QUALITY','OUT_OF_ORDER',t,bid,ask)]
        gap = self.previous_time >= 0 and t-self.previous_time > c['max_gap_ms']
        survivors = []
        for p in self.active:
            exit_price = bid if c['model'] == 'BID_REFERENCE' or p['d'] == 1 else ask
            move = (exit_price-p['ref'])*p['d']/0.01
            if gap:
                code = 'GAP'
            else:
                p['mae'] = max(p['mae'], -move, 0)
                p['mfe'] = max(p['mfe'], move, 0)
                code = ('TIME' if t-p['time'] >= c['watch_ms'] else
                        'TP' if move >= c['target']-1e-6 else
                        'SL' if move <= -c['stop']+1e-6 else '')
            if code:
                events.append(self.event('RESULT', code, t,bid,ask,p,
                              None if gap else move-c['additional_cost']))
            else:
                survivors.append(p)
        self.active = survivors
        bucket = t//300000*300000
        if bucket != self.bucket:
            if self.bucket >= 0:
                if not self.drop_first:
                    self.closes.append(self.previous_bid)
                self.drop_first = False
            self.bucket, self.used = bucket, False
            self.upper = self.lower = None
            if len(self.closes) == c['length']-1:
                mean = sum(self.closes)/len(self.closes)
                variance = sum((x-mean)**2/len(self.closes) for x in self.closes)
                if variance > 0:
                    radius = c['sigma']*math.sqrt(c['length']*variance/(c['length']-1-c['sigma']**2))
                    self.upper, self.lower = mean+radius, mean-radius
        d = (-1 if self.upper is not None and bid >= self.upper else
             1 if self.lower is not None and bid <= self.lower else 0)
        if d and not self.used:
            self.used = True
            self.serial += 1
            spread = (ask-bid)/0.01
            p = dict(id=self.serial, time=t,d=d,ref=ask if c['model']=='BID_ASK' and d==1 else bid,
                     up=self.upper,low=self.lower,spread=spread,mae=0.,mfe=0.)
            if c['max_spread'] > 0 and spread > c['max_spread']+1e-6:
                events.append(self.event('SKIP','SPREAD',t,bid,ask,p))
            else:
                p['mae'] = spread if c['model']=='BID_ASK' else 0.
                events.append(self.event('TOUCH','',t,bid,ask,p))
                if p['mae'] >= c['stop']-1e-6:
                    events.append(self.event('RESULT','SL',t,bid,ask,p,-p['mae']-c['additional_cost']))
                else:
                    self.active.append(p)
        self.previous_time, self.previous_bid = t,bid
        return events

    def end(self):
        result = [self.event('RESULT','END',self.previous_time,self.previous_bid,None,p) for p in self.active]
        self.active.clear()
        return result


def read_seed(path, first_time):
    if not path:
        return []
    with open(path, newline='', encoding='utf-8') as source:
        rows = list(csv.DictReader(source))
    times = [int(r['bar_start_ms']) for r in rows]
    if times != sorted(set(times)) or any(t < 0 or t % 300000 or t+300000 > first_time//300000*300000 for t in times):
        raise ValueError('Seed must be sorted, unique, completed five-minute bars preceding the first quote')
    return [float(r['close']) for r in rows]


def replay(ticks, config, seed_path, output):
    with open(ticks, newline='', encoding='utf-8') as src, open(output,'w',newline='',encoding='utf-8') as out:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        engine = None
        for r in reader:
            t = int(r['time_ms'])
            if engine is None:
                engine = Observer(config, read_seed(seed_path,t))
            writer.writerows(engine.tick(t,float(r['bid']),float(r['ask'])))
        if engine:
            writer.writerows(engine.end())

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ticks',required=True)
    p.add_argument('--config',default='config/observer.json')
    p.add_argument('--seed')
    p.add_argument('--events',required=True)
    a = p.parse_args()
    replay(a.ticks,json.loads(Path(a.config).read_text()),a.seed,a.events)
