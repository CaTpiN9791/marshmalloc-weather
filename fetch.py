# VRChat 월드 Marshmalloc 의 날씨판이 읽는 weather.json 을 만든다. GitHub Actions 가 1시간마다 돌린다.
#  - 국내 도시: 기상청 단기·중기예보 (활용신청 승인 전이거나 실패하면 Open-Meteo 로 채움)
#  - 해외 도시: Open-Meteo (키 필요 없음)
#  - 날씨판은 방문자 위치(IP)·시간대에서 가장 가까운 도시를 고른다
# 환경 변수
#   KMA_KEY        : 기상청 API허브(apihub.kma.go.kr) 인증키
#   DATA_GO_KR_KEY : (선택) 공공데이터포털 일반 인증키. 있으면 기상청 예보를 이쪽에서 받는다
import datetime as dt
import json
import math
import os
import sys

import requests

KST = dt.timezone(dt.timedelta(hours=9))
APIHUB = "https://apihub.kma.go.kr/api/"
DATAGO = "https://apis.data.go.kr/1360000/"
DAYS = 8   # 자정을 넘겨도 7칸이 남도록 하루 더

# 국내: 이름, 영문, 위도, 경도, 격자 nx, ny, 중기 육상 구역, 중기 기온 지점
KR = [
    ("서울", "Seoul", 37.566, 126.978, 60, 127, "11B00000", "11B10101"),
    ("인천", "Incheon", 37.456, 126.705, 55, 124, "11B00000", "11B20201"),
    ("수원", "Suwon", 37.263, 127.029, 60, 121, "11B00000", "11B20601"),
    ("춘천", "Chuncheon", 37.881, 127.730, 73, 134, "11D10000", "11D10301"),
    ("강릉", "Gangneung", 37.752, 128.876, 92, 131, "11D20000", "11D20501"),
    ("청주", "Cheongju", 36.642, 127.489, 69, 106, "11C10000", "11C10301"),
    ("대전", "Daejeon", 36.351, 127.385, 67, 100, "11C20000", "11C20401"),
    ("전주", "Jeonju", 35.825, 127.148, 63, 89, "11F10000", "11F10201"),
    ("광주", "Gwangju", 35.160, 126.851, 58, 74, "11F20000", "11F20501"),
    ("대구", "Daegu", 35.871, 128.601, 89, 90, "11H10000", "11H10701"),
    ("울산", "Ulsan", 35.538, 129.311, 102, 84, "11H20000", "11H20101"),
    ("부산", "Busan", 35.180, 129.075, 98, 76, "11H20000", "11H20201"),
    ("제주", "Jeju", 33.500, 126.531, 52, 38, "11G00000", "11G00201"),
]

# 해외: 이름, 영문, 위도, 경도, 나라 (시간대가 같은 곳은 앞쪽이 시간대만 알 때의 기본값)
# 국내 시 단위 추가 (이름, 영문, 위도, 경도). 격자 nx/ny 는 위경도에서 계산, 중기 구역은 가장 가까운 위 13곳을 따른다
KR_EXTRA = [
    ("고양", "Goyang", 37.658, 126.832), ("용인", "Yongin", 37.241, 127.178), ("성남", "Seongnam", 37.420, 127.127),
    ("부천", "Bucheon", 37.503, 126.766), ("화성", "Hwaseong", 37.199, 126.831), ("안산", "Ansan", 37.322, 126.831),
    ("남양주", "Namyangju", 37.636, 127.216), ("안양", "Anyang", 37.394, 126.957), ("평택", "Pyeongtaek", 36.992, 127.113),
    ("시흥", "Siheung", 37.380, 126.803), ("파주", "Paju", 37.760, 126.780), ("의정부", "Uijeongbu", 37.738, 127.034),
    ("김포", "Gimpo", 37.615, 126.716), ("경기 광주", "Gwangju (Gyeonggi)", 37.429, 127.255), ("하남", "Hanam", 37.539, 127.215),
    ("광명", "Gwangmyeong", 37.479, 126.865), ("군포", "Gunpo", 37.362, 126.935), ("오산", "Osan", 37.150, 127.077),
    ("이천", "Icheon", 37.272, 127.435), ("양주", "Yangju", 37.785, 127.046), ("안성", "Anseong", 37.008, 127.280),
    ("구리", "Guri", 37.594, 127.130), ("포천", "Pocheon", 37.895, 127.200), ("의왕", "Uiwang", 37.345, 126.968),
    ("여주", "Yeoju", 37.298, 127.637), ("동두천", "Dongducheon", 37.904, 127.061), ("과천", "Gwacheon", 37.429, 126.988),
    ("원주", "Wonju", 37.342, 127.920), ("동해", "Donghae", 37.525, 129.114), ("속초", "Sokcho", 38.207, 128.592),
    ("삼척", "Samcheok", 37.450, 129.165), ("태백", "Taebaek", 37.164, 128.986),
    ("충주", "Chungju", 36.991, 127.926), ("제천", "Jecheon", 37.133, 128.191),
    ("천안", "Cheonan", 36.815, 127.114), ("아산", "Asan", 36.790, 127.002), ("서산", "Seosan", 36.785, 126.450),
    ("당진", "Dangjin", 36.890, 126.628), ("공주", "Gongju", 36.446, 127.119), ("보령", "Boryeong", 36.333, 126.613),
    ("논산", "Nonsan", 36.187, 127.099), ("계룡", "Gyeryong", 36.274, 127.249), ("세종", "Sejong", 36.480, 127.289),
    ("군산", "Gunsan", 35.968, 126.737), ("익산", "Iksan", 35.948, 126.958), ("정읍", "Jeongeup", 35.570, 126.856),
    ("남원", "Namwon", 35.416, 127.390), ("김제", "Gimje", 35.804, 126.880),
    ("목포", "Mokpo", 34.812, 126.392), ("여수", "Yeosu", 34.760, 127.662), ("순천", "Suncheon", 34.951, 127.487),
    ("광양", "Gwangyang", 34.940, 127.696), ("나주", "Naju", 35.016, 126.711),
    ("포항", "Pohang", 36.019, 129.343), ("경주", "Gyeongju", 35.856, 129.225), ("구미", "Gumi", 36.120, 128.344),
    ("경산", "Gyeongsan", 35.825, 128.741), ("안동", "Andong", 36.568, 128.730), ("김천", "Gimcheon", 36.140, 128.114),
    ("영주", "Yeongju", 36.806, 128.624), ("상주", "Sangju", 36.411, 128.159), ("영천", "Yeongcheon", 35.973, 128.939),
    ("문경", "Mungyeong", 36.587, 128.187),
    ("창원", "Changwon", 35.228, 128.681), ("김해", "Gimhae", 35.229, 128.889), ("진주", "Jinju", 35.180, 128.108),
    ("양산", "Yangsan", 35.335, 129.037), ("거제", "Geoje", 34.880, 128.621), ("통영", "Tongyeong", 34.854, 128.433),
    ("사천", "Sacheon", 35.004, 128.064), ("밀양", "Miryang", 35.504, 128.747),
    ("서귀포", "Seogwipo", 33.254, 126.560),
]


def kma_grid(lat, lon):
    """위경도 → 기상청 동네예보 격자 (LCC, 기상청 공개 공식)"""
    RE, GRID, SLAT1, SLAT2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    DEG = math.pi / 180.0
    re = RE / GRID
    s1, s2, olon, olat = SLAT1 * DEG, SLAT2 * DEG, OLON * DEG, OLAT * DEG
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(math.tan(math.pi * 0.25 + s2 * 0.5) / math.tan(math.pi * 0.25 + s1 * 0.5))
    sf = math.tan(math.pi * 0.25 + s1 * 0.5) ** sn * math.cos(s1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn
    ra = re * sf / math.tan(math.pi * 0.25 + lat * DEG * 0.5) ** sn
    theta = lon * DEG - olon
    if theta > math.pi: theta -= 2 * math.pi
    if theta < -math.pi: theta += 2 * math.pi
    theta *= sn
    return int(ra * math.sin(theta) + XO + 0.5), int(ro - ra * math.cos(theta) + YO + 0.5)


def _extend_kr():
    base = list(KR)
    for name, en, lat, lon in KR_EXTRA:
        nx, ny = kma_grid(lat, lon)
        near = min(base, key=lambda c: (c[2] - lat) ** 2 + ((c[3] - lon) * math.cos(lat * math.pi / 180)) ** 2)
        KR.append((name, en, lat, lon, nx, ny, near[6], near[7]))
    KR.sort(key=lambda c: c[0])   # 가나다순 (날씨판에서 ◀▶ 로 고르기 쉽게)


_extend_kr()

WORLD = [
    ("도쿄", "Tokyo", 35.68, 139.69, "JP"), ("오사카", "Osaka", 34.69, 135.50, "JP"),
    ("삿포로", "Sapporo", 43.06, 141.35, "JP"), ("후쿠오카", "Fukuoka", 33.59, 130.40, "JP"),
    ("타이베이", "Taipei", 25.03, 121.57, "TW"), ("상하이", "Shanghai", 31.23, 121.47, "CN"),
    ("베이징", "Beijing", 39.90, 116.41, "CN"), ("홍콩", "Hong Kong", 22.32, 114.17, "HK"),
    ("마닐라", "Manila", 14.60, 120.98, "PH"), ("싱가포르", "Singapore", 1.35, 103.82, "SG"),
    ("쿠알라룸푸르", "Kuala Lumpur", 3.14, 101.69, "MY"), ("방콕", "Bangkok", 13.76, 100.50, "TH"),
    ("하노이", "Hanoi", 21.03, 105.85, "VN"), ("호찌민", "Ho Chi Minh City", 10.82, 106.63, "VN"),
    ("자카르타", "Jakarta", -6.21, 106.85, "ID"), ("델리", "Delhi", 28.61, 77.21, "IN"),
    ("뭄바이", "Mumbai", 19.08, 72.88, "IN"), ("두바이", "Dubai", 25.20, 55.27, "AE"),
    ("이스탄불", "Istanbul", 41.01, 28.98, "TR"), ("모스크바", "Moscow", 55.76, 37.62, "RU"),
    ("런던", "London", 51.51, -0.13, "GB"), ("파리", "Paris", 48.86, 2.35, "FR"),
    ("베를린", "Berlin", 52.52, 13.40, "DE"), ("암스테르담", "Amsterdam", 52.37, 4.90, "NL"),
    ("마드리드", "Madrid", 40.42, -3.70, "ES"), ("로마", "Rome", 41.90, 12.50, "IT"),
    ("스톡홀름", "Stockholm", 59.33, 18.07, "SE"), ("바르샤바", "Warsaw", 52.23, 21.01, "PL"),
    ("헬싱키", "Helsinki", 60.17, 24.94, "FI"), ("카이로", "Cairo", 30.04, 31.24, "EG"),
    ("요하네스버그", "Johannesburg", -26.20, 28.05, "ZA"), ("시드니", "Sydney", -33.87, 151.21, "AU"),
    ("멜버른", "Melbourne", -37.81, 144.96, "AU"), ("브리즈번", "Brisbane", -27.47, 153.03, "AU"),
    ("퍼스", "Perth", -31.95, 115.86, "AU"), ("오클랜드", "Auckland", -36.85, 174.76, "NZ"),
    ("뉴욕", "New York", 40.71, -74.01, "US"), ("토론토", "Toronto", 43.65, -79.38, "CA"),
    ("시카고", "Chicago", 41.88, -87.63, "US"), ("댈러스", "Dallas", 32.78, -96.80, "US"),
    ("덴버", "Denver", 39.74, -104.99, "US"), ("로스앤젤레스", "Los Angeles", 34.05, -118.24, "US"),
    ("샌프란시스코", "San Francisco", 37.77, -122.42, "US"), ("시애틀", "Seattle", 47.61, -122.33, "US"),
    ("밴쿠버", "Vancouver", 49.28, -123.12, "CA"), ("앵커리지", "Anchorage", 61.22, -149.90, "US"),
    ("호놀룰루", "Honolulu", 21.31, -157.86, "US"), ("멕시코시티", "Mexico City", 19.43, -99.13, "MX"),
    ("상파울루", "São Paulo", -23.55, -46.63, "BR"), ("부에노스아이레스", "Buenos Aires", -34.60, -58.38, "AR"),
    ("산티아고", "Santiago", -33.45, -70.67, "CL"), ("리마", "Lima", -12.05, -77.04, "PE"),
]

PTY_ICON = {1: "rain", 2: "sleet", 3: "snow", 4: "shower", 5: "rain", 6: "sleet", 7: "snow"}
MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

log = []


def note(s):
    log.append(s)
    print(s, file=sys.stderr)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def r1(v):
    return None if v is None else round(v, 1)


# ── Open-Meteo ─────────────────────────────────────────
def wmo_icon(code):
    c = int(code or 0)
    if c <= 1:
        return "sun"
    if c == 2:
        return "partly"
    if c in (3, 45, 48):
        return "cloud"
    if c in (66, 67, 56, 57):
        return "sleet"
    if 71 <= c <= 77 or c in (85, 86):
        return "snow"
    if 80 <= c <= 82 or c >= 95:
        return "shower"
    return "rain"


def open_meteo(points):
    """points: [(lat, lon)] → [(tz 분, [day...])] (실패하면 None)"""
    out = []
    for i in range(0, len(points), 50):
        chunk = points[i:i + 50]
        url = ("https://api.open-meteo.com/v1/forecast?"
               f"latitude={','.join(str(p[0]) for p in chunk)}&longitude={','.join(str(p[1]) for p in chunk)}"
               "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
               f"&timezone=auto&forecast_days={DAYS}")
        try:
            r = requests.get(url, timeout=40)
            r.raise_for_status()
            j = r.json()
            j = j if isinstance(j, list) else [j]
        except Exception as e:
            note(f"open-meteo: {e}")
            out += [None] * len(chunk)
            continue
        for x in j:
            d = x["daily"]
            days = []
            for k, t in enumerate(d["time"]):
                day = dt.date.fromisoformat(t)
                days.append({"m": day.month, "d": day.day, "wd": day.weekday(),
                             "i": wmo_icon(d["weather_code"][k]),
                             "hi": r1(d["temperature_2m_max"][k]), "lo": r1(d["temperature_2m_min"][k]),
                             "p": d["precipitation_probability_max"][k] or 0})
            out.append((x.get("utc_offset_seconds", 0) // 60, days))
    return out


# ── 기상청 ────────────────────────────────────────────
class Kma:
    def __init__(self):
        self.hub = os.environ.get("KMA_KEY", "").strip()
        self.dgo = os.environ.get("DATA_GO_KR_KEY", "").strip()
        self.mid_cache = {}
        self.denied = False

    def items(self, path):
        if self.denied or not (self.hub or self.dgo):
            return None
        if self.dgo:
            url, key = DATAGO + path + "&serviceKey=" + self.dgo, None
        else:
            url = APIHUB + "typ02/openApi/" + path + "&authKey=" + self.hub
        name = path.split("?")[0].rsplit("/", 1)[-1]
        try:
            r = requests.get(url, timeout=25)
            r.encoding = "utf-8"
            if r.status_code != 200:
                note(f"{name}: HTTP {r.status_code}")
                if r.status_code == 403:
                    self.denied = True   # 활용신청 전: 나머지 도시도 같은 결과라 더 부르지 않는다
                return None
            res = r.json()["response"]
            if res["header"]["resultCode"] != "00":
                note(f"{name}: {res['header']['resultCode']} {res['header'].get('resultMsg', '')}")
                return None
            it = res["body"]["items"]["item"]
            return it if isinstance(it, list) else [it]
        except Exception as e:
            note(f"{name}: {e}")
            return None

    def short(self, nx, ny, now):
        b = now - dt.timedelta(minutes=15)
        hs = [h for h in (2, 5, 8, 11, 14, 17, 20, 23) if h <= b.hour]
        bd, bh = (b.date(), hs[-1]) if hs else ((b - dt.timedelta(days=1)).date(), 23)
        it = self.items(f"VilageFcstInfoService_2.0/getVilageFcst?pageNo=1&numOfRows=1500&dataType=JSON"
                        f"&base_date={bd:%Y%m%d}&base_time={bh:02d}00&nx={nx}&ny={ny}")
        if not it:
            return {}
        slots = {}
        for x in it:
            t = dt.datetime.strptime(x["fcstDate"] + x["fcstTime"], "%Y%m%d%H%M")
            slots.setdefault(t, {})[x["category"]] = x["fcstValue"]
        return slots

    def mid(self, kind, reg, tm):
        k = (kind, reg)
        if k not in self.mid_cache:
            it = self.items(f"MidFcstInfoService/{kind}?pageNo=1&numOfRows=10&dataType=JSON&regId={reg}&tmFc={tm:%Y%m%d%H%M}")
            self.mid_cache[k] = it[0] if it else None
        return self.mid_cache[k]


def sky_icon(sky):
    return {1: "sun", 3: "partly"}.get(sky, "cloud")


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


def kma_days(kma, c, now):
    """기상청 값으로 채운 날만 돌려준다 {date: day}"""
    _, _, _, _, nx, ny, land, ta = c
    slots = kma.short(nx, ny, now)
    t = now - dt.timedelta(minutes=10)
    tm = (dt.datetime(t.year, t.month, t.day, 18) if t.hour >= 18 else
          dt.datetime(t.year, t.month, t.day, 6) if t.hour >= 6 else
          dt.datetime(t.year, t.month, t.day, 18) - dt.timedelta(days=1))
    out = {}
    for n in range(DAYS):
        d = now.date() + dt.timedelta(days=n)
        ds = {k: v for k, v in slots.items() if k.date() == d}
        day = {"m": d.month, "d": d.day, "wd": d.weekday()}
        if len(ds) >= 6:
            temps = [num(v.get("TMP")) for v in ds.values() if num(v.get("TMP")) is not None]
            lo = next((num(v["TMN"]) for v in ds.values() if "TMN" in v), None)
            hi = next((num(v["TMX"]) for v in ds.values() if "TMX" in v), None)
            day["lo"] = lo if lo is not None else min(temps)
            day["hi"] = hi if hi is not None else max(temps)
            day["p"] = max(num(v.get("POP")) or 0 for v in ds.values())
            wet = [int(num(v.get("PTY")) or 0) for k, v in ds.items() if 6 <= k.hour <= 21 and (num(v.get("POP")) or 0) >= 60]
            wet = [p for p in wet if p]
            noon = ds.get(dt.datetime(d.year, d.month, d.day, 12)) or list(ds.values())[len(ds) // 2]
            day["i"] = PTY_ICON.get(wet[0], "rain") if wet else sky_icon(int(num(noon.get("SKY")) or 0))
            out[d] = day
            continue
        k = (d - tm.date()).days
        lf, tf = kma.mid("getMidLandFcst", land, tm), kma.mid("getMidTa", ta, tm)
        if lf and tf and f"taMin{k}" in tf:
            day["i"] = text_icon(lf.get(f"wf{k}Pm") or lf.get(f"wf{k}"))
            day["lo"], day["hi"] = num(tf.get(f"taMin{k}")), num(tf.get(f"taMax{k}"))
            day["p"] = max(num(lf.get(f"rnSt{k}Am")) or 0, num(lf.get(f"rnSt{k}Pm")) or 0, num(lf.get(f"rnSt{k}")) or 0)
            out[d] = day
    return out


def holidays_near(today):
    try:
        import holidays
    except ImportError:
        return []
    years = [today.year - 1, today.year, today.year + 1]
    ko = holidays.KR(years=years, language="ko")
    en = holidays.KR(years=years, language="en_US")
    start = dt.date(today.year - 1, 12, 1)
    end = dt.date(today.year + 1, 12, 31)
    return [{"d": d.isoformat(), "n": n, "e": en.get(d, n)} for d, n in sorted(ko.items()) if start <= d <= end]


def main():
    now = dt.datetime.now(KST).replace(tzinfo=None)   # 한국 시각
    kma = Kma()
    if not (kma.hub or kma.dgo):
        note("기상청 인증키가 없습니다 (KMA_KEY / DATA_GO_KR_KEY)")
    pts = [(c[2], c[3]) for c in KR] + [(c[2], c[3]) for c in WORLD]
    om = open_meteo(pts)
    cities = []
    for i, c in enumerate(KR):
        tz, days = om[i] if om[i] else (540, [])
        kd = kma_days(kma, c, now)
        merged = []
        for day in days:   # Open-Meteo 날짜 틀에 기상청 값을 덮는다
            k = dt.date(now.year if day["m"] >= now.month - 1 else now.year + 1, day["m"], day["d"])
            merged.append(kd.get(k, day))
        if not days:
            merged = [kd[k] for k in sorted(kd)]
        cities.append({"name": c[0], "en": c[1], "lat": c[2], "lon": c[3], "cc": "KR", "tz": tz, "src": "kma" if kd else "om", "days": merged})
    for i, c in enumerate(WORLD):
        r = om[len(KR) + i]
        if not r:
            continue
        cities.append({"name": c[0], "en": c[1], "lat": c[2], "lon": c[3], "cc": c[4], "tz": r[0], "days": r[1]})
    out = {
        "ts": now.isoformat(timespec="minutes") + "+09:00",
        "upd_ko": f"{now.month}월 {now.day}일 {now:%H:%M} 기준",
        "upd_en": f"Updated {MON_EN[now.month - 1]} {now.day}, {now:%H:%M} KST",
        "cities": cities,
        "holidays": holidays_near(now.date()),
        "log": log[:20],
    }
    os.makedirs("site", exist_ok=True)
    with open("site/weather.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    kma_n = sum(1 for c in cities if c.get("src") == "kma")
    print(f"ok: {len(cities)} cities (기상청 {kma_n}), {len(log)} notes, {os.path.getsize('site/weather.json')} bytes")


if __name__ == "__main__":
    main()
