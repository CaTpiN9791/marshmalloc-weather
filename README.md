# marshmalloc-weather

Marshmalloc VRChat 월드 2층 날씨판이 읽는 `weather.json` 을 만든다.
GitHub Actions 가 1시간마다 기상청 API허브에서 예보·관측을 받아 GitHub Pages 에 올린다.

- 주소: `https://<아이디>.github.io/marshmalloc-weather/weather.json`
- Secret `KMA_KEY` : 기상청 API허브 인증키 (필수)
- Secret `DATA_GO_KR_KEY` : 공공데이터포털 일반 인증키 (선택, 있으면 예보는 이쪽에서 받음)
