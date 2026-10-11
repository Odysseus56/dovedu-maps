"""The last days' broadcast orbit files for the Taxi Antispoof app, written into ./out/ under the names the app asks for
(solver/ephemeris.brdc_urls in the app repository). Run hourly by .github/workflows/orbits.yml; standard library only.

For each of the last three UTC days, the first source that answers:
  1. IGS/BKG's daily merged file (BRDC00IGS_R, else BRDC00WRD_R, else BRDC00WRD_S): the one the app used to fetch itself;
  2. for a finished day, Wuhan University's IGS archive copy of BRDC00IGS_R (anonymous FTP);
  3. for today, our own merge of the stations' hourly navigation files in Wuhan's archive (the last 6 hours, every station):
     one RINEX 3 header (the first station's, with its ionosphere lines) and every record once. It is written as
     BRDC00WRD_S_<day>, the name of BKG's own file of the day so far.
BKG answers from few places some days (2026-10-08 and -11: neither the founder's networks in Spain nor GitHub's runners).
"""
import datetime, ftplib, gzip, io, re, sys, urllib.request
from pathlib import Path

OUT = Path('out'); OUT.mkdir(exist_ok=True)
WHU = 'igs.gnsswhu.cn'
MIN_BYTES = 10_000


def names(day):
    return [f'BRDC00IGS_R_{day}0000_01D_MN.rnx.gz', f'BRDC00WRD_R_{day}0000_01D_MN.rnx.gz', f'BRDC00WRD_S_{day}0000_01D_MN.rnx.gz']


def good(raw):
    try: return len(raw) >= MIN_BYTES and b'END OF HEADER' in gzip.decompress(raw)[:20000]
    except OSError: return False


def bkg(day):
    for n in names(day):
        try:
            with urllib.request.urlopen(f'https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{day[:4]}/{day[4:]}/{n}', timeout=10) as r: raw = r.read()
            if good(raw): return n, raw
        except Exception as e: print(f'  bkg {n}: {type(e).__name__} {str(e)[:80]}')
    return None


def ftp():
    f = ftplib.FTP(WHU, timeout=30); f.login(); return f


def whu_daily(day):
    n = names(day)[0]; buf = io.BytesIO()
    try:
        f = ftp(); f.retrbinary(f'RETR /pub/gps/data/daily/{day[:4]}/brdc/{n}', buf.write); f.close()
        if good(buf.getvalue()): return n, buf.getvalue()
    except Exception as e: print(f'  whu daily {n}: {type(e).__name__} {str(e)[:80]}')
    return None


def split(text):
    """(header lines, [records]): a record is its first line (a satellite id in column 1) and the continuation lines."""
    lines = text.splitlines(); end = next(i for i, l in enumerate(lines) if 'END OF HEADER' in l)
    head, recs, cur = lines[:end + 1], [], None
    for l in lines[end + 1:]:
        if re.match(r'^[GRECJIS]\d\d ', l):
            if cur: recs.append(cur)
            cur = [l]
        elif cur is not None and l.strip(): cur.append(l)
    if cur: recs.append(cur)
    return head, recs


def whu_merge(day, now, per_hour=40):
    """Today's records from the stations' hourly navigation files of the last 3 hours (one station per country, at most
    per_hour an hour: spread over the world, so every satellite is in view of some), each record once."""
    f = ftp(); head = None; seen = set(); recs = []; files = 0
    for back in range(3):
        t = now - datetime.timedelta(hours=back)
        if t.strftime('%Y%j') != day: break
        folder = f'/pub/gps/data/hourly/{day[:4]}/{day[4:]}/{t:%H}'
        try: listing = [x.rsplit('/', 1)[-1] for x in f.nlst(folder)]
        except Exception: continue
        countries = set(); pick = []
        for n in sorted(listing):
            if n.endswith('_01H_MN.rnx.gz') and n[6:9] not in countries and len(pick) < per_hour: countries.add(n[6:9]); pick.append(n)
        for n in pick:
            buf = io.BytesIO()
            try: f.retrbinary(f'RETR {folder}/{n}', buf.write); text = gzip.decompress(buf.getvalue()).decode('latin-1')
            except Exception: continue
            try: h, rs = split(text)
            except StopIteration: continue
            files += 1
            if head is None and any('IONOSPHERIC CORR' in l for l in h): head = h
            for r in rs:
                key = r[0][:23]                                   # satellite and its epoch: one record each
                if key not in seen: seen.add(key); recs.append(r)
    try: f.quit()
    except Exception: f.close()
    if head is None or not recs: return None
    head = [l for l in head if not l[60:].startswith(('MARKER', 'COMMENT'))]
    head.insert(1, f"{'merged by orbits.py (taxi-antispoof-maps) ' + now.strftime('%Y%m%d %H%M%S UTC'):60.60}COMMENT")
    recs.sort(key=lambda r: (r[0][:3], r[0][4:23]))
    text = '\n'.join(head + [l for r in recs for l in r]) + '\n'
    print(f'  merged {len(recs)} records from {files} station files')
    return names(day)[2], gzip.compress(text.encode('latin-1'))


now = datetime.datetime.now(datetime.timezone.utc); kept = []
for back in range(3):
    day = (now - datetime.timedelta(days=back)).strftime('%Y%j'); print(day)
    got = bkg(day) or (whu_daily(day) if back > 0 else None) or (whu_merge(day, now) if back == 0 else None)
    if got: (OUT / got[0]).write_bytes(got[1]); kept.append(got[0]); print(f'  wrote {got[0]} ({len(got[1])} B)')
    else: print('  nothing')
print('kept:', kept)
sys.exit(0 if kept else 1)
