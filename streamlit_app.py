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
       s.platform         AS 플랫폼,
       s.traffic_source AS 유입경로,
       COUNT(DISTINCT e.session_id)                                                                     AS 세션수,
       COUNT(DISTINCT CASE WHEN e.event_name = 'view_restaurant' THEN e.session_id END)   AS 조회세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'add_to_cart'     THEN e.session_id END)   AS 장바구니세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'begin_checkout'  THEN e.session_id END)   AS 결제시작세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'order_complete'  THEN e.session_id END)   AS 주문세션,
       SUM(CASE WHEN e.event_name = 'payment_fail' THEN 1 ELSE 0 END)                     AS 결제실패
  FROM events e
  JOIN s ON e.session_id = s.session_id
 WHERE s.주시작일 < '2026-06-29'             -- 이틀치뿐인 마지막 주 제외
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

@st.cache_data
def load_data():
    data = query(SQL_WEEKLY_FUNNEL)
    data["주시작일"] = pd.to_datetime(data["주시작일"]).dt.date
    return data

df = load_data()                                          # 주 × 플랫폼 × 유입 경로별 세션 퍼널

AI_NOTES = {
    "전체": "전체 28,840세션 중 주문세션은 4,178건으로 14.49%의 주문 전환율을 기록했다. 퍼널 단계 중 조회에서 장바구니로 넘어갈 때(41.41%) 가장 큰 이탈이 발생한 것으로 보인다. 2025년 6월 말부터 2026년 6월 말까지 전체 기간에 걸쳐 데이터가 집계되었다.",
    "Android": "총 16,053세션으로 전체의 55.66%를 차지하며, 주문 전환율은 14.26%로 전체 평균(14.49%)과 유사하다. 결제실패 이벤트가 881건 발생하여 전체 결제실패(913건)의 대부분을 차지했다. 전체 기간 동안 꾸준한 유입 규모를 유지한 것으로 보인다.",
    "iOS": "총 12,787세션으로 전체의 44.34%를 차지하며, 주문 전환율은 14.77%로 Android(14.26%)와 유사한 수준이다. 결제실패 이벤트가 32건으로 Android(881건)에 비해 매우 적게 집계되었다. 전체 기간 동안 안정적인 트래픽 흐름을 보였다.",
    "organic": "총 22,489세션으로 전체 유입경로 중 가장 큰 비중을 차지하며, 주문 전환율은 16.05%로 전체 평균(14.49%)보다 높다. 조회세션 비율이 68.53%로 타 채널 대비 높게 나타났다. 전체 기간 동안 핵심 유입 채널 역할을 한 것으로 보인다.",
    "paid_ad": "총 1,595세션으로 집단 크기가 상대적으로 작지만, 주문 전환율은 26.27%로 전체 평균(14.49%)을 크게 상회한다. 장바구니에서 결제시작으로의 전환율이 81.12%로 다른 채널 대비 높았다. 전체 기간 동안 소규모 유입이지만 높은 효율을 보인 것으로 보인다.",
    "push": "총 4,635세션이며, 주문 전환율은 3.24%로 전체 평균(14.49%) 및 타 채널 대비 낮다. 조회세션 전환율이 28.37%로 상세 조회로 이어지는 비율이 상대적으로 저조했다. 2026년 2월 이후부터 데이터가 새롭게 집계되기 시작했다.",
    "referral": "총 121세션으로 집단 크기가 매우 작으며, 주문세션이 0건으로 주문 전환율이 0%이다. 결제시작세션이 4건에 불과하고 최종 주문으로 이어지지 않아 전환 효율이 극히 저조하다. 전체 기간 중 간헐적으로 소수 유입만 발생한 것으로 보인다."
}
AI_SOURCE = "🤖 Gemini가 미리 만든 해설 · 전체 기간 기준"


st.sidebar.header("필터")

# 기간: 주 시작일 목록에서 범위 고르기
weeks = sorted(df["주시작일"].unique())
start, end = st.sidebar.select_slider("기간 (주 시작일)", options=weeks, value=(weeks[0], weeks[-1]))

# 플랫폼 · 유입 경로: 여러 개 고르기 (처음엔 전부 선택)
platforms = sorted(df["플랫폼"].unique())
sel_platform = st.sidebar.multiselect("플랫폼", platforms, default=platforms)
sources = sorted(df["유입경로"].unique())
sel_source = st.sidebar.multiselect("유입 경로", sources, default=sources)

# 평소 범위 기준 기간 추가
default_baseline_end_idx = min(25, len(weeks) - 1)
baseline_start, baseline_end = st.sidebar.select_slider(
    "평소 범위 기준 기간",
    options=weeks,
    value=(weeks[0], weeks[default_baseline_end_idx]),
    help="문제가 없던 기간을 고르세요. 이 기간의 주별 값 범위를 '평소 범위'로 씁니다."
)

# 집단 조건(플랫폼·유입경로)만 적용한 데이터 g 생성
g = df[df["플랫폼"].isin(sel_platform) & df["유입경로"].isin(sel_source)]

# 기존 f는 g에 기간 조건을 더해 만듦
f = g[(g["주시작일"] >= start) & (g["주시작일"] <= end)]

if f.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 바꿔 주세요.")
    st.stop()    # 여기서 화면 그리기를 멈춤

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
# 선택된 기간의 주 목록 및 개수 확인
selected_weeks = sorted(f["주시작일"].unique())
num_selected_weeks = len(selected_weeks)

# 기준 기간의 데이터 추출 및 주별 집계 (g 기준)
g_baseline = g[(g["주시작일"] >= baseline_start) & (g["주시작일"] <= baseline_end)]
baseline_weekly = g_baseline.groupby("주시작일")[["세션수", "결제시작세션", "주문세션"]].sum().reset_index()
num_baseline_weeks = len(baseline_weekly)

# 이번 값 계산용 (마지막 4주 합계)
if num_selected_weeks >= 4:
    last_4_weeks_dates = selected_weeks[-4:]
    f_last4 = f[f["주시작일"].isin(last_4_weeks_dates)]
    t_last4 = f_last4[["세션수", "결제시작세션", "주문세션"]].sum()
    
    current_order_rate = rate(t_last4["주문세션"], t_last4["세션수"])
    current_payment_rate = rate(t_last4["주문세션"], t_last4["결제시작세션"])
    period_str = f"{last_4_weeks_dates[0]} 주부터 4주"
else:
    period_str = ""

# 평소 범위 계산 (기준 기간의 주별 전환율 최솟값 ~ 최댓값)
if num_baseline_weeks > 0:
    baseline_weekly["주문전환율"] = baseline_weekly.apply(lambda r: rate(r["주문세션"], r["세션수"]), axis=1)
    baseline_weekly["결제전환율"] = baseline_weekly.apply(lambda r: rate(r["주문세션"], r["결제시작세션"]), axis=1)
    
    order_min, order_max = baseline_weekly["주문전환율"].min(), baseline_weekly["주문전환율"].max()
    payment_min, payment_max = baseline_weekly["결제전환율"].min(), baseline_weekly["결제전환율"].max()
else:
    order_min, order_max = 0, 0
    payment_min, payment_max = 0, 0

# 1) 결제 전환율 설명 문장 생성
if num_selected_weeks < 4:
    pay_msg = "결제 전환율 설명: 선택 기간이 4주 미만이어야 하는 조건에 못 미치거나 데이터가 부족하여 이번 값(마지막 4주 합계)을 계산할 수 없습니다."
elif num_baseline_weeks < 4:
    pay_msg = "결제 전환율 설명: 기준 기간의 데이터가 4주 미만이어야 하는 조건에 못 미치거나 데이터가 부족하여 평소 범위를 산출할 수 없습니다."
else:
    diff_p_pay = current_payment_rate - payment_max
    diff_m_pay = payment_min - current_payment_rate
    if current_payment_rate < payment_min:
        pay_msg = f"결제 전환율 ({period_str})은 이번 값이 {current_payment_rate:.1f}%로, 평소 범위({payment_min:.1f}% ~ {payment_max:.1f}%)보다 {diff_m_pay:.1f}%p 낮습니다."
    elif current_payment_rate > payment_max:
        pay_msg = f"결제 전환율 ({period_str})은 이번 값이 {current_payment_rate:.1f}%로, 평소 범위({payment_min:.1f}% ~ {payment_max:.1f}%)보다 {diff_p_pay:.1f}%p 높습니다."
    else:
        pay_msg = f"결제 전환율 ({period_str})은 이번 값이 {current_payment_rate:.1f}%로, 평소 범위({payment_min:.1f}% ~ {payment_max:.1f}%) 안에 있습니다."

# 2) 주문 전환율 설명 문장 생성
if num_selected_weeks < 4:
    ord_msg = "주문 전환율 설명: 선택 기간이 4주 미만이어야 하는 조건에 못 미치거나 데이터가 부족하여 이번 값(마지막 4주 합계)을 계산할 수 없습니다."
elif num_baseline_weeks < 4:
    ord_msg = "주문 전환율 설명: 기준 기간의 데이터가 4주 미만이어야 하는 조건에 못 미치거나 데이터가 부족하여 평소 범위를 산출할 수 없습니다."
else:
    diff_p_ord = current_order_rate - order_max
    diff_m_ord = order_min - current_order_rate
    if current_order_rate < order_min:
        ord_msg = f"주문 전환율 ({period_str})은 이번 값이 {current_order_rate:.1f}%로, 평소 범위({order_min:.1f}% ~ {order_max:.1f}%)보다 {diff_m_ord:.1f}%p 낮습니다."
    elif current_order_rate > order_max:
        ord_msg = f"주문 전환율 ({period_str})은 이번 값이 {current_order_rate:.1f}%로, 평소 범위({order_min:.1f}% ~ {order_max:.1f}%)보다 {diff_p_ord:.1f}%p 높습니다."
    else:
        ord_msg = f"주문 전환율 ({period_str})은 이번 값이 {current_order_rate:.1f}%로, 평소 범위({order_min:.1f}% ~ {order_max:.1f}%) 안에 있습니다."

st.info(f"{pay_msg}\n\n{ord_msg}")
st.caption(f"📏 자동 계산 · 평소 범위 기준 기간 {baseline_start} ~ {baseline_end} (주별 값)")

with st.expander("🤖 AI 해설 · 전체", expanded=False):
    st.write(AI_NOTES.get("전체", "이 집단의 해설은 아직 없습니다."))
st.caption(AI_SOURCE)

st.divider()

# ------------------------------------------------------------
# 3. 차트
# ------------------------------------------------------------
left, right = st.columns(2)

# 3-1. 주별 결제 전환율 (플랫폼별)
wp = f.groupby(["주시작일", "플랫폼"])[["결제시작세션", "주문세션"]].sum().reset_index()
wp["결제전환율"] = (wp["주문세션"] / wp["결제시작세션"] * 100).round(1)
fig1 = px.line(wp, x="주시작일", y="결제전환율", color="플랫폼", markers=True,
               title="주별 결제 전환율 (플랫폼별)")
fig1.update_layout(yaxis_title="결제 전환율 (%)", xaxis_title="")
left.plotly_chart(fig1, width="stretch")

# 3-2. 세션 퍼널
steps = {"1.방문": "세션수", "2.식당조회": "조회세션", "3.장바구니": "장바구니세션",
         "4.결제시작": "결제시작세션", "5.주문완료": "주문세션"}
fun = pd.DataFrame({"단계": list(steps), "세션수": [f[c].sum() for c in steps.values()]})
fig2 = px.funnel(fun, x="세션수", y="단계", title="세션 퍼널")
right.plotly_chart(fig2, width="stretch")

# 3-3. 유입 경로별 주문 전환율
ws = f.groupby("유입경로")[["세션수", "주문세션"]].sum().reset_index()
ws["주문전환율"] = (ws["주문세션"] / ws["세션수"] * 100).round(1)
ws = ws.sort_values("주문전환율")
fig3 = px.bar(ws, x="주문전환율", y="유입경로", orientation="h", text_auto=".1f",
              hover_data=["세션수"], title="유입 경로별 주문 전환율")
fig3.update_xaxes(range=[0, ws["주문전환율"].max() * 1.2])
fig3.update_layout(xaxis_title="주문 전환율 (%)", yaxis_title="")
st.plotly_chart(fig3, width="stretch")

st.divider()

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

# 누적 전환율 퍼널용 데이터 변환 (첫 단계(세션수) 대비 %)
cum_rows = []
for _, row in group_agg.iterrows():
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
for _, row in group_agg.iterrows():
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
    hover_data=["세션수"],
    title=f"집단별 누적 전환율 퍼널 ({compare_by} 기준)"
)
fig_comp_funnel.update_traces(texttemplate="%{text:.1f}%", textposition="inside")
fig_comp_funnel.update_layout(xaxis_title="누적 전환율 (%)", yaxis_title="")
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
    title=f"집단별 단계 전환율 ({compare_by} 기준)"
)
fig_comp_bar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_comp_bar.update_layout(yaxis_title="단계 전환율 (%)", xaxis_title="")
comp_right.plotly_chart(fig_comp_bar, width="stretch")

st.divider()

# ------------------------------------------------------------
# 5. 드릴다운 영역: 언제부터, 무엇 때문일까
# ------------------------------------------------------------
st.subheader("드릴다운: 언제부터, 무엇 때문일까")

# f에 존재하는 해당 기준의 값만 추출
available_groups = sorted(f[col_target].unique())

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
    title=f"① {selected_group}의 주별 {selected_step} 전환율 — {other_col}별로 쪼개 보기"
)
fig_drill1.update_layout(yaxis_title="전환율 (%)", xaxis_title="")
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
    "그 외 집단": "#B0B0B0"     # 회색
}

fig_drill2 = px.bar(
    weekly_fail,
    x="주시작일",
    y="결제실패",
    color="집단구분",
    barmode="group",
    color_discrete_map=color_map,
    title=f"주별 결제실패 건수 ({selected_group} vs 그 외 집단)"
)
fig_drill2.update_layout(yaxis_title="결제실패 건수", xaxis_title="")
st.plotly_chart(fig_drill2, width="stretch")
st.caption("문제가 생긴 시점과 함께 움직였다면 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

target = selected_group
with st.expander(f"🤖 AI 해설 · {target}", expanded=False):
    st.write(AI_NOTES.get(target, "이 집단의 해설은 아직 없습니다."))
st.caption(AI_SOURCE)
