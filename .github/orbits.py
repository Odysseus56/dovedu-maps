"""The last days' broadcast orbit files for the Dovedu app, written into ./out/ under the names the app asks for
(solver/ephemeris.brdc_urls in the app repository). Run hourly by .github/workflows/orbits.yml; standard library only.

For each of the last three UTC days, the first source that answers:
  1. IGS/BKG's daily merged file (BRDC00IGS_R, else BRDC00WRD_R, else BRDC00WRD_S): the one the app used to fetch itself;
  2. for a finished day, Wuhan University's IGS archive copy of BRDC00IGS_R (anonymous FTP);
  3. for today, and for yesterday until its daily file is out (the first hours after midnight UTC), our own merge of the
     stations' hourly navigation files in Wuhan's archive (those of the last 3 hours that belong to the day):
     one RINEX 3 header (the first station's, with its ionosphere lines) and every record once. It is written as
     BRDC00WRD_S_<day>, the name of BKG's own file of the day so far.
BKG answers from few places some days (2026-10-08 and -11: neither the founder's networks in Spain nor GitHub's runners).
BKG's merged file comes without the GPS ionosphere lines (IONOSPHERIC CORR GPSA / GPSB) about half the time (October 2026):
such a file gets the lines of a station's hourly navigation file of the same day in Wuhan's archive (every receiver decodes the
same GPS broadcast).

Also CODE's (Bern) forecast ionosphere maps (IONEX) for today and tomorrow, under their own names (solver/ephemeris.iono_names
in the app repository): today's out that morning (COD0OPSP0D_, about 07:15 UTC) and out the morning before (COD0OPSP1D_), and
tomorrow's out this morning (COD0OPSP1D_). From ESA's archive, else Wuhan's (anonymous FTP, byte for byte as CODE wrote them),
else the copy already in our release, so a run that reaches neither keeps them.
"""
import datetime, ftplib, gzip, io, os, re, sys, urllib.request
from pathlib import Path

OUT = Path('out'); OUT.mkdir(exist_ok=True)
WHU = 'igs.gnsswhu.cn'
MIN_BYTES = 10_000
IONEX_FTP = (('gssc.esa.int', '/gnss/products/ionex/{y}/{doy}/'), (WHU, '/pub/gps/products/ionex/{y}/{doy}/'))
RELEASE = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'Odysseus56/dovedu-maps')}/releases/download/orbits/"


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
    n = names(day)[0]
    for _ in range(2):                                    # a transfer cut short (EOFError on 2026-10-13) is tried once more
        buf = io.BytesIO()
        try:
            f = ftp(); f.retrbinary(f'RETR /pub/gps/data/daily/{day[:4]}/brdc/{n}', buf.write); f.close()
            if good(buf.getvalue()): return n, buf.getvalue()
        except Exception as e:
            print(f'  whu daily {n}: {type(e).__name__} {str(e)[:80]}')
            if 'Failed to open' in str(e): break             # not published (yet): asking again changes nothing
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
        if t.strftime('%Y%j') != day: continue           # an hour of the other day
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
    head.insert(1, f"{'merged by orbits.py (dovedu-maps) ' + now.strftime('%Y%m%d %H%M%S UTC'):60.60}COMMENT")
    recs.sort(key=lambda r: (r[0][:3], r[0][4:23]))
    text = '\n'.join(head + [l for r in recs for l in r]) + '\n'
    print(f'  merged {len(recs)} records from {files} station files')
    return names(day)[2], gzip.compress(text.encode('latin-1'))


def station_iono(day, now, tries=12):
    """(station file, its IONOSPHERIC CORR lines) from a station's hourly navigation file of the day in Wuhan's archive that has
    the GPS ones (the last 3 hours for today, a finished day's last 3), else None."""
    hours = [now - datetime.timedelta(hours=b) for b in range(3)] if day == now.strftime('%Y%j') else \
            [datetime.datetime.strptime(day, '%Y%j') + datetime.timedelta(hours=h) for h in (23, 22, 21)]
    f = ftp(); tried = 0
    try:
        for t in hours:
            if t.strftime('%Y%j') != day: continue
            folder = f'/pub/gps/data/hourly/{day[:4]}/{day[4:]}/{t:%H}'
            try: listing = sorted(x.rsplit('/', 1)[-1] for x in f.nlst(folder))
            except Exception: continue
            for n in listing:
                if not n.endswith('_01H_MN.rnx.gz') or tried >= tries: continue
                tried += 1; buf = io.BytesIO()
                try: f.retrbinary(f'RETR {folder}/{n}', buf.write); h, _ = split(gzip.decompress(buf.getvalue()).decode('latin-1'))
                except Exception: continue
                lines = [l for l in h if l[60:].startswith('IONOSPHERIC CORR')]
                if any(l[:4] == 'GPSA' for l in lines) and any(l[:4] == 'GPSB' for l in lines): return n, lines
    finally:
        try: f.quit()
        except Exception: f.close()
    return None


def with_iono(raw, day, now):
    """The file with the GPS ionosphere lines: as it is when it has them, else with a station's (station_iono) before END OF HEADER."""
    text = gzip.decompress(raw).decode('latin-1'); lines = text.split('\n')
    end = next((i for i, l in enumerate(lines) if 'END OF HEADER' in l), None)
    if end is None or any(l[:4] == 'GPSA' and 'IONOSPHERIC CORR' in l for l in lines[:end]): return raw
    got = station_iono(day, now)
    if got is None: print('  no GPS ionosphere lines, and none found in a station file'); return raw
    n, add = got; note = f"{'ionosphere lines from ' + n[:9] + ' (orbits.py, dovedu-maps)':60.60}COMMENT"
    print(f'  no GPS ionosphere lines: {len(add)} taken from {n}')
    return gzip.compress('\n'.join(lines[:end] + [note] + add + lines[end:]).encode('latin-1'))


def ftp_get(host, path):
    buf = io.BytesIO()
    try: f = ftplib.FTP(host, timeout=30); f.login(); f.retrbinary(f'RETR {path}', buf.write); f.quit(); return buf.getvalue()
    except Exception as e: print(f'  {host} {path.rsplit("/", 1)[-1]}: {type(e).__name__} {str(e)[:80]}'); return None


def good_ionex(raw):
    try: return raw is not None and len(raw) >= 50_000 and b'START OF TEC MAP' in gzip.decompress(raw)
    except OSError: return False


def ionex(now):
    """[(name, bytes)] of the forecast maps wanted (the module's docstring), each from the first source that has it."""
    out = []
    for back, kinds in ((0, ('P0D', 'P1D')), (-1, ('P1D',))):
        d = now - datetime.timedelta(days=back); day = d.strftime('%Y%j')
        for k in kinds:
            name = f'COD0OPS{k}_{day}0000_01D_01H_GIM.INX.gz'; raw = None
            for host, folder in IONEX_FTP:
                raw = ftp_get(host, folder.format(y=day[:4], doy=day[4:]) + name)
                if good_ionex(raw): break
            if not good_ionex(raw):
                try:
                    with urllib.request.urlopen(RELEASE + name, timeout=30) as r: raw = r.read()
                    if good_ionex(raw): print(f'  {name}: our release\'s copy kept')
                except Exception: raw = None
            if good_ionex(raw): out.append((name, raw))
            else: print(f'  {name}: not out yet, or nowhere')
    return out


now = datetime.datetime.now(datetime.timezone.utc); kept = []
for back in range(3):
    day = (now - datetime.timedelta(days=back)).strftime('%Y%j'); print(day)
    got = bkg(day) or (whu_daily(day) if back > 0 else None)
    if got:
        try: got = (got[0], with_iono(got[1], day, now))
        except Exception as e: print(f'  ionosphere lines: {type(e).__name__} {str(e)[:80]}')
    got = got or (whu_merge(day, now) if back < 2 else None)
    if got: (OUT / got[0]).write_bytes(got[1]); kept.append(got[0]); print(f'  wrote {got[0]} ({len(got[1])} B)')
    else: print('  nothing')
print('ionosphere maps')
try:
    for name, raw in ionex(now): (OUT / name).write_bytes(raw); kept.append(name); print(f'  wrote {name} ({len(raw)} B)')
except Exception as e: print(f'  {type(e).__name__} {str(e)[:120]}')
print('kept:', kept)
sys.exit(0 if any(n.startswith('BRDC') for n in kept) else 1)
