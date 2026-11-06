# 기상청 예보를 받아 VRChat 월드가 읽을 weather.json 하나로 정리한다.
# GitHub Actions 가 1시간마다 돌린다. 인증키는 저장소 Secret 에서 환경 변수로 들어온다.
#   KMA_KEY        : 기상청 API허브(apihub.kma.go.kr) 인증키. 관측(ASOS)과 예보
#   DATA_GO_KR_KEY : (선택) 공공데이터포털 일반 인증키. 있으면 예보를 이쪽에서 받는다
# 받지 못한 부분은 지난번 weather.json 의 값을 쓴다 (PREV_URL).
import datetime as dt
import json
import math
import os
import sys

import requests

KST = dt.timezone(dt.timedelta(hours=9))
APIHUB = "https://apihub.kma.go.kr/api/"
DATAGO = "https://apis.data.go.kr/1360000/"

# 이름, 격자 nx, ny, 중기 육상 구역, 중기 기온 지점, ASOS 지점
CITIES = [
    ("서울", 60, 127, "11B00000", "11B10101", 108),
    ("인천", 55, 124, "11B00000", "11B20201", 112),
    ("강릉", 92, 131, "11D20000", "11D20501", 105),
    ("대전", 67, 100, "11C20000", "11C20401", 133),
    ("대구", 89, 90, "11H10000", "11H10701", 143),
    ("광주", 58, 74, "11F20000", "11F20501", 156),
    ("부산", 98, 76, "11H20000", "11H20201", 159),
    ("제주", 52, 38, "11G00000", "11G00201", 184),
]
WEEK = "월화수목금토일"
SKY_TEXT = {1: "맑음", 3: "구름많음", 4: "흐림"}
PTY_TEXT = {1: "비", 2: "비/눈", 3: "눈", 4: "소나기", 5: "빗방울", 6: "빗방울눈날림", 7: "눈날림"}
PTY_ICON = {1: "rain", 2: "sleet", 3: "snow", 4: "shower", 5: "rain", 6: "sleet", 7: "snow"}

log = []


def note(s):
    log.append(s)
    print(s, file=sys.stderr)


def get(url, key_name, key, enc="utf-8"):
    try:
        r = requests.get(url + ("&" if "?" in url else "?") + key_name + "=" + key, timeout=25)
        r.encoding = enc
        if r.status_code != 200:
            note(f"{url.split('?')[0].rsplit('/', 1)[-1]}: HTTP {r.status_code}")
            return None
        return r.text
    except Exception as e:
        note(f"{url.split('?')[0].rsplit('/', 1)[-1]}: {e}")
        return None


def items(text):
    if not text:
        return None
    try:
        j = json.loads(text)
        res = j["response"]
        code = res["header"]["resultCode"]
        if code != "00":
            note("예보 응답 " + code + " " + res["header"].get("resultMsg", ""))
            return None
        it = res["body"]["items"]["item"]
        return it if isinstance(it, list) else [it]
    except Exception as e:
        note(f"예보 해석 실패: {e}")
        return None


class Source:
    def __init__(self):
        self.hub = os.environ.get("KMA_KEY", "").strip()
        self.dgo = os.environ.get("DATA_GO_KR_KEY", "").strip()

    def fcst(self, path):
        if self.dgo:
            return items(get(DATAGO + path, "serviceKey", self.dgo))
        if self.hub:
            return items(get(APIHUB + "typ02/openApi/" + path, "authKey", self.hub))
        return None


# ── 해가 떠 있는지 (밤에는 해 대신 달 아이콘) ───────────────
def is_day(t):
    doy = t.timetuple().tm_yday
    c = math.cos(2 * math.pi * (doy - 172) / 365.0)
    rise, set_ = 6.4 - 1.2 * c, 18.5 + 1.4 * c
    h = t.hour + t.minute / 60.0
    return rise <= h < set_


def icon(sky, pty, day):
    if pty and pty in PTY_ICON:
        return PTY_ICON[pty]
    if sky == 1:
        return "sun" if day else "moon"
    if sky == 3:
        return "partly" if day else "partly_night"
    return "cloud"


def text_icon(wf):
    wf = wf or ""
    if "소나기" in wf:
        return "shower"
    if "비/눈" in wf or "눈/비" in wf:
        return "sleet"
    if "비" in wf:
        return "rain"
    if "눈" in wf:
        return "snow"
    if "흐" in wf:
        return "cloud"
    if "구름" in wf:
        return "partly"
    return "sun"


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def day_label(d, today):
    n = (d - today).days
    return "오늘" if n == 0 else "내일" if n == 1 else WEEK[d.weekday()]


# ── 관측 (ASOS, 전 지점 최신 1시간) ─────────────────────────
def observations(src):
    if not src.hub:
        return {}, None
    t = get(APIHUB + "typ01/url/kma_sfctm2.php?tm=&stn=0&help=0", "authKey", src.hub, enc="euc-kr")
    if not t:
        return {}, None
    header, out, when = None, {}, None
    for line in t.splitlines():
        if line.startswith("# YYMM"):
            header = line[1:].split()
        elif line and not line.startswith("#") and header:
            c = line.split()
            if len(c) < len(header):
                continue
            def col(name):
                v = num(c[header.index(name)])
                return None if v is None or v <= -9 else v
            out[int(c[1])] = {"t": col("TA"), "h": col("HM"), "w": col("WS")}
            when = c[0]
    return out, when


# ── 단기예보 (오늘~글피, 1시간 간격) ────────────────────────
def short_base(now):
    b = now - dt.timedelta(minutes=15)
    hs = [h for h in (2, 5, 8, 11, 14, 17, 20, 23) if h <= b.hour]
    if not hs:
        return (b - dt.timedelta(days=1)).date(), 23
    return b.date(), hs[-1]


def short_fcst(src, nx, ny, now):
    bd, bh = short_base(now)
    it = src.fcst(f"VilageFcstInfoService_2.0/getVilageFcst?pageNo=1&numOfRows=1500&dataType=JSON"
                  f"&base_date={bd:%Y%m%d}&base_time={bh:02d}00&nx={nx}&ny={ny}")
    if not it:
        return None
    slots = {}
    for x in it:
        t = dt.datetime.strptime(x["fcstDate"] + x["fcstTime"], "%Y%m%d%H%M").replace(tzinfo=KST)
        slots.setdefault(t, {})[x["category"]] = x["fcstValue"]
    return dict(sorted(slots.items()))


# ── 중기예보 (3~10일 뒤) ─────────────────────────────────
def mid_tmfc(now):
    t = now - dt.timedelta(minutes=10)
    if t.hour >= 18:
        return dt.datetime(t.year, t.month, t.day, 18, tzinfo=KST)
    if t.hour >= 6:
        return dt.datetime(t.year, t.month, t.day, 6, tzinfo=KST)
    y = t - dt.timedelta(days=1)
    return dt.datetime(y.year, y.month, y.day, 18, tzinfo=KST)


_mid_cache = {}


def mid(src, kind, reg, tm):
    k = (kind, reg)
    if k not in _mid_cache:
        it = src.fcst(f"MidFcstInfoService/{kind}?pageNo=1&numOfRows=10&dataType=JSON&regId={reg}&tmFc={tm:%Y%m%d%H%M}")
        _mid_cache[k] = it[0] if it else None
    return _mid_cache[k]


def city_block(src, c, obs, now, prev):
    name, nx, ny, land, ta, stn = c
    today = now.date()
    slots = short_fcst(src, nx, ny, now)
    block = {"name": name}

    # 지금
    o = obs.get(stn, {})
    cur = None
    if slots:
        future = [t for t in slots if t >= now.replace(minute=0, second=0, microsecond=0)]
        cur = slots[future[0]] if future else None
    if cur or o.get("t") is not None:
        sky = int(num((cur or {}).get("SKY")) or 0)
        pty = int(num((cur or {}).get("PTY")) or 0)
        t = o.get("t") if o.get("t") is not None else num((cur or {}).get("TMP"))
        block["now"] = {
            "t": t,
            "i": icon(sky, pty, is_day(now)) if cur else "",
            "s": (PTY_TEXT.get(pty) or SKY_TEXT.get(sky, "")) if cur else "",
            "h": o.get("h") if o.get("h") is not None else num((cur or {}).get("REH")),
            "w": o.get("w") if o.get("w") is not None else num((cur or {}).get("WSD")),
            "p": num((cur or {}).get("POP")),
        }
    elif prev and prev.get("now"):
        block["now"] = prev["now"]

    # 시간별: 지금부터 3시간 간격 8칸
    if slots:
        hours = []
        start = now.replace(minute=0, second=0, microsecond=0)
        for t, v in slots.items():
            if t < start or int((t - start).total_seconds()) // 3600 % 3 or len(hours) >= 8:
                continue
            hours.append({"l": "지금" if t == start else f"{t.hour}시", "t": num(v.get("TMP")),
                          "i": icon(int(num(v.get("SKY")) or 0), int(num(v.get("PTY")) or 0), is_day(t)),
                          "p": num(v.get("POP"))})
        block["hours"] = hours
    elif prev and prev.get("hours"):
        block["hours"] = prev["hours"]   # 받지 못하면 지난번 값

    # 날짜별 7일: 단기예보가 있는 날은 그것으로, 나머지는 중기예보로
    days = []
    tm = mid_tmfc(now)
    for n in range(7):
        d = today + dt.timedelta(days=n)
        day = {"l": day_label(d, today), "d": d.day, "wd": d.weekday()}
        ds = {t: v for t, v in (slots or {}).items() if t.date() == d}
        if ds and len(ds) >= 6:
            temps = [num(v.get("TMP")) for v in ds.values() if num(v.get("TMP")) is not None]
            lo = next((num(v["TMN"]) for v in ds.values() if "TMN" in v), None)
            hi = next((num(v["TMX"]) for v in ds.values() if "TMX" in v), None)
            day["lo"] = lo if lo is not None else min(temps)
            day["hi"] = hi if hi is not None else max(temps)
            pops = [num(v.get("POP")) or 0 for v in ds.values()]
            day["p"] = max(pops)
            wet = [int(num(v.get("PTY")) or 0) for t, v in ds.items() if 6 <= t.hour <= 21 and (num(v.get("POP")) or 0) >= 60]
            wet = [p for p in wet if p]
            noon = ds.get(dt.datetime(d.year, d.month, d.day, 12, tzinfo=KST)) or list(ds.values())[len(ds) // 2]
            day["i"] = PTY_ICON[wet[0]] if wet else icon(int(num(noon.get("SKY")) or 0), 0, True)
        else:
            k = (d - tm.date()).days
            l, t = mid(src, "getMidLandFcst", land, tm), mid(src, "getMidTa", ta, tm)
            if l and t and f"taMin{k}" in t:
                wf = l.get(f"wf{k}Pm") or l.get(f"wf{k}") or ""
                day["i"] = text_icon(wf)
                day["lo"], day["hi"] = num(t.get(f"taMin{k}")), num(t.get(f"taMax{k}"))
                day["p"] = max(num(l.get(f"rnSt{k}Am")) or 0, num(l.get(f"rnSt{k}Pm")) or 0, num(l.get(f"rnSt{k}")) or 0)
            elif prev:
                old = next((x for x in prev.get("days", []) if x.get("d") == d.day and x.get("wd") == d.weekday() and "i" in x), None)
                if old:
                    day.update({k2: old[k2] for k2 in ("i", "lo", "hi", "p") if k2 in old})
        days.append(day)
    block["days"] = days
    return block


def holidays_near(today):
    try:
        import holidays
    except ImportError:
        return []
    kr = holidays.KR(years=[today.year, today.year + 1], language="ko")
    start = today.replace(day=1)
    end = start + dt.timedelta(days=100)
    return [{"d": d.isoformat(), "n": n} for d, n in sorted(kr.items()) if start <= d <= end]


def load_prev():
    url = os.environ.get("PREV_URL", "")
    if not url:
        return {}
    try:
        j = requests.get(url, timeout=20).json()
        return {c["name"]: c for c in j.get("cities", [])}
    except Exception:
        return {}


def main():
    now = dt.datetime.now(KST)
    src = Source()
    if not src.hub and not src.dgo:
        note("인증키가 없습니다 (KMA_KEY / DATA_GO_KR_KEY)")
    prev = load_prev()
    obs, obs_time = observations(src)
    cities = [city_block(src, c, obs, now, prev.get(c[0])) for c in CITIES]
    out = {
        "updated": f"{now.month}월 {now.day}일 {now:%H:%M} 기준",
        "ts": now.isoformat(timespec="minutes"),
        "obs": obs_time,
        "cities": cities,
        "holidays": holidays_near(now.date()),
        "log": log[:20],
    }
    os.makedirs("site", exist_ok=True)
    with open("site/weather.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"ok: {len(cities)} cities, {len(log)} notes")


if __name__ == "__main__":
    main()
