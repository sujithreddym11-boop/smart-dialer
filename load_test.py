from dialer import Dialer
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile,time
for n in (100,1000,10000):
    with tempfile.TemporaryDirectory() as tmp:
        path=str(Path(tmp)/'load.db'); Dialer(path).setup(n,n*2); t=time.perf_counter()
        with ThreadPoolExecutor(8) as pool: batches=list(pool.map(lambda _:Dialer(path).allocate()[0],range(8)))
        elapsed=time.perf_counter()-t; count=sum(map(len,batches)); assert count==n
        print(f'{n} agents: {count} reservations in {elapsed:.3f}s ({count/elapsed:.0f}/s), 8 workers')
