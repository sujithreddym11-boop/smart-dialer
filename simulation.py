import tempfile,random
from pathlib import Path
from dialer import Dialer,MockProvider

def run():
    for name,rate,talk in [('A',.2,120),('B',.5,90),('C',.7,180),('D',.5,90)]:
        for mode in ('progressive','predictive'):
            with tempfile.TemporaryDirectory() as tmp:
                d=Dialer(str(Path(tmp)/'sim.db')); d.setup(30,2000); p=MockProvider('slow' if name=='D' else 'fast',8 if name=='D' else 3,.12 if name=='D' else .02,name=='D'); rng=random.Random(42); busy=online=proposed=approved=0; estimate=rate
                for t in range(300):
                    if name=='D' and t==150:
                        for a in range(12): d.offline(a,t)
                    p.outage=name=='D' and 100<=t<130
                    actual=.2 if name=='D' and t>=150 else rate
                    d.tick(t); ids,q,n=d.allocate(estimate,mode,t,p.outage); proposed+=q; approved+=n
                    for cid in ids: d.start(cid,p,rng,actual,talk if t<150 or name!='D' else 180,t)
                    s=d.stats(); busy+=s['busy']; online+=s['online']
                    if s['initiated']: estimate=max(.05,s['connected']/s['initiated'])
                print(name,mode,'utilization',round(100*busy/max(1,online),1),'%', 'initiated',s['initiated'],'connected',s['connected'],'proposed',proposed,'approved',approved)
if __name__=='__main__': run()
