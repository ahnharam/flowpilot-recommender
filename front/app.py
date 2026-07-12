"""FlowPilot Streamlit client.

The client only collects context and renders the FastAPI response. All routine
selection and scoring stays in the backend.
"""

from __future__ import annotations

import html
import json
import os
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
import streamlit as st


st.set_page_config(
    page_title="FlowPilot | 상황 기반 몰입 루틴",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


API_URL = os.getenv("API_URL", "http://localhost:8000").strip()


def _timeout_from_env() -> float:
    try:
        return max(1.0, float(os.getenv("API_TIMEOUT", "20")))
    except ValueError:
        return 20.0


API_TIMEOUT = _timeout_from_env()
REQUIRED_RESPONSE_FIELDS = {
    "request_id",
    "algorithm_version",
    "recommendation",
    "alternatives",
    "rationale",
    "generated_at",
}

ENERGY_LABELS = {
    1: "1 · 방전 직전",
    2: "2 · 조금 지침",
    3: "3 · 보통",
    4: "4 · 꽤 선명함",
    5: "5 · 에너지 충전",
}
ENVIRONMENTS = {
    "조용한 개인 공간": "quiet",
    "학교 · 사무실 · 공유 공간": "shared",
    "카페 · 공용 공간": "cafe",
    "이동 중 · 짧은 대기": "commute",
}
TASK_TYPES = {
    "학습 · 문제 풀이": "study",
    "코딩 · 디버깅": "coding",
    "글쓰기 · 문서 작성": "writing",
    "창작 · 기획": "creative",
    "읽기 · 자료 조사": "reading",
    "정리 · 행정": "admin",
}
INTERRUPTION_LEVELS = {
    "낮음 · 거의 없음": "low",
    "보통 · 가끔 있음": "medium",
    "높음 · 자주 끊김": "high",
}
PREFERRED_STYLES = {
    "구조적으로 · 명확한 순서": "structured",
    "유연하게 · 상황에 맞춰": "flexible",
    "게임처럼 · 도전과 보상": "gamified",
}


class RecommendationAPIError(Exception):
    """A user-safe API communication or contract error."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


def endpoint_for(api_url: str) -> str:
    base = api_url.rstrip("/")
    if base.endswith("/api/v1/recommend"):
        return base
    return f"{base}/api/v1/recommend"


def public_api_label(api_url: str) -> str:
    parsed = urlparse(api_url)
    if parsed.hostname:
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.hostname}{port}"
    return "환경 변수 확인 필요"


def extract_error_detail(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:240]

    if isinstance(body, dict):
        detail = body.get("detail") or body.get("message") or body.get("error")
        if isinstance(detail, list):
            messages: list[str] = []
            for item in detail:
                if isinstance(item, dict):
                    location = ".".join(str(part) for part in item.get("loc", []))
                    message = str(item.get("msg", "입력값을 확인해 주세요."))
                    messages.append(f"{location}: {message}" if location else message)
                else:
                    messages.append(str(item))
            return " · ".join(messages)[:400]
        if detail is not None:
            return str(detail)[:400]
    return json.dumps(body, ensure_ascii=False)[:400]


def request_recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    """Send the user's context to FastAPI without making any local recommendation."""

    try:
        response = requests.post(
            endpoint_for(API_URL),
            json=payload,
            headers={"Accept": "application/json"},
            timeout=API_TIMEOUT,
        )
    except requests.Timeout as exc:
        raise RecommendationAPIError(
            "추천 서버의 응답이 늦어지고 있어요.",
            "잠시 뒤 다시 시도해 주세요.",
        ) from exc
    except requests.ConnectionError as exc:
        raise RecommendationAPIError(
            "추천 서버에 연결할 수 없어요.",
            "FastAPI 실행 상태와 API_URL 설정을 확인해 주세요.",
        ) from exc
    except requests.RequestException as exc:
        raise RecommendationAPIError(
            "추천 요청을 보내는 중 문제가 발생했어요.", str(exc)[:240]
        ) from exc

    if not response.ok:
        detail = extract_error_detail(response)
        if response.status_code == 422:
            message = "입력값을 처리할 수 없어요. 선택 내용을 확인해 주세요."
        elif response.status_code >= 500:
            message = "추천 서버에서 일시적인 오류가 발생했어요."
        else:
            message = f"추천 요청이 완료되지 않았어요. (HTTP {response.status_code})"
        raise RecommendationAPIError(message, detail)

    try:
        data = response.json()
    except ValueError as exc:
        raise RecommendationAPIError(
            "추천 서버가 올바른 JSON을 반환하지 않았어요.",
            "백엔드 응답 형식을 확인해 주세요.",
        ) from exc

    if not isinstance(data, dict):
        raise RecommendationAPIError(
            "추천 결과의 형식을 확인할 수 없어요.",
            "응답 최상위 값은 JSON 객체여야 합니다.",
        )

    missing = sorted(REQUIRED_RESPONSE_FIELDS - data.keys())
    if missing:
        raise RecommendationAPIError(
            "추천 결과에 필요한 정보가 빠져 있어요.",
            f"누락 필드: {', '.join(missing)}",
        )
    return data


def first_value(mapping: dict[str, Any], keys: Iterable[str], default: Any = "") -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "예" if value else "아니요"
    if isinstance(value, (str, int, float)):
        return str(value)
    if isinstance(value, list):
        return " · ".join(text_value(item) for item in value if item is not None)
    if isinstance(value, dict):
        return " · ".join(
            f"{key}: {text_value(item)}" for key, item in value.items() if item is not None
        )
    return str(value)


def safe(value: Any) -> str:
    return html.escape(text_value(value), quote=True)


def as_list(value: Any) -> list[Any]:
    if value in (None, "", [], {}):
        return []
    return value if isinstance(value, list) else [value]


def display_timestamp(value: Any) -> str:
    raw = text_value(value)
    if not raw:
        return "생성 시각 미제공"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%Y.%m.%d %H:%M")
    except (ValueError, OSError):
        return raw


def score_parts(value: Any) -> tuple[float | None, str, str]:
    """Normalize a backend-provided score only for visual progress display."""

    explanation = ""
    raw_score = value
    if isinstance(value, dict):
        raw_score = first_value(value, ["score", "value", "percent", "percentage"])
        explanation = text_value(first_value(value, ["reason", "description", "detail"]))
    try:
        number = float(raw_score)
    except (TypeError, ValueError):
        return None, text_value(raw_score), explanation

    ratio = number if 0 <= number <= 1 else number / 100
    ratio = min(1.0, max(0.0, ratio))
    label = f"{ratio * 100:.0f}%"
    return ratio, label, explanation


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --fp-ink: #15233c;
          --fp-muted: #66758f;
          --fp-blue: #3157f5;
          --fp-violet: #7b5cf0;
          --fp-mint: #12b886;
          --fp-line: #e6eaf2;
          --fp-soft: #f5f7fc;
        }
        .stApp {
          background:
            radial-gradient(circle at 72% -8%, rgba(123,92,240,.12), transparent 28rem),
            radial-gradient(circle at 4% 22%, rgba(49,87,245,.08), transparent 24rem),
            #fbfcff;
          color: var(--fp-ink);
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] {
          background: linear-gradient(180deg, #121c35 0%, #172542 100%);
          border-right: 0;
        }
        [data-testid="stSidebar"] * { color: #edf2ff; }
        [data-testid="stSidebar"] .stCaption { color: #aebbd3 !important; }
        .block-container { max-width: 1480px; padding-top: 2rem; padding-bottom: 4rem; }
        h1, h2, h3 { color: var(--fp-ink); letter-spacing: -.025em; }
        .fp-brand { display:flex; align-items:center; gap:.75rem; margin-bottom:2.3rem; }
        .fp-mark {
          width:2.55rem; height:2.55rem; display:grid; place-items:center;
          color:#fff; font-weight:800; font-size:1.15rem; border-radius:.9rem;
          background:linear-gradient(140deg,#5c7cfa,#9b6cff); box-shadow:0 10px 24px rgba(92,124,250,.28);
        }
        .fp-brand-name { font-size:1.2rem; font-weight:800; letter-spacing:-.02em; }
        .fp-brand-sub { font-size:.72rem; color:#9eacc7; margin-top:.1rem; }
        .fp-side-label { color:#8fa0bf !important; font-size:.68rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; margin:1.7rem 0 .75rem; }
        .fp-side-step { display:flex; gap:.7rem; align-items:flex-start; margin:.85rem 0; color:#dce5f6; font-size:.83rem; line-height:1.5; }
        .fp-side-num { min-width:1.5rem; height:1.5rem; display:grid; place-items:center; border-radius:50%; background:rgba(255,255,255,.1); font-size:.7rem; font-weight:800; }
        .fp-api { padding:.8rem .9rem; border:1px solid rgba(255,255,255,.12); border-radius:.8rem; background:rgba(255,255,255,.05); font-size:.78rem; }
        .fp-api-dot { display:inline-block; width:.48rem; height:.48rem; border-radius:50%; background:#3dd9a4; box-shadow:0 0 0 4px rgba(61,217,164,.12); margin-right:.5rem; }
        .fp-eyebrow { color:var(--fp-blue); font-size:.75rem; font-weight:850; letter-spacing:.11em; text-transform:uppercase; margin-bottom:.45rem; }
        .fp-title { font-size:clamp(2rem,3vw,3.5rem); line-height:1.08; font-weight:850; letter-spacing:-.055em; color:var(--fp-ink); max-width:850px; }
        .fp-title span { background:linear-gradient(120deg,var(--fp-blue),var(--fp-violet)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
        .fp-lead { margin-top:.85rem; max-width:720px; color:var(--fp-muted); font-size:1rem; line-height:1.75; }
        .fp-status-row { display:flex; gap:.6rem; flex-wrap:wrap; margin:1.35rem 0 2rem; }
        .fp-chip { display:inline-flex; align-items:center; gap:.45rem; padding:.45rem .72rem; border:1px solid var(--fp-line); border-radius:999px; background:rgba(255,255,255,.78); color:#53627b; font-size:.76rem; font-weight:700; }
        .fp-chip-dot { width:.4rem; height:.4rem; border-radius:50%; background:#94a3b8; }
        .fp-chip.ready .fp-chip-dot { background:var(--fp-mint); }
        .fp-chip.error .fp-chip-dot { background:#f06595; }
        div[data-testid="stForm"] { background:rgba(255,255,255,.88); border:1px solid var(--fp-line); border-radius:1.25rem; padding:1.2rem 1.25rem 1.35rem; box-shadow:0 18px 60px rgba(28,44,84,.06); }
        div[data-baseweb="select"] > div, .stTextArea textarea { border-color:#dfe5f0 !important; border-radius:.75rem !important; background:#fff !important; }
        .stSlider [data-testid="stThumbValue"] { color:var(--fp-blue); }
        .stButton button, .stFormSubmitButton button { border-radius:.8rem; min-height:2.9rem; font-weight:800; }
        .stFormSubmitButton button[kind="primary"] { background:linear-gradient(120deg,var(--fp-blue),var(--fp-violet)); border:0; box-shadow:0 9px 24px rgba(49,87,245,.2); }
        .fp-empty { min-height:565px; display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center; border:1px dashed #d7deeb; border-radius:1.25rem; background:linear-gradient(160deg,rgba(255,255,255,.84),rgba(246,248,254,.92)); padding:3rem; }
        .fp-orbit { width:6.2rem; height:6.2rem; border:1px solid #cdd6e8; border-radius:50%; display:grid; place-items:center; position:relative; margin-bottom:1.5rem; }
        .fp-orbit:before { content:""; position:absolute; inset:.8rem; border:1px solid #e2e7f1; border-radius:50%; }
        .fp-orbit-core { width:2.35rem; height:2.35rem; border-radius:.82rem; transform:rotate(12deg); background:linear-gradient(145deg,var(--fp-blue),var(--fp-violet)); box-shadow:0 10px 30px rgba(70,85,220,.28); }
        .fp-empty h3 { margin:.2rem 0 .65rem; font-size:1.35rem; }
        .fp-empty p { color:var(--fp-muted); line-height:1.7; max-width:430px; }
        .fp-result-hero { position:relative; overflow:hidden; padding:1.55rem 1.65rem; border-radius:1.25rem; color:white; background:linear-gradient(125deg,#223a7a 0%,#405ed5 52%,#7c5ce8 100%); box-shadow:0 18px 50px rgba(49,72,160,.2); }
        .fp-result-hero:after { content:""; position:absolute; right:-4rem; top:-6rem; width:17rem; height:17rem; border:1px solid rgba(255,255,255,.2); border-radius:50%; box-shadow:0 0 0 2.6rem rgba(255,255,255,.035),0 0 0 5.3rem rgba(255,255,255,.025); }
        .fp-result-kicker { color:#dfe6ff; font-size:.72rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; position:relative; z-index:1; }
        .fp-result-title { color:#fff; font-size:1.7rem; line-height:1.25; font-weight:850; margin:.45rem 0 .55rem; position:relative; z-index:1; }
        .fp-result-summary { color:#eef1ff; line-height:1.68; max-width:760px; position:relative; z-index:1; }
        .fp-result-tagline { color:#fff; font-weight:750; font-size:.92rem; margin-bottom:.35rem; position:relative; z-index:1; }
        .fp-result-stats { display:flex; gap:.55rem; flex-wrap:wrap; margin-top:.95rem; position:relative; z-index:1; }
        .fp-result-stat { padding:.42rem .62rem; border-radius:.6rem; background:rgba(12,25,68,.2); border:1px solid rgba(255,255,255,.16); font-size:.73rem; color:#fff; font-weight:750; }
        .fp-tags { display:flex; gap:.45rem; flex-wrap:wrap; margin-top:.9rem; position:relative; z-index:1; }
        .fp-tag { padding:.32rem .55rem; border-radius:999px; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.18); color:white; font-size:.72rem; font-weight:700; }
        .fp-meta { display:flex; gap:1rem; flex-wrap:wrap; margin-top:1rem; color:#dbe2ff; font-size:.69rem; position:relative; z-index:1; }
        .fp-section-title { margin:1.65rem 0 .8rem; font-size:1.02rem; font-weight:850; color:var(--fp-ink); }
        .fp-timeline { position:relative; margin:.25rem 0 0 .25rem; }
        .fp-step { display:grid; grid-template-columns:1.35rem 1fr; gap:.8rem; padding-bottom:1rem; position:relative; }
        .fp-step:not(:last-child):before { content:""; position:absolute; left:.41rem; top:1rem; bottom:-.1rem; width:1px; background:#dbe2ef; }
        .fp-step-dot { width:.85rem; height:.85rem; margin-top:.28rem; border-radius:50%; background:linear-gradient(145deg,var(--fp-blue),var(--fp-violet)); box-shadow:0 0 0 4px #eef1ff; z-index:1; }
        .fp-step-card { padding:.8rem .95rem; border:1px solid var(--fp-line); border-radius:.9rem; background:#fff; box-shadow:0 7px 24px rgba(30,46,88,.04); }
        .fp-step-top { display:flex; justify-content:space-between; gap:.75rem; align-items:flex-start; }
        .fp-step-name { font-size:.88rem; font-weight:800; color:var(--fp-ink); }
        .fp-step-time { white-space:nowrap; font-size:.68rem; font-weight:800; color:var(--fp-blue); background:#eef2ff; padding:.24rem .43rem; border-radius:.45rem; }
        .fp-step-desc { color:var(--fp-muted); font-size:.78rem; line-height:1.6; margin-top:.32rem; }
        .fp-note { border:1px solid var(--fp-line); border-left:3px solid var(--fp-violet); border-radius:.8rem; background:#fff; padding:.85rem 1rem; color:#53627b; font-size:.81rem; line-height:1.65; margin:.45rem 0; }
        .fp-tip { display:flex; gap:.65rem; padding:.72rem .8rem; border-radius:.8rem; background:#f3fbf8; color:#385f55; font-size:.79rem; line-height:1.55; margin:.45rem 0; }
        .fp-tip-icon { color:var(--fp-mint); font-weight:900; }
        .fp-small { color:var(--fp-muted); font-size:.75rem; }
        @media (max-width: 800px) { .block-container { padding-top:1rem; } .fp-title { font-size:2.1rem; } .fp-empty { min-height:320px; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="fp-brand">
              <div class="fp-mark">F</div>
              <div><div class="fp-brand-name">FlowPilot</div><div class="fp-brand-sub">CONTEXT-AWARE ROUTINE</div></div>
            </div>
            <div class="fp-side-label">HOW IT WORKS</div>
            <div class="fp-side-step"><span class="fp-side-num">1</span><span>지금의 목표와 여건을 짧게 알려주세요.</span></div>
            <div class="fp-side-step"><span class="fp-side-num">2</span><span>FastAPI가 상황을 바탕으로 루틴을 추천합니다.</span></div>
            <div class="fp-side-step"><span class="fp-side-num">3</span><span>타임라인대로 시작하고 대안으로 조정하세요.</span></div>
            <div class="fp-side-label">API CONNECTION</div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="fp-api"><span class="fp-api-dot"></span>{safe(public_api_label(API_URL))}</div>',
            unsafe_allow_html=True,
        )
        st.caption("실제 추천과 점수 계산은 FastAPI 서버에서 수행됩니다.")


def render_page_header() -> None:
    phase = st.session_state.get("phase", "idle")
    status_map = {
        "idle": ("입력 대기", ""),
        "ready": ("추천 준비 완료", "ready"),
        "error": ("연결 확인 필요", "error"),
    }
    label, status_class = status_map.get(phase, status_map["idle"])
    st.markdown(
        f"""
        <div class="fp-eyebrow">Design your next focus</div>
        <div class="fp-title">지금의 상황을, <span>움직일 수 있는 루틴</span>으로.</div>
        <div class="fp-lead">완벽한 계획보다 지금 실행 가능한 흐름이 중요해요. 시간·에너지·환경을 알려주면 FlowPilot이 가장 자연스러운 몰입 경로를 찾아드립니다.</div>
        <div class="fp-status-row">
          <span class="fp-chip {status_class}"><span class="fp-chip-dot"></span>{safe(label)}</span>
          <span class="fp-chip">FastAPI 연동</span>
          <span class="fp-chip">상황 기반 추천</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_input_form() -> tuple[bool, dict[str, Any]]:
    with st.form("routine_request", clear_on_submit=False):
        st.subheader("오늘의 컨텍스트")
        st.caption("7가지 신호만 입력하면 바로 실행 가능한 루틴으로 바꿔드려요.")

        goal = st.text_area(
            "지금 끝내고 싶은 목표",
            placeholder="예: 발표 자료 초안을 완성하고 핵심 메시지를 다듬기",
            height=104,
            max_chars=120,
            help="가능하면 결과물이 보이도록 구체적으로 적어주세요.",
        )

        left, right = st.columns(2)
        with left:
            available_minutes = st.slider(
                "사용 가능한 시간",
                min_value=10,
                max_value=180,
                value=45,
                step=5,
                format="%d분",
            )
        with right:
            energy_level = st.select_slider(
                "현재 에너지",
                options=list(ENERGY_LABELS),
                value=3,
                format_func=ENERGY_LABELS.get,
            )

        environment_label = st.selectbox("현재 환경", list(ENVIRONMENTS), index=0)
        task_type_label = st.selectbox("과업의 성격", list(TASK_TYPES), index=0)
        interruption_level = st.select_slider(
            "방해 가능성",
            options=list(INTERRUPTION_LEVELS),
            value="보통 · 가끔 있음",
        )
        preferred_style_label = st.radio(
            "선호하는 진행 방식",
            list(PREFERRED_STYLES),
            index=0,
            horizontal=True,
        )

        submitted = st.form_submit_button(
            "내 몰입 루틴 생성하기  →",
            type="primary",
            use_container_width=True,
        )

    payload = {
        "goal": goal.strip(),
        "available_minutes": available_minutes,
        "energy_level": energy_level,
        "environment": ENVIRONMENTS[environment_label],
        "task_type": TASK_TYPES[task_type_label],
        "interruption_level": INTERRUPTION_LEVELS[interruption_level],
        "preferred_style": PREFERRED_STYLES[preferred_style_label],
    }
    return submitted, payload


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="fp-empty">
          <div class="fp-orbit"><div class="fp-orbit-core"></div></div>
          <h3>당신의 다음 흐름을 설계할게요</h3>
          <p>왼쪽에서 지금의 조건을 알려주세요. 추천 요청 후 이곳에 맞춤 루틴, 적합도 점수, 추천 근거와 대안이 나타납니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def recommendation_view(recommendation: Any) -> dict[str, Any]:
    if isinstance(recommendation, dict):
        return recommendation
    if isinstance(recommendation, list):
        return {"name": "맞춤 몰입 루틴", "timeline": recommendation}
    return {"name": "맞춤 몰입 루틴", "summary": text_value(recommendation)}


def render_result_hero(data: dict[str, Any], recommendation: dict[str, Any]) -> None:
    title = first_value(
        recommendation,
        ["name", "title", "routine_name", "label"],
        "맞춤 몰입 루틴",
    )
    summary = first_value(
        recommendation,
        ["summary", "description", "overview", "message"],
        "지금의 조건에 맞춰 구성한 실행 흐름입니다.",
    )
    tagline = first_value(recommendation, ["tagline", "subtitle", "slogan"])
    tags = as_list(first_value(recommendation, ["tags", "tag", "keywords"]))
    tags_html = "".join(f'<span class="fp-tag">{safe(tag)}</span>' for tag in tags[:5])
    tagline_html = f'<div class="fp-result-tagline">{safe(tagline)}</div>' if tagline else ""
    score = first_value(recommendation, ["score", "total_score"])
    _, score_label, _ = score_parts(score)
    total_minutes = first_value(recommendation, ["total_minutes", "duration_minutes"])
    stats = []
    if total_minutes not in (None, ""):
        stats.append(f'<span class="fp-result-stat">총 {safe(total_minutes)}분</span>')
    if score_label:
        stats.append(f'<span class="fp-result-stat">적합도 {safe(score_label)}</span>')
    stats_html = f'<div class="fp-result-stats">{"".join(stats)}</div>' if stats else ""
    request_id = text_value(data.get("request_id"))
    short_id = f"{request_id[:12]}…" if len(request_id) > 12 else request_id
    generated_at = display_timestamp(data.get("generated_at"))
    st.markdown(
        f"""
        <div class="fp-result-hero">
          <div class="fp-result-kicker">Your recommended flow</div>
          <div class="fp-result-title">{safe(title)}</div>
          {tagline_html}
          <div class="fp-result-summary">{safe(summary)}</div>
          {stats_html}
          <div class="fp-tags">{tags_html}</div>
          <div class="fp-meta"><span>REQUEST {safe(short_id)}</span><span>ENGINE v{safe(data.get('algorithm_version'))}</span><span>{safe(generated_at)}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def timeline_fields(item: Any, index: int) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        return f"STEP {index}", text_value(item), ""

    title = text_value(first_value(item, ["title", "name", "label", "step"], f"STEP {index}"))
    description = text_value(
        first_value(item, ["description", "detail", "action", "instruction", "summary"])
    )
    time_label = text_value(first_value(item, ["time", "time_range", "range", "duration"]))
    if not time_label:
        start = first_value(item, ["start_minute", "start", "from"])
        end = first_value(item, ["end_minute", "end", "to"])
        if start not in (None, "") and end not in (None, ""):
            time_label = f"{start}–{end}분"
        elif first_value(item, ["minutes", "duration_minutes"]) not in (None, ""):
            time_label = f"{first_value(item, ['minutes', 'duration_minutes'])}분"
    return title, description, time_label


def render_timeline(recommendation: dict[str, Any]) -> None:
    timeline = first_value(recommendation, ["timeline", "steps", "routine", "phases"])
    items = as_list(timeline)
    st.markdown('<div class="fp-section-title">실행 타임라인</div>', unsafe_allow_html=True)
    if not items:
        st.caption("백엔드 응답에 타임라인이 포함되지 않았습니다.")
        return

    fragments: list[str] = []
    for index, item in enumerate(items, start=1):
        title, description, time_label = timeline_fields(item, index)
        time_html = f'<span class="fp-step-time">{safe(time_label)}</span>' if time_label else ""
        description_html = (
            f'<div class="fp-step-desc">{safe(description)}</div>' if description else ""
        )
        fragments.append(
            '<div class="fp-step">'
            '<div class="fp-step-dot"></div>'
            '<div class="fp-step-card">'
            f'<div class="fp-step-top"><span class="fp-step-name">{safe(title)}</span>{time_html}</div>'
            f'{description_html}'
            '</div>'
            '</div>'
        )
    st.markdown(f'<div class="fp-timeline">{"".join(fragments)}</div>', unsafe_allow_html=True)


SCORE_LABELS = {
    "context_fit": "상황 적합도",
    "task_fit": "과업 적합도",
    "goal_alignment": "목표 정렬도",
    "energy_fit": "에너지 적합도",
    "time_fit": "시간 적합도",
    "environment_fit": "환경 적합도",
    "interrupt_resilience": "방해 대응력",
    "interruption_fit": "방해 대응력",
    "preference_fit": "선호 방식 적합도",
    "style_fit": "진행 방식 적합도",
    "goal_fit": "목표 키워드 적합도",
    "overall": "종합 적합도",
    "total": "종합 점수",
}


def render_score_breakdown(scores: Any) -> None:
    st.markdown('<div class="fp-section-title">적합도 시그널</div>', unsafe_allow_html=True)
    if not isinstance(scores, dict) or not scores:
        if scores not in (None, "", [], {}):
            st.markdown(f'<div class="fp-note">{safe(scores)}</div>', unsafe_allow_html=True)
        else:
            st.caption("백엔드 응답에 점수 정보가 포함되지 않았습니다.")
        return

    for key, value in scores.items():
        ratio, score_label, explanation = score_parts(value)
        label = SCORE_LABELS.get(str(key), str(key).replace("_", " ").title())
        st.markdown(f"**{label}** · {score_label or '—'}")
        if ratio is not None:
            st.progress(ratio)
        if explanation:
            st.caption(explanation)


def render_rationale(rationale: Any, recommendation: dict[str, Any]) -> None:
    st.markdown('<div class="fp-section-title">왜 이 루틴인가요?</div>', unsafe_allow_html=True)
    why_it_fits = as_list(first_value(recommendation, ["why_it_fits", "reasons"]))
    if isinstance(rationale, dict):
        items = [f"<strong>{safe(key)}</strong> · {safe(value)}" for key, value in rationale.items()]
    else:
        items = [safe(item) for item in as_list(rationale)]
    items.extend(safe(item) for item in why_it_fits)
    if not items:
        st.caption("백엔드 응답에 추천 근거가 포함되지 않았습니다.")
        return
    for item in items:
        st.markdown(f'<div class="fp-note">{item}</div>', unsafe_allow_html=True)


def alternative_fields(item: Any, index: int) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        return f"대안 {index}", text_value(item), ""
    title = text_value(first_value(item, ["name", "title", "label"], f"대안 {index}"))
    tagline = text_value(first_value(item, ["tagline", "subtitle"]))
    summary = text_value(
        first_value(item, ["summary", "description", "reason", "when_to_use", "detail"])
    )
    description = f"{tagline} — {summary}" if tagline and summary else tagline or summary
    meta = text_value(first_value(item, ["total_minutes", "duration", "duration_minutes", "tag", "style"]))
    if meta and meta.isdigit():
        meta = f"{meta}분"
    return title, description, meta


def render_alternatives(alternatives: Any) -> None:
    items = as_list(alternatives)
    st.markdown('<div class="fp-section-title">상황이 바뀌면, 이런 대안</div>', unsafe_allow_html=True)
    if not items:
        st.caption("백엔드 응답에 대안이 포함되지 않았습니다.")
        return

    for index, item in enumerate(items, start=1):
        title, description, meta = alternative_fields(item, index)
        with st.container(border=True):
            st.markdown(f"**{title}**")
            if description:
                st.caption(description)
            if meta:
                st.markdown(f"`{meta}`")
            if isinstance(item, dict) and item.get("score") is not None:
                _, score_label, _ = score_parts(item["score"])
                st.markdown(f"적합도 **{score_label}**")


def render_tips(recommendation: dict[str, Any], data: dict[str, Any]) -> None:
    tips = first_value(recommendation, ["tips", "tip", "coach_tips", "notes"])
    if tips in (None, "", [], {}):
        tips = first_value(data, ["tips", "tip"])
    items = as_list(tips)
    st.markdown('<div class="fp-section-title">시작 전 작은 팁</div>', unsafe_allow_html=True)
    if not items:
        st.caption("백엔드 응답에 팁이 포함되지 않았습니다.")
        return
    for item in items:
        st.markdown(
            f'<div class="fp-tip"><span class="fp-tip-icon">✦</span><span>{safe(item)}</span></div>',
            unsafe_allow_html=True,
        )


def render_result(data: dict[str, Any]) -> None:
    recommendation = recommendation_view(data.get("recommendation"))
    render_result_hero(data, recommendation)

    timeline_column, insight_column = st.columns([1.08, 0.92], gap="large")
    with timeline_column:
        render_timeline(recommendation)
        render_alternatives(data.get("alternatives"))
    with insight_column:
        render_score_breakdown(recommendation.get("score_breakdown"))
        render_rationale(data.get("rationale"), recommendation)
        render_tips(recommendation, data)

    st.divider()
    reset_col, caption_col = st.columns([0.34, 0.66])
    with reset_col:
        if st.button("새 조건으로 다시 설계하기", use_container_width=True):
            st.session_state.response_data = None
            st.session_state.error_data = None
            st.session_state.phase = "idle"
            st.rerun()
    with caption_col:
        st.caption("추천 결과는 현재 입력한 상황을 기준으로 생성되었습니다. 조건이 달라지면 새로 요청해 주세요.")


def handle_submission(payload: dict[str, Any]) -> None:
    if not payload["goal"]:
        st.session_state.response_data = None
        st.session_state.error_data = (
            "목표를 한 문장으로 알려주세요.",
            "예: 45분 안에 발표 자료의 핵심 슬라이드 5장을 완성하기",
        )
        st.session_state.phase = "error"
        return

    st.session_state.error_data = None
    with st.status("FlowPilot이 실행 가능한 흐름을 찾고 있어요…", expanded=True) as status:
        st.write("현재 컨텍스트를 FastAPI 추천 엔진에 전달했습니다.")
        try:
            data = request_recommendation(payload)
        except RecommendationAPIError as exc:
            st.session_state.response_data = None
            st.session_state.error_data = (exc.message, exc.detail)
            st.session_state.phase = "error"
            status.update(label="추천 요청을 완료하지 못했어요", state="error", expanded=True)
        else:
            st.session_state.response_data = data
            st.session_state.last_payload = payload
            st.session_state.phase = "ready"
            status.update(label="맞춤 몰입 루틴이 준비됐어요", state="complete", expanded=False)


def main() -> None:
    inject_styles()
    st.session_state.setdefault("phase", "idle")
    st.session_state.setdefault("response_data", None)
    st.session_state.setdefault("error_data", None)
    st.session_state.setdefault("last_payload", None)

    render_sidebar()
    render_page_header()

    form_column, result_column = st.columns([0.38, 0.62], gap="large")
    with form_column:
        submitted, payload = render_input_form()
    if submitted:
        handle_submission(payload)
        # Re-run once so the header status chip and result panel reflect the new phase.
        st.rerun()

    with result_column:
        error_data = st.session_state.get("error_data")
        if error_data:
            message, detail = error_data
            st.error(message)
            if detail:
                st.caption(detail)

        response_data = st.session_state.get("response_data")
        if response_data:
            render_result(response_data)
        else:
            render_empty_state()


if __name__ == "__main__":
    main()
