"""
7주차 1번 수업 — 시작 코드 (필터 없음)
6주차 시각화 리포트와 같은 형태입니다. 오늘 여기에 필터를 붙여 대시보드로 만듭니다.
"""
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="사용자 행동 탐색 대시보드", layout="wide")
st.title("사용자 행동 탐색 대시보드")
st.caption("주별 세션 퍼널 | 플랫폼 · 유입 경로별 | 2025.07 ~ 2026.06")

# ------------------------------------------------------------
# 0. 필요한 데이터만 추출 — 쓸 테이블과 컬럼만 메모리 DB에 올리고, 정제 테이블 events를 처음 한 번만 만듦
# ------------------------------------------------------------
DATA_DIR = "data"                                         # 원본 CSV를 넣어 둔 폴더
NEEDED = {                                                # 이번 대시보드에 필요한 테이블과 컬럼
    "app_events": ["event_id", "event_datetime", "customer_id", "session_id",
                   "event_name", "platform", "traffic_source"],
}

@st.cache_resource
def get_db():                                             # 필요한 컬럼만 메모리 DB에 올리고, 정제 테이블 events를 만듦 (처음 한 번만)
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for name, cols in NEEDED.items():
        pd.read_csv(f"{DATA_DIR}/{name}.csv", usecols=cols).to_sql(name, con, index=False)
    # 5주차 제외 규칙: QA 계정 제외 · 중복 이벤트 제거
    con.execute("""
        CREATE TABLE events AS
        SELECT event_id, event_datetime, customer_id, session_id, event_name, platform, traffic_source
          FROM (SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY session_id, event_datetime, event_name
                                          ORDER BY event_id) AS dup
                  FROM app_events
                 WHERE customer_id NOT LIKE 'QA%')
         WHERE dup = 1
    """)
    return con

# ------------------------------------------------------------
# 1. 데이터 준비 — 정제된 events 테이블을 SQL로 집계
# ------------------------------------------------------------
@st.cache_data
def query(sql):                                           # SQL을 실행해 표로 돌려줌
    return pd.read_sql(sql, get_db())

# 주 × 플랫폼 × 유입 경로별 세션 퍼널
SQL_WEEKLY_FUNNEL = """
WITH s AS (                                               -- 세션의 첫 이벤트로 플랫폼 · 유입 경로 · 주 정하기
    SELECT session_id, platform, traffic_source,
           DATE(MIN(event_datetime), 'weekday 0', '-6 days') AS 주시작일
      FROM events
     GROUP BY session_id
)
SELECT s.주시작일,
       s.platform       AS 플랫폼,
       s.traffic_source AS 유입경로,
       COUNT(DISTINCT e.session_id)                                                                           AS 세션수,
       COUNT(DISTINCT CASE WHEN e.event_name = 'view_restaurant' THEN e.session_id END)   AS 조회세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'add_to_cart'     THEN e.session_id END)   AS 장바구니세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'begin_checkout'  THEN e.session_id END)   AS 결제시작세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'order_complete'  THEN e.session_id END)   AS 주문세션,
       SUM(CASE WHEN e.event_name = 'payment_fail' THEN 1 ELSE 0 END)                     AS 결제실패
  FROM events e
  JOIN s ON e.session_id = s.session_id
 WHERE s.주시작일 < '2026-06-29'              -- 이틀치뿐인 마지막 주 제외
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

@st.cache_data
def load_data():
    data = query(SQL_WEEKLY_FUNNEL)
    data["주시작일"] = pd.to_datetime(data["주시작일"]).dt.date
    return data

df = load_data()                                        # 주 × 플랫폼 × 유입 경로별 세션 퍼널

AI_NOTES = {
    "전체": "전체 기간 동안 주문 전환율은 14.5%이며, 조회세션에서 장바구니세션으로 넘어가는 단계의 전환율이 41.4%로 가장 낮았다. 전체 데이터의 기준이 되는 수치로 다른 집단 비교의 기본이 된다. 이 단계에서 이탈이 큰 원인은 추가적인 확인이 필요하다.",
    "Android": "주문 전환율은 14.3%로 전체와 유사하며, 가장 낮은 단계는 조회세션에서 장바구니세션(41.8%)이었다. 2026-04-13 주부터 2026-05-25 주까지 결제 전환율이 평소보다 크게 낮아진 상태가 이어졌다. 이 시기의 급격한 지표 변화는 시스템 장애나 외부 요인에 기인했을 것으로 보인다.",
    "iOS": "주문 전환율은 14.8%로 전체 대비 약간 높고, 최저 단계는 조회세션에서 장바구니세션(40.8%)이었다. 안드로이드와 달리 특정 장기 하락 기간 없이 안정적인 흐름을 보였다. 플랫폼 간 차이가 발생한 배경에 대한 정밀한 분석이 필요하다.",
    "organic": "주문 전환율은 16.0%로 전체 평균보다 높으며, 가장 낮은 단계는 조회세션에서 장바구니세션(41.4%)이었다. 전체 세션의 다수를 차지하여 전체 트렌드와 유사한 패턴을 나타냈다. 자연 유입 사용자의 특성이 반영된 결과로 보인다.",
    "paid_ad": "주문 전환율이 26.3%로 다른 유입경로 대비 매우 높았으며, 최저 단계 전환율도 조회세션에서 장바구니세션(53.7%)으로 가장 양호했다. 전체 대비 구매 의도가 높은 사용자가 집중적으로 유입된 것으로 보인다. 유료 광고 효율이 우수하게 작용했을 가능성이 있다.",
    "push": "주문 전환율이 3.2%로 전체 및 타 경로에 비해 현저히 낮았고, 세션수에서 조회세션으로의 단계가 28.4%로 가장 낮았다. 푸시 메시지를 통해 유입된 트래픽의 초기 반응률이 저조함을 보여준다. 메시지 타겟팅이나 콘텐츠의 적절성 검토가 필요하다.",
    "referral": "세션수가 121개로 500개 미만이며 주문 전환율이 0.0%, 결제시작세션에서 주문세션으로의 단계가 0.0%로 가장 낮았다. 표본 크기가 매우 작아 수치의 신뢰도가 제한적이다. 유입 경로의 실제 효과를 파악하기 위해 추가 데이터 수집이 필요하다."
}
AI_SOURCE = "🤖 Gemini가 미리 만든 해설 · 전체 기간 기준"


# ------------------------------------------------------------
# 사이드바 & 초기화 기능 (Session State 활용 위젯 버전 관리)
# ------------------------------------------------------------
if "filter_version" not in st.session_state:
    st.session_state["filter_version"] = 0

v = st.session_state["filter_version"]

st.sidebar.header("필터")

# 필터 초기화 버튼
if st.sidebar.button("필터 초기화"):
    st.session_state["filter_version"] += 1
    st.rerun()

# 기간: 주 시작일 목록에서 범위 고르기
weeks = sorted(df["주시작일"].unique())
start, end = st.sidebar.select_slider(
    "기간 (주 시작일)", 
    options=weeks, 
    value=(weeks[0], weeks[-1]),
    key=f"slider_period_{v}"
)

# 플랫폼 · 유입 경로: 여러 개 고르기 (처음엔 전부 선택)
platforms = sorted(df["플랫폼"].unique())
sel_platform = st.sidebar.multiselect(
    "플랫폼", 
    platforms, 
    default=platforms,
    key=f"multi_platform_{v}"
)
sources = sorted(df["유입경로"].unique())
sel_source = st.sidebar.multiselect(
    "유입 경로", 
    sources, 
    default=sources,
    key=f"multi_source_{v}"
)

# 고급 설정 영역
with st.sidebar.expander("고급 설정"):
    normal_default_end_idx = min(25, len(weeks) - 1)
    normal_start, normal_end = st.select_slider(
        "평소 범위 기준 기간",
        options=weeks,
        value=(weeks[0], weeks[normal_default_end_idx]),
        help="문제가 없던 기간을 고르세요. 이 기간의 주별 값 범위를 '평소 범위'로 씁니다.",
        key=f"slider_normal_{v}"
    )
    exclude_low_sample = st.checkbox(
        "세션 500개 미만 집단 제외 (집단 비교 · 드릴다운)", 
        value=False,
        key=f"chk_exclude_{v}"
    )

# ------------------------------------------------------------
# 1-1. 보고 있는 조건 캡션 표시 (제목 아래, 탭 위)
# ------------------------------------------------------------
# 기간 텍스트
period_text = f"{start} ~ {end}"

# 플랫폼 텍스트
if len(sel_platform) == len(platforms):
    platform_text = "전체"
elif len(sel_platform) == 0:
    platform_text = "선택 없음"
else:
    platform_text = ", ".join(sel_platform)

# 유입 경로 텍스트
if len(sel_source) == len(sources):
    source_text = "전체"
elif len(sel_source) == 0:
    source_text = "선택 없음"
else:
    source_text = ", ".join(sel_source)

st.caption(f"🔎 보고 있는 조건: 기간 ({period_text}) · 플랫폼 ({platform_text}) · 유입 경로 ({source_text})")

# 집단 조건(플랫폼·유입경로)만 적용한 데이터 g
g = df[df["플랫폼"].isin(sel_platform) & df["유입경로"].isin(sel_source)]

# 기존 f는 g에 기간 조건을 더해 만듦
f = g[(g["주시작일"] >= start) & (g["주시작일"] <= end)]

if f.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 바꿔 주세요.")
    st.stop()    # 여기서 화면 그리기를 멈춤

# ------------------------------------------------------------
# 탭 구성 ("📊 개요", "🔍 탐색", "✅ 액션")
# ------------------------------------------------------------
tab_overview, tab_explore, tab_action = st.tabs(["📊 개요", "🔍 탐색", "✅ 액션"])

with tab_overview:
    st.caption("이 탭에서 볼 수 있는 것: 주요 KPI 지표, 자동 규칙 기반 인사이트, 전체 AI 해설, 주별 결제 전환율, 세션 퍼널, 유입 경로별 주문 전환율")

    # ------------------------------------------------------------
    # 2. KPI 카드
    # ------------------------------------------------------------
    def rate(a, b):
        return a / b * 100 if b else 0

    t = f[["세션수", "결제시작세션", "주문세션"]].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("세션 수", f"{t['세션수']:,}개")
    c2.metric("주문 전환율 (방문 → 주문)", f"{rate(t['주문세션'], t['세션수']):.1f}%")
    c3.metric("결제 전환율 (결제 시작 → 주문)", f"{rate(t['주문세션'], t['결제시작세션']):.1f}%")

    # ------------------------------------------------------------
    # 2-1. 규칙 기반 설명 문장 (st.info)
    # ------------------------------------------------------------
    def generate_insights(f_data, g_data, norm_start, norm_end):
        # f의 마지막 4주 합계 기반 이번 값 계산을 위해 정렬된 주 목록 확인
        f_weeks = sorted(f_data["주시작일"].unique())
        if len(f_weeks) < 4:
            msg_order = "주문 전환율: 비교하려면 선택 기간을 4주 이상 골라 주세요"
            msg_payment = "결제 전환율: 비교하려면 선택 기간을 4주 이상 골라 주세요"
            return msg_order, msg_payment

        # 마지막 4주 데이터 추출 및 합계
        last_4_weeks = f_weeks[-4:]
        start_str = str(last_4_weeks[0])
        f_last4 = f_data[f_data["주시작일"].isin(last_4_weeks)]
        t_last4 = f_last4[["세션수", "결제시작세션", "주문세션"]].sum()
        
        current_order_rate = rate(t_last4["주문세션"], t_last4["세션수"])
        current_payment_rate = rate(t_last4["주문세션"], t_last4["결제시작세션"])

        # g 데이터에서 평소 범위 기준 기간 데이터 필터링
        g_normal = g_data[(g_data["주시작일"] >= norm_start) & (g_data["주시작일"] <= norm_end)]
        
        # 주별로 집계 후 분모가 0인 주 제외
        g_weekly = g_normal.groupby("주시작일")[["세션수", "결제시작세션", "주문세션"]].sum().reset_index()
        
        # 주문 전환율 평소 범위 계산 (분모: 세션수 > 0)
        g_order_valid = g_weekly[g_weekly["세션수"] > 0]
        if len(g_order_valid) < 4:
            msg_order = "주문 전환율: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
        else:
            order_rates = (g_order_valid["주문세션"] / g_order_valid["세션수"] * 100)
            min_o, max_o = order_rates.min(), order_rates.max()
            
            if current_order_rate < min_o:
                diff = min_o - current_order_rate
                msg_order = f"주문 전환율은 {start_str}부터 4주 동안 {current_order_rate:.1f}%로, 평소 범위({min_o:.1f}% ~ {max_o:.1f}%)보다 {diff:.1f}%p 낮습니다."
            elif current_order_rate > max_o:
                diff = current_order_rate - max_o
                msg_order = f"주문 전환율은 {start_str}부터 4주 동안 {current_order_rate:.1f}%로, 평소 범위({min_o:.1f}% ~ {max_o:.1f}%)보다 {diff:.1f}%p 높습니다."
            else:
                msg_order = f"주문 전환율은 {start_str}부터 4주 동안 {current_order_rate:.1f}%로, 평소 범위({min_o:.1f}% ~ {max_o:.1f}%) 안에 있습니다."

        # 결제 전환율 평소 범위 계산 (분모: 결제시작세션 > 0)
        g_payment_valid = g_weekly[g_weekly["결제시작세션"] > 0]
        if len(g_payment_valid) < 4:
            msg_payment = "결제 전환율: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
        else:
            payment_rates = (g_payment_valid["주문세션"] / g_payment_valid["결제시작세션"] * 100)
            min_p, max_p = payment_rates.min(), payment_rates.max()
            
            if current_payment_rate < min_p:
                diff = min_p - current_payment_rate
                msg_payment = f"결제 전환율은 {start_str}부터 4주 동안 {current_payment_rate:.1f}%로, 평소 범위({min_p:.1f}% ~ {max_p:.1f}%)보다 {diff:.1f}%p 낮습니다."
            elif current_payment_rate > max_p:
                diff = current_payment_rate - max_p
                msg_payment = f"결제 전환율은 {start_str}부터 4주 동안 {current_payment_rate:.1f}%로, 평소 범위({min_p:.1f}% ~ {max_p:.1f}%)보다 {diff:.1f}%p 높습니다."
            else:
                msg_payment = f"결제 전환율은 {start_str}부터 4주 동안 {current_payment_rate:.1f}%로, 평소 범위({min_p:.1f}% ~ {max_p:.1f}%) 안에 있습니다."

        return msg_order, msg_payment

    msg_order, msg_payment = generate_insights(f, g, normal_start, normal_end)

    st.info(msg_order)
    st.info(msg_payment)
    st.caption(f"📏 자동 계산 · 평소 범위 기준 기간 {normal_start} ~ {normal_end} (주별 값)")

    # 1. 규칙 문장과 caption 아래에 AI 해설 전체 추가
    with st.expander("🤖 AI 해설 · 전체", expanded=False):
        st.write(AI_NOTES.get("전체", ""))
        st.caption(AI_SOURCE)

    st.divider()

    # ------------------------------------------------------------
    # 3. 차트 (레이블 및 단위 한국어화 적용)
    # ------------------------------------------------------------
    left, right = st.columns(2)

    # 3-1. 주별 결제 전환율 (플랫폼별)
    wp = f.groupby(["주시작일", "플랫폼"])[["결제시작세션", "주문세션"]].sum().reset_index()
    wp["결제전환율"] = (wp["주문세션"] / wp["결제시작세션"] * 100).round(1)
    fig1 = px.line(
        wp, x="주시작일", y="결제전환율", color="플랫폼", markers=True,
        title="주별 결제 전환율 (플랫폼별)",
        labels={"주시작일": "주 시작일", "결제전환율": "결제 전환율 (%)", "플랫폼": "플랫폼 구분"}
    )
    fig1.update_layout(yaxis_title="결제 전환율 (%)", xaxis_title="주 시작일")
    left.plotly_chart(fig1, width="stretch")

    # 3-2. 세션 퍼널
    steps = {"1.방문": "세션수", "2.식당조회": "조회세션", "3.장바구니": "장바구니세션",
             "4.결제시작": "결제시작세션", "5.주문완료": "주문세션"}
    fun = pd.DataFrame({"단계": list(steps), "세션수": [f[c].sum() for c in steps.values()]})
    fig2 = px.funnel(
        fun, x="세션수", y="단계", 
        title="세션 퍼널",
        labels={"세션수": "세션 수 (개)", "단계": "퍼널 단계"}
    )
    fig2.update_layout(xaxis_title="세션 수 (개)", yaxis_title="퍼널 단계")
    right.plotly_chart(fig2, width="stretch")

    # 3-3. 유입 경로별 주문 전환율
    ws = f.groupby("유입경로")[["세션수", "주문세션"]].sum().reset_index()
    ws["주문전환율"] = (ws["주문세션"] / ws["세션수"] * 100).round(1)
    ws = ws.sort_values("주문전환율")
    fig3 = px.bar(
        ws, x="주문전환율", y="유입경로", orientation="h", text_auto=".1f",
        hover_data={"세션수": True, "주문전환율": ":.1f%"}, 
        title="유입 경로별 주문 전환율",
        labels={"주문전환율": "주문 전환율 (%)", "유입경로": "유입 경로", "세션수": "세션 수 (개)"}
    )
    fig3.update_xaxes(range=[0, ws["주문전환율"].max() * 1.2])
    fig3.update_layout(xaxis_title="주문 전환율 (%)", yaxis_title="유입 경로")
    st.plotly_chart(fig3, width="stretch")

with tab_explore:
    st.caption("이 탭에서 볼 수 있는 것: 플랫폼 및 유입 경로별 집단 비교(누적 전환율 퍼널, 단계별 전환율 막대) 및 상세 드릴다운 분석, 집단별 AI 해설")

    # ------------------------------------------------------------
    # 4. 집단 비교 영역
    # ------------------------------------------------------------
    st.subheader("집단 비교")
    compare_by = st.radio("비교 기준", ["플랫폼", "유입경로"], horizontal=True)

    col_target = "플랫폼" if compare_by == "플랫폼" else "유입경로"

    # 집단별 퍼널 5단계 집계
    step_cols = {
        "1.방문": "세션수",
        "2.식당조회": "조회세션",
        "3.장바구니": "장바구니세션",
        "4.결제시작": "결제시작세션",
        "5.주문완료": "주문세션"
    }

    group_agg = f.groupby(col_target)[list(step_cols.values())].sum().reset_index()

    # 세션 수가 500개 미만인 집단 확인
    low_sample_groups = group_agg[group_agg["세션수"] < 500][col_target].tolist()
    if low_sample_groups:
        st.caption(f"⚠️ 경고: 다음 집단은 세션 수가 500개 미만으로 값이 크게 흔들릴 수 있습니다: {', '.join(low_sample_groups)}")

    # 체크박스 옵션에 따른 집단 필터링 처리
    if exclude_low_sample and low_sample_groups:
        filtered_group_agg = group_agg[~group_agg[col_target].isin(low_sample_groups)]
        st.caption(f"제외한 집단: {', '.join(low_sample_groups)} (세션 500개 미만)")
    else:
        filtered_group_agg = group_agg

    # 누적 전환율 퍼널용 데이터 변환 (첫 단계(세션수) 대비 %)
    cum_rows = []
    for _, row in filtered_group_agg.iterrows():
        group_name = row[col_target]
        base_val = row["세션수"]
        for step_name, col_name in step_cols.items():
            val = row[col_name]
            cum_rate = (val / base_val * 100) if base_val > 0 else 0
            cum_rows.append({
                col_target: group_name,
                "단계": step_name,
                "누적전환율": round(cum_rate, 1),
                "세션수": val,
                "기준세션": base_val
            })
    df_cum = pd.DataFrame(cum_rows)

    # 단계 전환율 막대용 데이터 변환 (직전 단계 대비 %)
    step_names = list(step_cols.keys())
    step_col_keys = list(step_cols.values())

    step_rows = []
    for _, row in filtered_group_agg.iterrows():
        group_name = row[col_target]
        for i in range(1, len(step_names)):
            curr_step_name = step_names[i]
            curr_col = step_col_keys[i]
            prev_col = step_col_keys[i - 1]
            
            curr_val = row[curr_col]
            prev_val = row[prev_col]
            step_rate = (curr_val / prev_val * 100) if prev_val > 0 else 0
            
            step_rows.append({
                col_target: group_name,
                "단계": curr_step_name,
                "단계전환율": round(step_rate, 1),
                "현재세션수": curr_val,
                "직전단계세션수": prev_val
            })
    df_step = pd.DataFrame(step_rows)

    # 좌우 레이아웃 구성
    comp_left, comp_right = st.columns(2)

    # 왼쪽: 누적 전환율 퍼널 (px.funnel)
    fig_comp_funnel = px.funnel(
        df_cum,
        x="누적전환율",
        y="단계",
        color=col_target,
        text="누적전환율",
        hover_data={"세션수": True, "누적전환율": ":.1f%", "기준세션": True},
        title=f"집단별 누적 전환율 퍼널 ({compare_by} 기준)",
        labels={"누적전환율": "누적 전환율 (%)", "단계": "퍼널 단계", col_target: f"{compare_by} 구분", "세션수": "현재 세션 수 (개)", "기준세션": "기준 세션 수(방문)(개)"}
    )
    fig_comp_funnel.update_traces(texttemplate="%{text:.1f}%", textposition="inside")
    fig_comp_funnel.update_layout(xaxis_title="누적 전환율 (%)", yaxis_title="퍼널 단계")
    comp_left.plotly_chart(fig_comp_funnel, width="stretch")

    # 오른쪽: 단계 전환율 막대 (barmode="group")
    fig_comp_bar = px.bar(
        df_step,
        x="단계",
        y="단계전환율",
        color=col_target,
        barmode="group",
        text="단계전환율",
        hover_data={"직전단계세션수": True, "현재세션수": True, "단계전환율": ":.1f%"},
        title=f"집단별 단계 전환율 ({compare_by} 기준)",
        labels={"단계전환율": "단계 전환율 (%)", "단계": "전환 단계", col_target: f"{compare_by} 구분", "직전단계세션수": "직전 단계 세션 수 (개)", "현재세션수": "현재 세션 수 (개)"}
    )
    fig_comp_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_comp_bar.update_layout(yaxis_title="단계 전환율 (%)", xaxis_title="전환 단계")
    comp_right.plotly_chart(fig_comp_bar, width="stretch")

    st.divider()

    # ------------------------------------------------------------
    # 5. 드릴다운 영역: 언제부터, 무엇 때문일까
    # ------------------------------------------------------------
    st.subheader("드릴다운: 언제부터, 무엇 때문일까")

    # 선택 가능한 집단 목록 (고급 설정 체크 여부에 따라 500개 미만 집단 제외)
    base_available_groups = sorted(f[col_target].unique())
    if exclude_low_sample and low_sample_groups:
        available_groups = [g_name for g_name in base_available_groups if g_name not in low_sample_groups]
        if not available_groups:
            available_groups = base_available_groups  # 모두 제외되어 비는 경우 방지
    else:
        available_groups = base_available_groups

    dd_col1, dd_col2 = st.columns(2)
    with dd_col1:
        selected_group = st.selectbox("자세히 볼 집단", available_groups)
    with dd_col2:
        selected_step = st.selectbox(
            "단계",
            [
                "방문 → 식당조회",
                "식당조회 → 장바구니",
                "장바구니 → 결제시작",
                "결제시작 → 주문"
            ]
        )

    # 단계 매핑 설정 (직전 컬럼, 현재 컬럼)
    step_mapping = {
        "방문 → 식당조회": ("세션수", "조회세션"),
        "식당조회 → 장바구니": ("조회세션", "장바구니세션"),
        "장바구니 → 결제시작": ("장바구니세션", "결제시작세션"),
        "결제시작 → 주문": ("결제시작세션", "주문세션")
    }
    prev_col_key, curr_col_key = step_mapping[selected_step]

    # 다른 축 결정 (플랫폼이면 유입경로, 유입경로면 플랫폼)
    other_col = "유입경로" if col_target == "플랫폼" else "플랫폼"

    # 차트 ① 데이터 준비: 고른 집단만 필터링한 후, 다른 축별로 주별 집계
    df_drill_target = f[f[col_target] == selected_group]
    weekly_other = df_drill_target.groupby(["주시작일", other_col])[[prev_col_key, curr_col_key]].sum().reset_index()

    # 직전 단계 세션이 0인 주는 0%로 채우지 않고 빈 값(NaN)으로 두기
    weekly_other["전환율"] = weekly_other.apply(
        lambda row: (row[curr_col_key] / row[prev_col_key] * 100) if row[prev_col_key] > 0 else float('nan'),
        axis=1
    )

    fig_drill1 = px.line(
        weekly_other,
        x="주시작일",
        y="전환율",
        color=other_col,
        markers=True,
        title=f"① {selected_group}의 주별 {selected_step} 전환율 — {other_col}별로 쪼개 보기",
        labels={"주시작일": "주 시작일", "전환율": "전환율 (%)", other_col: f"{other_col} 구분"}
    )
    fig_drill1.update_layout(yaxis_title="전환율 (%)", xaxis_title="주 시작일")
    st.plotly_chart(fig_drill1, width="stretch")
    st.caption("모든 갈래가 같은 시점에 함께 움직였다면, 그 축은 원인이 아닙니다.")

    # 차트 ② 데이터 준비: 결제실패 건수를 주별 막대로, 고른 집단(진한 빨간색) vs 그 외(회색)
    # 원본 f에서 전체 주별 집계를 위해 '그룹 구분' 컬럼 생성
    f_copy = f.copy()
    f_copy["집단구분"] = f_copy[col_target].apply(lambda x: selected_group if x == selected_group else "그 외 집단")

    weekly_fail = f_copy.groupby(["주시작일", "집단구분"])["결제실패"].sum().reset_index()

    # 색상 매핑 (고른 집단: 진한 빨간색, 그 외 집단: 회색)
    color_map = {
        selected_group: "#D32F2F",  # 진한 빨간색
        "그 외 집단": "#B0B0B0"      # 회색
    }

    fig_drill2 = px.bar(
        weekly_fail,
        x="주시작일",
        y="결제실패",
        color="집단구분",
        barmode="group",
        color_discrete_map=color_map,
        title=f"주별 결제실패 건수 ({selected_group} vs 그 외 집단)",
        labels={"주시작일": "주 시작일", "결제실패": "결제 실패 건수 (건)", "집단구분": "집단 구분"}
    )
    fig_drill2.update_layout(yaxis_title="결제 실패 건수 (건)", xaxis_title="주 시작일")
    st.plotly_chart(fig_drill2, width="stretch")
    st.caption("문제가 생긴 시점과 함께 움직였다면 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

    # 2. 드릴다운 차트 아래에 선택된 집단(target)별 AI 해설 추가
    with st.expander(f"🤖 AI 해설 · {selected_group}", expanded=False):
        note_text = AI_NOTES.get(selected_group, "이 집단의 해설은 아직 없습니다.")
        st.write(note_text)
        st.caption(AI_SOURCE)

with tab_action:
    st.caption("측정 KPI의 현재 값은 선택한 기간의 마지막 4주로 계산합니다")

    # 사이드바 기간만 적용하고 플랫폼/유입경로 필터는 무시한 원본 기반 데이터 추출
    df_period_only = df[(df["주시작일"] >= start) & (df["주시작일"] <= end)]
    
    # 선택된 기간의 마지막 4주 데이터 구하기
    period_weeks = sorted(df_period_only["주시작일"].unique())
    if len(period_weeks) >= 4:
        last_4_weeks = period_weeks[-4:]
        df_last4_base = df_period_only[df_period_only["주시작일"].isin(last_4_weeks)]
    else:
        df_last4_base = df_period_only  (-4주 미만인 경우 전체 선택 기간 기준)

    # 카드 1 KPI 계산: 플랫폼이 Android인 데이터의 결제 전환율 (주문세션 ÷ 결제시작세션)
    df_card1 = df_last4_base[df_last4_base["platform"] == "Android"]
    if not df_card1.empty:
        sum_card1 = df_last4_base[df_last4_base["플랫폼"] == "Android"][["결제시작세션", "주문세션"]].sum()
        val_card1 = (sum_card1["주문세션"] / sum_card1["결제시작세션"] * 100) if sum_card1["결제시작세션"] > 0 else 0
        metric_str_card1 = f"{val_card1:.1f}%" if sum_card1["결제시작세션"] > 0 else "데이터 없음"
    else:
        metric_str_card1 = "데이터 없음"

    # 카드 2 KPI 계산: 유입경로가 push인 데이터의 방문 → 식당 조회 전환율 (조회세션 ÷ 세션수)
    df_card2 = df_last4_base[df_last4_base["유입경로"] == "push"]
    if not df_card2.empty:
        sum_card2 = df_card2[["세션수", "조회세션"]].sum()
        val_card2 = (sum_card2["조회세션"] / sum_card2["세션수"] * 100) if sum_card2["세션수"] > 0 else 0
        metric_str_card2 = f"{val_card2:.1f}%" if sum_card2["세션수"] > 0 else "데이터 없음"
    else:
        metric_str_card2 = "데이터 없음"

    col_action1, col_action2 = st.columns(2)

    with col_action1:
        with st.container(border=True):
            st.markdown("""
            **카드 1 · Android 결제**
            - 문제: 결제 시작 → 주문 전환율이 2026-04-13 주부터 하락해 최저 41.4%(5/18 주), 6/1 주부터 회복
            - 근거: 같은 기간 iOS는 평소 범위 안 · Android 결제 실패가 주 4건 이하 → 최대 153건
            - 성격: 특정 시점에 생긴 문제
            - 액션: 추가 분석: 앱 버전별로 결제 실패 확인 → 재발 감시: 결제 전환율이 평소 범위를 벗어나는지 매주 점검
            - 우선순위: 영향 큼 · 실행 쉬움 → 바로 실행
            """)
            st.metric("Android 결제 전환율 (마지막 4주)", metric_str_card1)
            st.caption("대시보드에서: 개요 탭 규칙 문장(플랫폼 Android) · 탐색 탭 드릴다운")

    with col_action2:
        with st.container(border=True):
            st.markdown("""
            **카드 2 · push 방문**
            - 문제: 방문 → 식당 조회 전환율 28.4% (다른 경로 57~69%), 주문 전환율 3.2%
            - 근거: 2026년 2월부터 세션의 30~36%가 push · 기간 내내 25~35%
            - 성격: 처음부터 그런 구조
            - 액션: 실험: 일부 사용자에게만 푸시 대상과 문구를 바꿔 방문 → 식당 조회 전환율 비교
            - 우선순위: 효과 불확실 · 실행 쉬움 → 실험부터
            """)
            st.metric("push 방문 → 식당 조회 전환율 (마지막 4주)", metric_str_card2)
            st.caption("대시보드에서: 탐색 탭 비교 기준 '유입경로' · 드릴다운 push")
