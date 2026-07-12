# FlowPilot Backend

상황·시간·에너지·작업 유형을 7개 점수로 평가해 최종 몰입 루틴 1개와 대안 2개를 반환하는 FastAPI 서비스입니다. 같은 입력은 항상 같은 순위, 점수, 타임라인과 `request_id`를 생성합니다(`generated_at`만 현재 시각).

## 로컬 실행

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

- Swagger UI: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>
- Recommendation: `POST http://localhost:8000/api/v1/recommend`

## 요청 예시

```json
{
  "goal": "자료구조 과제의 그래프 탐색 구현 완료",
  "available_minutes": 90,
  "energy_level": 5,
  "environment": "quiet",
  "task_type": "coding",
  "interruption_level": "low",
  "preferred_style": "structured"
}
```

응답에는 `recommendation`, 완전한 실행 정보를 가진 `alternatives` 2개, 선정 근거, 분 단위 `timeline`, 실행 `tips`, 7개 항목의 `score_breakdown`이 포함됩니다.

## 허용 입력값

| 필드 | 값 |
| --- | --- |
| `available_minutes` | 10~180 |
| `energy_level` | 1~5 |
| `environment` | `quiet`, `shared`, `cafe`, `commute` |
| `task_type` | `study`, `coding`, `writing`, `creative`, `reading`, `admin` |
| `interruption_level` | `low`, `medium`, `high` |
| `preferred_style` | `structured`, `flexible`, `gamified` |

## 테스트

```bash
pytest
```

## Docker

```bash
docker build -t flowpilot-api .
docker run --rm -p 8000:8000 flowpilot-api
```

컨테이너는 UID/GID `10001`의 비-root 사용자로 실행되며 `/health`를 자체 점검합니다.

브라우저에서 직접 호출할 프런트엔드 주소는 쉼표로 구분해 설정할 수 있습니다.

```bash
FLOWPILOT_CORS_ORIGINS=https://your-streamlit.example.com,http://localhost:8501
```
