"""Download the pinned official API, verify its hash, compile standalone strategy."""
import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SHA='bad5923eb37b07aaf3f8f257eec1cfec57d645c1f61ea68ec2b7e179d3736ac2'
JAR=ROOT/'vendor/JForex-API-2.13.99.jar'
URL='https://www.dukascopy.com/client/jforexlib/publicrepo/com/dukascopy/api/JForex-API/2.13.99/JForex-API-2.13.99.jar'
JAR.parent.mkdir(exist_ok=True)
if not JAR.exists():
    with urllib.request.urlopen(URL,timeout=60) as response:
        data=response.read()
    if hashlib.sha256(data).hexdigest()!=SHA: raise SystemExit('Official API checksum mismatch')
    JAR.write_bytes(data)
if hashlib.sha256(JAR.read_bytes()).hexdigest()!=SHA: raise SystemExit('API checksum mismatch')
build=ROOT/'build/adapter'; build.mkdir(parents=True,exist_ok=True)
compiler=['javac'] if shutil.which('javac') else ['java','--module','jdk.compiler/com.sun.tools.javac.Main']
subprocess.run(compiler+['--release','8','-classpath',str(JAR),'-d',str(build),str(ROOT/'jforex/WemofObserver.java')],check=True)
print('Standalone JForex observer compiled against verified API 2.13.99')
