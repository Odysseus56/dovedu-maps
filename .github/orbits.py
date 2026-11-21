"""Writes the files of the release "orbits" into ./out/. Run by .github/workflows/orbits.yml; standard library only."""
import contextlib, datetime, ftplib, gzip, io, re, sys, urllib.error, urllib.request
from pathlib import Path

OUT = Path('out'); OUT.mkdir(exist_ok=True)
PREV = Path('prev')                   # the release's files before this run (orbits.yml downloads them)
ALERTS = Path('alerts.txt')           # the files no archive answered for; orbits.yml fails the run on them
ESA, WHU = 'gssc.esa.int', 'igs.gnsswhu.cn'
DAILY = {ESA: '/gnss/data/daily/{y}/{doy}/', WHU: '/pub/gps/data/daily/{y}/brdc/'}
HOURLY = {ESA: '/gnss/data/hourly/{y}/{doy}/{h}', WHU: '/pub/gps/data/hourly/{y}/{doy}/{h}'}
BKG = 'https://igs.bkg.bund.de/root_ftp/IGS/BRDC/{y}/{doy}/'
MIN_BYTES = 10_000
IONEX_FTP = ((ESA, '/gnss/products/ionex/{y}/{doy}/'), (WHU, '/pub/gps/products/ionex/{y}/{doy}/'))
PRED_OBS_H, PRED_KEEP = 6, 8      # the app asks for the file names these give: change them only together with the app
PRED_ALERT_H = 4                  # a source file is out 1-2 h after its hour: none of the last 4 hours' means hours of failures


def names(day):
    return [f'BRDC00IGS_R_{day}0000_01D_MN.rnx.gz', f'BRDC00WRD_R_{day}0000_01D_MN.rnx.gz', f'BRDC00WRD_S_{day}0000_01D_MN.rnx.gz']


def good(raw):
    try: return len(raw) >= MIN_BYTES and b'END OF HEADER' in gzip.decompress(raw)[:20000]
    except OSError: return False


def ours(name):
    """The release's copy of the file (downloaded into PREV), else None."""
    p = PREV / name
    return p.read_bytes() if p.is_file() else None


def missing(e):
    """An archive's answer that it has no such file (HTTP 404, FTP 5xx: not out yet), as against a failure to reach it."""
    return isinstance(e, ftplib.error_perm) or (isinstance(e, urllib.error.HTTPError) and e.code == 404)


def first(tries):
    """(the first (name, bytes) one of tries [(archive, fn)] gives, else None; None when some archive answered, else the list of
    their failures). fn returns None, or raises a 404 or 550, when the archive answers that it has no such file."""
    failed, reached = [], False
    for src, fn in tries:
        try: got = fn()
        except Exception as e:
            print(f'  {src}: {type(e).__name__} {str(e)[:80]}')
            if missing(e): reached = True
            else: failed.append(f'{src}: {type(e).__name__}')
            continue
        reached = True
        if got: print(f'  {src}: {got[0]}'); return got, None
        print(f'  {src}: not out yet')
    return None, (None if reached else failed)


@contextlib.contextmanager
def ftp(host):
    """A logged-in anonymous FTP session, closed after without a QUIT (to a server that stopped answering it waits 30 s more)."""
    f = ftplib.FTP(host, timeout=30)
    try: f.login(); yield f
    finally: f.close()


def ftp_get(host, path):
    """The file's bytes. A refusal or a transfer cut short (421 too many users, 425, EOFError on 2026-10-13) is tried once more;
    a 550 (not there) and a timeout (the archive is down, and each costs 30 s) are not."""
    for again in (False, True):
        buf = io.BytesIO()
        try:
            with ftp(host) as f: f.retrbinary(f'RETR {path}', buf.write)
            return buf.getvalue()
        except (ftplib.error_perm, TimeoutError): raise
        except Exception as e:
            if again: raise
            print(f'  {host} {path.rsplit("/", 1)[-1]}: {type(e).__name__} {str(e)[:80]}, once more')


def daily(host, day):
    """The finished day's BRDC00IGS_R from host's archive."""
    n = names(day)[0]; raw = ftp_get(host, DAILY[host].format(y=day[:4], doy=day[4:]) + n)
    return (n, raw) if good(raw) else None


def bkg(day, wanted):
    """BKG's first file of wanted (names) it has. A failure to reach it ends the try at once: each costs 10 s."""
    for n in wanted:
        try:
            with urllib.request.urlopen(BKG.format(y=day[:4], doy=day[4:]) + n, timeout=10) as r: raw = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: continue
            raise
        if good(raw): return n, raw
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


def merge(host, day, now, per_hour=40):
    """One file of the day's records from the hourly files of the last 3 hours in host's archive (one per country, at most
    per_hour an hour), each record once. None when the archive has no file of those hours yet; an error when it stops
    answering halfway."""
    head = None; seen = set(); recs = []; files = 0
    with ftp(host) as f:
        for back in range(3):
            t = now - datetime.timedelta(hours=back)
            if t.strftime('%Y%j') != day: continue           # an hour of the other day
            folder = HOURLY[host].format(y=day[:4], doy=day[4:], h=f'{t:%H}')
            try: listing = [x.rsplit('/', 1)[-1] for x in f.nlst(folder)]
            except ftplib.error_perm: continue               # the hour's folder is not there yet
            countries = set(); pick = []
            for n in sorted(listing):
                if n.endswith('_01H_MN.rnx.gz') and n[6:9] not in countries and len(pick) < per_hour: countries.add(n[6:9]); pick.append(n)
            for n in pick:
                buf = io.BytesIO()
                try: f.retrbinary(f'RETR {folder}/{n}', buf.write)
                except ftplib.error_perm: continue           # gone since the listing
                try: h, rs = split(gzip.decompress(buf.getvalue()).decode('latin-1'))
                except Exception: continue                   # a station's broken file
                files += 1
                if head is None and any('IONOSPHERIC CORR' in l for l in h): head = h
                for r in rs:
                    key = r[0][:23]                                   # satellite and its epoch: one record each
                    if key not in seen: seen.add(key); recs.append(r)
    if head is None or not recs: return None
    head = [l for l in head if not l[60:].startswith(('MARKER', 'COMMENT'))]
    head.insert(1, f"{'merged by orbits.py (dovedu-maps) ' + now.strftime('%Y%m%d %H%M%S UTC'):60.60}COMMENT")
    recs.sort(key=lambda r: (r[0][:3], r[0][4:23]))
    text = '\n'.join(head + [l for r in recs for l in r]) + '\n'
    print(f'  merged {len(recs)} records from {files} station files')
    return names(day)[2], gzip.compress(text.encode('latin-1'))


def station_iono(day, now, tries=12):
    """(file name, its IONOSPHERIC CORR lines) from an hourly file of the day that has the GPSA and GPSB ones (the last 3 hours
    for today, a finished day's last 3), in ESA's archive, else Wuhan's; else None."""
    hours = [now - datetime.timedelta(hours=b) for b in range(3)] if day == now.strftime('%Y%j') else \
            [datetime.datetime.strptime(day, '%Y%j') + datetime.timedelta(hours=h) for h in (23, 22, 21)]
    for host in (ESA, WHU):
        try:
            with ftp(host) as f:
                tried = 0
                for t in hours:
                    if t.strftime('%Y%j') != day: continue
                    folder = HOURLY[host].format(y=day[:4], doy=day[4:], h=f'{t:%H}')
                    try: listing = sorted(x.rsplit('/', 1)[-1] for x in f.nlst(folder))
                    except ftplib.error_perm: continue
                    for n in listing:
                        if not n.endswith('_01H_MN.rnx.gz') or tried >= tries: continue
                        tried += 1; buf = io.BytesIO()
                        try: f.retrbinary(f'RETR {folder}/{n}', buf.write)
                        except ftplib.error_perm: continue
                        try: h, _ = split(gzip.decompress(buf.getvalue()).decode('latin-1'))
                        except Exception: continue
                        lines = [l for l in h if l[60:].startswith('IONOSPHERIC CORR')]
                        if any(l[:4] == 'GPSA' for l in lines) and any(l[:4] == 'GPSB' for l in lines): return n, lines
        except Exception as e: print(f'  ionosphere lines, {host}: {type(e).__name__} {str(e)[:80]}')
    return None


def with_iono(raw, day, now):
    """The file as it is when its header has a GPSA line, else with station_iono's lines before END OF HEADER."""
    text = gzip.decompress(raw).decode('latin-1'); lines = text.split('\n')
    end = next((i for i, l in enumerate(lines) if 'END OF HEADER' in l), None)
    if end is None or any(l[:4] == 'GPSA' and 'IONOSPHERIC CORR' in l for l in lines[:end]): return raw
    got = station_iono(day, now)
    if got is None: print('  no GPS ionosphere lines, and none found in a station file'); return raw
    n, add = got; note = f"{'ionosphere lines from ' + n[:9] + ' (orbits.py, dovedu-maps)':60.60}COMMENT"
    print(f'  no GPS ionosphere lines: {len(add)} taken from {n}')
    return gzip.compress('\n'.join(lines[:end] + [note] + add + lines[end:]).encode('latin-1'))


def broadcast(day, back, now):
    """(name, bytes) of the day's file (back: days before today), else None; and the alert when no archive answered."""
    mine = None
    for n in names(day):
        raw = ours(n)
        if raw and good(raw): mine = (n, raw); break
    merges = [('ESA merge', lambda: merge(ESA, day, now)), ('Wuhan merge', lambda: merge(WHU, day, now))]
    if back == 0:
        tries = [merges[0], ('BKG', lambda: bkg(day, names(day)[2:])), merges[1]]
    elif mine and not mine[0].startswith('BRDC00WRD_S'):
        tries = []                                            # the day's final file: it never changes
    else:
        tries = [('ESA', lambda: daily(ESA, day)), ('BKG', lambda: bkg(day, names(day))), ('Wuhan', lambda: daily(WHU, day))]
        if back == 1 and now.hour < 2: tries += merges        # yesterday's last hours are among the last 3
    got, failed = first(tries) if tries else (None, None)
    alert = None
    if got is None:
        got = mine; print(f'  ours: {mine[0]}' if mine else '  nothing')
        if failed: alert = f'{day}: no archive answered ({", ".join(failed)}); ' + (f'our copy {mine[0]} kept' if mine else 'none in our copy either')
    if got:
        try: got = (got[0], with_iono(got[1], day, now))
        except Exception as e: print(f'  ionosphere lines: {type(e).__name__} {str(e)[:80]}')
    return got, alert


def good_ionex(raw):
    try: return raw is not None and len(raw) >= 50_000 and b'START OF TEC MAP' in gzip.decompress(raw)
    except OSError: return False


def ionex(now):
    """([(name, bytes)], alerts): each file from the release's copy (it never changes once out), else ESA's archive, else
    Wuhan's."""
    out, alerts = [], []
    for back, kinds in ((0, ('P0D', 'P1D')), (-1, ('P1D',))):
        day = (now - datetime.timedelta(days=back)).strftime('%Y%j')
        for k in kinds:
            name = f'COD0OPS{k}_{day}0000_01D_01H_GIM.INX.gz'; raw = ours(name)
            if good_ionex(raw): print(f'  ours: {name}'); out.append((name, raw)); continue
            def get(host, path):
                raw = ftp_get(host, path); return (name, raw) if good_ionex(raw) else None
            got, failed = first([(host, lambda h=host, p=folder.format(y=day[:4], doy=day[4:]) + name: get(h, p)) for host, folder in IONEX_FTP])
            if got: out.append(got)
            elif failed: alerts.append(f'{name}: no archive answered ({", ".join(failed)})')
    return out, alerts


def pred_name(issue):
    """The file name for an issue hour."""
    return f'WUM0MGXNRT_{issue - datetime.timedelta(hours=PRED_OBS_H):%Y%j%H%M}_{PRED_OBS_H + 24}H_15M_ORB.SP3.gz'


def good_sp3(raw):
    try: t = gzip.decompress(raw); return len(raw) >= 50_000 and t[:1] == b'#' and b'\n* ' in t and t.rstrip().endswith(b'EOF')
    except OSError: return False


def cut(text):
    """SP3 text -> (issue: its first epoch flagged P in column 80, the text cut to the epochs from PRED_OBS_H before it on whole
    quarter hours, the header's first epoch, count and step rewritten). None without such an epoch."""
    lines = text.splitlines(); first = next(i for i, l in enumerate(lines) if l.startswith('* '))
    head, blocks = list(lines[:first]), []
    for l in lines[first:]:
        if l.startswith('* '): blocks.append([l])
        elif l.startswith('EOF'): break
        elif blocks: blocks[-1].append(l)
    def when(b):
        p = b[0][2:].split(); return datetime.datetime(int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4]), int(float(p[5])))
    issue = next((when(b) for b in blocks if any(l.startswith('P') and l[79:80] == 'P' for l in b[1:])), None)
    if issue is None: return None
    keep = [b for b in blocks if when(b) >= issue - datetime.timedelta(hours=PRED_OBS_H) and (when(b) - issue).total_seconds() % 900 == 0]
    t0 = when(keep[0]); g = (t0 - datetime.datetime(1980, 1, 6)).total_seconds(); mjd = t0 - datetime.datetime(1858, 11, 17)
    head[0] = head[0][:3] + f'{t0.year:4d} {t0.month:2d} {t0.day:2d} {t0.hour:2d} {t0.minute:2d} {t0.second:11.8f} {len(keep):7d}' + head[0][39:]
    head[1] = f'## {int(g // 604800):4d} {g % 604800:15.8f} {900.0:14.8f} {mjd.days:5d} {mjd.seconds / 86400:15.13f}'
    head.insert(max(i for i, l in enumerate(head) if l.startswith('/*')) + 1, f'/* cut by orbits.py (dovedu-maps): {PRED_OBS_H} h observed, 24 h predicted, 15 min')
    return issue, '\n'.join(head + [l for b in keep for l in b] + ['EOF']) + '\n'


def predicted(now):
    """([(name, bytes)] of the last PRED_KEEP issue hours that are out, alert or None): each from the release's copy, else cut
    from the source file in Wuhan's archive (in the GPS week folder of its first epoch, or the next)."""
    out = []; fresh = reached = False
    for h in range(1, PRED_KEEP + 1):
        issue = now.replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=h); name = pred_name(issue)
        raw = ours(name)
        if raw is None or not good_sp3(raw):
            start = (issue - datetime.timedelta(days=1)).replace(tzinfo=None); src = f'WUM0MGXNRT_{start:%Y%j%H%M}_02D_05M_ORB.SP3.gz'
            week = (start - datetime.datetime(1980, 1, 6)).days // 7; raw = None
            for w in (week, week + 1):
                try: got = ftp_get(WHU, f'/pub/gnss/products/mgex/{w}/{src}')
                except Exception as e:
                    print(f'  {WHU} {src}: {type(e).__name__} {str(e)[:80]}')
                    reached |= missing(e) and h <= PRED_ALERT_H; continue
                reached |= h <= PRED_ALERT_H
                try: c = cut(gzip.decompress(got).decode('latin-1'))
                except Exception as e: print(f'  {src}: {type(e).__name__} {str(e)[:80]}'); continue
                if c is not None and pred_name(c[0]) == name: raw = gzip.compress(c[1].encode('latin-1')); break
        if raw is not None and good_sp3(raw): out.append((name, raw)); fresh |= h <= PRED_ALERT_H
        else: print(f'  {name}: not out yet, or nowhere')
    return out, (None if fresh or reached else f'predicted orbits: none of the last {PRED_ALERT_H} issue hours, and Wuhan did not answer')


now = datetime.datetime.now(datetime.timezone.utc); kept = []; alerts = []
for back in range(3):
    day = (now - datetime.timedelta(days=back)).strftime('%Y%j'); print(day)
    got, alert = broadcast(day, back, now)
    if alert: alerts.append(alert)
    if got: (OUT / got[0]).write_bytes(got[1]); kept.append(got[0]); print(f'  wrote {got[0]} ({len(got[1])} B)')
print('ionosphere maps')
try:
    maps, a = ionex(now); alerts += a
    for name, raw in maps: (OUT / name).write_bytes(raw); kept.append(name); print(f'  wrote {name} ({len(raw)} B)')
except Exception as e: print(f'  {type(e).__name__} {str(e)[:120]}')
print('predicted orbits')
try:
    cuts, a = predicted(now); alerts += [a] if a else []
    for name, raw in cuts: (OUT / name).write_bytes(raw); kept.append(name); print(f'  wrote {name} ({len(raw)} B)')
except Exception as e: print(f'  {type(e).__name__} {str(e)[:120]}')
print('kept:', kept)
if alerts: ALERTS.write_text('\n'.join(alerts) + '\n'); print('alerts:', *alerts, sep='\n  ')
sys.exit(0 if any(n.startswith('BRDC') for n in kept) else 1)    # no BRDC file at all: the workflow leaves the release as it is
