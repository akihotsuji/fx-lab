"""Build a self-contained JForex strategy from the tested core and adapter."""
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1]
def render():
 core=(ROOT/'src/main/java/lab/wemof/ObserverEngine.java').read_text()
 core=core[core.index('/** Deterministic'):].replace('public final class ObserverEngine {','public static final class ObserverEngine {',1)
 adapter=(ROOT/'src/adapter/WemofObserver.java.in').read_text()
 return adapter.replace('    // @EMBED_ENGINE@','\n'.join('    '+line if line else '' for line in core.splitlines()))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
 output=ROOT/'jforex/WemofObserver.java';content=render()
 if args.check:
  if not output.exists() or output.read_text()!=content:raise SystemExit('Generated strategy is stale. Run tools/bundle_strategy.py')
 else:output.write_text(content)
 print('JForex bundle verified' if args.check else str(output))
