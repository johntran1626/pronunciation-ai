"""Vowel-spike follow-up: where inside the vowel should we measure? Re-measures formants from saved run-2 times (no model). Run: python spikes/a_window_test.py. Throwaway."""
import csv, io, numpy as np, parselmouth, pyarrow.parquet as pq, soundfile as sf
from collections import defaultdict
rows=list(csv.DictReader(open("data/cache/spike_a_vowels_heard.csv")))
audio={r["id"]:r["audio"]["bytes"] for r in pq.read_table("data/zeroth/data/test-00000-of-00001.parquet",columns=["id","audio"]).to_pylist()}
VAR={
 "A middle 40% of blip->next (current)": lambda s,e:(s+0.3*(e-s), s+0.7*(e-s)),
 "B at the blip (first 20 ms)":          lambda s,e:(s, s+0.02),
 "C centred on blip (-30..+30 ms)":      lambda s,e:(s-0.03, s+0.03),
 "D 40 ms BEFORE the blip":              lambda s,e:(s-0.05, s-0.01),
 "E first 40% of blip->next":            lambda s,e:(s, s+0.4*(e-s)),
}
by_utt=defaultdict(list)
for r in rows: by_utt[r["utt"]].append(r)
meas={k:[] for k in VAR}
for utt,rs in by_utt.items():
    a,_=sf.read(io.BytesIO(audio[utt]),dtype="float32")
    fm=parselmouth.Sound(a,16000).to_formant_burg(time_step=0.005,max_number_of_formants=5,maximum_formant=float(rs[0]["ceiling"]))
    for r in rs:
        s,e=float(r["start"]),float(r["end"])
        for k,f in VAR.items():
            lo,hi=f(s,e); ts=np.linspace(max(lo,0),hi,5)
            f1=np.nanmedian([fm.get_value_at_time(1,t) for t in ts]); f2=np.nanmedian([fm.get_value_at_time(2,t) for t in ts])
            if not(np.isnan(f1) or np.isnan(f2)): meas[k].append(dict(speaker=r["speaker"],vowel=r["vowel"],f1=f1,f2=f2))
def loso(rows,a,b):
    by=defaultdict(list)
    for r in rows: by[r["speaker"]].append(r)
    for g in by.values():
        for k in("f1","f2"):
            v=np.array([r[k] for r in g])
            for r in g: r["z"+k]=(r[k]-v.mean())/v.std()
    rows=[r for r in rows if abs(r["zf1"])<=3 and abs(r["zf2"])<=3]
    accs=[]
    for h in by:
        tr=[r for r in rows if r["speaker"]!=h]; te=[r for r in rows if r["speaker"]==h]
        c={v:np.mean([[r["zf1"],r["zf2"]] for r in tr if r["vowel"]==v],axis=0) for v in(a,b)}
        acc=[]
        for v in(a,b):
            t=np.array([[r["zf1"],r["zf2"]] for r in te if r["vowel"]==v]); o=b if v==a else a
            acc.append(np.mean(np.linalg.norm(t-c[v],axis=1)<np.linalg.norm(t-c[o],axis=1)))
        accs.append(np.mean(acc))
    return np.mean(accs),min(accs),max(accs)
print(f"{'where we measure':<40}{'ㅏ/ㅣ':>18}{'ㅓ/ㅗ':>18}{'ㅗ/ㅜ':>18}{'ㅐ/ㅔ':>18}")
for k,rs in meas.items():
    out=""
    for a,b in [("ㅏ","ㅣ"),("ㅓ","ㅗ"),("ㅗ","ㅜ"),("ㅐ","ㅔ")]:
        m,lo,hi=loso([dict(r) for r in rs],a,b); out+=f"{m:5.1%} ({lo:.0%}-{hi:.0%})".rjust(18)
    print(f"{k:<40}{out}")
