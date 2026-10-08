import csv
import math
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from replay import Observer, DEFAULT, FIELDS, read_seed

SEED = [150+(i-9)*0.01 for i in range(19)]
T = 6000000

def compiler():
    return ['javac'] if shutil.which('javac') else ['java','--module','jdk.compiler/com.sun.tools.javac.Main']

class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = ROOT/'build/tests'
        cls.build.mkdir(parents=True,exist_ok=True)
        subprocess.run(compiler()+['--release','8','-d',str(cls.build),
            str(ROOT/'src/main/java/lab/wemof/ObserverEngine.java'),
            str(ROOT/'tests/java/lab/wemof/Replay.java')],check=True)

    def parity(self, ticks, config=None, seed=SEED):
        c = DEFAULT | (config or {})
        engine = Observer(c, seed)
        expected = []
        for row in ticks:
            expected.extend(engine.tick(*row))
        expected.extend(engine.end())
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with (d/'ticks.csv').open('w',newline='') as f:
                w=csv.writer(f); w.writerow(['time_ms','bid','ask']); w.writerows(ticks)
            with (d/'seed.csv').open('w',newline='') as f:
                w=csv.writer(f); w.writerow(['bar_start_ms','close'])
                w.writerows((i*300000,x) for i,x in enumerate(seed))
            args=[str(d/'ticks.csv'),str(d/'seed.csv'),str(d/'events.csv')]
            args += [str(c[k]) for k in ('length','sigma','target','stop','watch_ms','max_gap_ms','additional_cost','max_spread','model')]
            subprocess.run(['java','-cp',str(self.build),'lab.wemof.Replay']+args,check=True)
            with (d/'events.csv').open() as f:
                actual=list(csv.DictReader(f))
        self.assertEqual(len(actual),len(expected))
        for a,b in zip(actual,expected):
            for k in FIELDS:
                value = b[k]
                if value is None or isinstance(value,float) and not math.isfinite(value):
                    self.assertEqual(a[k],'',k)
                elif isinstance(value,str):
                    self.assertEqual(a[k],value,k)
                else:
                    self.assertAlmostEqual(float(a[k]),value,places=7,msg=k)
        return expected

    def test_buy_inside_same_five_minute_bar(self):
        events=self.parity([(T,149.70,149.71),(T+1000,149.741,149.751)])
        self.assertEqual([e['type'] for e in events],['TOUCH','RESULT'])
        self.assertEqual(events[-1]['outcome'],'TP')
        self.assertAlmostEqual(events[-1]['net_pips'],3.1)

    def test_sell_uses_ask_for_exit(self):
        events=self.parity([(T,150.30,150.31),(T+1000,150.25,150.27)])
        self.assertEqual(events[-1]['outcome'],'TP')
        self.assertAlmostEqual(events[-1]['net_pips'],3)

    def test_bid_reference_has_no_spread_charge(self):
        events=self.parity([(T,149.70,149.75),(T+1000,149.73,149.78)],{'model':'BID_REFERENCE'})
        self.assertEqual(events[-1]['outcome'],'TP')
        self.assertAlmostEqual(events[-1]['net_pips'],3)

    def test_spread_can_stop_immediately(self):
        events=self.parity([(T,149.70,149.82)])
        self.assertEqual([e['outcome'] for e in events],['','SL'])
        self.assertAlmostEqual(events[-1]['net_pips'],-12)

    def test_spread_cap_consumes_first_contact(self):
        events=self.parity([(T,149.70,149.74),(T+1000,149.70,149.71)],{'max_spread':2})
        self.assertEqual([(e['type'],e['outcome']) for e in events],[('SKIP','SPREAD')])

    def test_gap_cannot_be_counted_as_profit(self):
        events=self.parity([(T,149.70,149.71),(T+60001,149.80,149.81)])
        self.assertEqual(events[-1]['outcome'],'GAP')
        self.assertIsNone(events[-1]['net_pips'])

    def test_deadline_precedes_target(self):
        events=self.parity([(T,149.70,149.71),(T+1000,149.80,149.81)],{'watch_ms':1000})
        self.assertEqual(events[-1]['outcome'],'TIME')
        self.assertAlmostEqual(events[-1]['net_pips'],9)

    def test_same_timestamp_preserves_arrival_order(self):
        events=self.parity([(T,149.70,149.71),(T,149.74,149.75),(T,149.50,149.51)])
        self.assertEqual(events[-1]['outcome'],'TP')
        self.assertEqual(events[-1]['elapsed_s'],0)

    def test_invalid_does_not_advance_state(self):
        events=self.parity([(T,149.70,149.71),(T+100,149.0,148.0),(T-1,149.8,149.81),(T+200,149.74,149.75)])
        self.assertEqual([e['outcome'] for e in events],['','INVALID_QUOTE','OUT_OF_ORDER','TP'])

    def test_stop_records_observed_overshoot_and_cost(self):
        events=self.parity([(T,149.70,149.71),(T+1000,149.59,149.60)],{'additional_cost':0.3})
        self.assertEqual(events[-1]['outcome'],'SL')
        self.assertAlmostEqual(events[-1]['net_pips'],-12.3)

    def test_unresolved_end_is_unknown(self):
        events=self.parity([(T,149.70,149.71)])
        self.assertEqual(events[-1]['outcome'],'END')
        self.assertIsNone(events[-1]['net_pips'])

    def test_touch_boundary_matches_current_bb(self):
        e=Observer(seed=SEED); e.tick(T,150,150.01)
        for x in (e.upper,e.lower):
            prices=SEED+[x]
            mean=sum(prices)/20
            sd=math.sqrt(sum((v-mean)**2 for v in prices)/20)
            self.assertAlmostEqual(abs(x-mean),3*sd,places=10)

    def test_future_seed_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'seed.csv'; p.write_text('bar_start_ms,close\n6000000,150\n')
            with self.assertRaises(ValueError): read_seed(p,T)

    def test_random_stream_both_models_and_no_seed(self):
        rng=random.Random(634)
        ticks=[]; t=T; bid=150.
        for i in range(12000):
            t+=rng.choice([0,100,1000,10000,60001])
            bid+=rng.gauss(0,0.025)
            ticks.append((t,bid,bid+rng.choice([0.001,0.01,0.025,0.12])))
        for model in ('BID_REFERENCE','BID_ASK'):
            self.parity(ticks,{'model':model})
        self.parity(ticks,seed=[])

    def test_partial_first_bar_is_not_used_as_completed_close(self):
        e=Observer(seed=[])
        ticks=[(T+100000,150,150.01)]
        for i in range(1,21): ticks.append((T+i*300000,150+i*.01,150+i*.01+.01))
        self.parity(ticks,seed=[])
        for row in ticks[:-1]: e.tick(*row)
        self.assertIsNone(e.upper)
        e.tick(*ticks[-1]); self.assertIsNotNone(e.upper)

if __name__=='__main__': unittest.main()
