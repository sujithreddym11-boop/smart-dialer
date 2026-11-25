import unittest,tempfile,random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dialer import Dialer,MockProvider
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path=str(Path(self.tmp.name)/'test.db'); self.d=Dialer(self.path); self.d.setup(10,100); self.p=MockProvider('fast',3,0)
    def start(self):
        c=self.d.allocate()[0][0]; self.d.start(c,self.p,random.Random(1),1,10,0); return c
    def test_concurrency(self):
        with ThreadPoolExecutor(8) as pool: batches=list(pool.map(lambda _:Dialer(self.path).allocate()[0],range(20)))
        self.assertEqual(sum(map(len,batches)),10)
    def test_duplicates(self):
        c=self.start(); self.d.event(c,'ANSWERED'); self.d.event(c,'ANSWERED'); self.assertEqual(self.d.stats()['connected'],1)
    def test_order(self):
        c=self.start(); self.d.event(c,'COMPLETED'); self.d.event(c,'ANSWERED'); self.assertEqual(self.d.stats()['connected'],0)
    def test_restart(self):
        c=self.start(); d=Dialer(self.path); d.recover(4); self.assertEqual(d.stats()['connected'],1); d.recover(20); self.assertEqual(d.stats()['busy'],0)
    def test_outage(self): self.assertEqual(self.d.allocate(outage=True)[2],0)
    def test_offline(self):
        c=self.start(); self.d.offline(0); self.d.event(c,'ANSWERED'); self.assertEqual(self.d.stats()['connected'],0)
    def test_safety(self): self.assertEqual(self.d.allocate(.2,'predictive')[1:],(50,10))
    def test_duplicate_start(self):
        c=self.start(); self.assertFalse(self.d.start(c,self.p,random.Random(1),1,10,0)); self.assertEqual(self.d.stats()['initiated'],1)
if __name__=='__main__': unittest.main()
