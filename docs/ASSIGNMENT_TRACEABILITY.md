# 기말 과제 요구사항 추적표

원문: [기말고사 대체 과제](https://kdpark.notion.site/3326afd87d3a80428a0df222ce23a533)

| 요구사항 | FlowPilot 구현 증거 |
|---|---|
| Streamlit 사용자 입력 | 목표, 가용 시간, 에너지, 환경, 작업 유형, 방해 수준, 선호 리듬 입력 |
| 추천 요청 버튼 | `front/app.py`의 추천 폼 제출 |
| Streamlit → FastAPI 실제 요청 | `API_URL`의 `/api/v1/recommend`로 HTTP POST |
| FastAPI 입력 수신 | Pydantic 요청 모델 검증 |
| 추천 결과 생성 | 여러 루틴을 점수화하는 결정론적 추천 엔진 |
| JSON 반환 | 구조화된 추천·대안·근거·점수 응답 모델 |
| Streamlit 결과 표시 | 추천 카드, 점수, 근거, 타임라인, 대안, 실행 팁 |
| Docker 필수 | 프론트와 API를 각각 비-root 컨테이너로 실행 |
| EC2 실행 | `docker compose`로 AWS Learner Lab EC2에 배포 |
| 외부 접속 | EC2 보안 그룹에서 Streamlit 포트만 공개 |
| 개인별 차별성 | 상황 신호 7개와 다중 점수 기반의 몰입 루틴 추천 |
| GitHub 제출 | 전체 소스·테스트·배포 스크립트·CI 포함 |
| 데모 영상 | 브라우저 입력부터 FastAPI 응답, 결과, `docker ps`까지 연속 증빙 |

## 설계 원칙

- 프론트엔드에는 추천 점수 계산을 두지 않는다.
- FastAPI가 유일한 추천 계산 주체다.
- API는 동일한 입력에 동일한 결과를 반환해 데모와 테스트를 재현 가능하게 한다.
- 외부에는 Streamlit만 노출하고 FastAPI 호스트 포트는 loopback에 바인딩한다.
