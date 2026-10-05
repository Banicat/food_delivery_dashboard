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
# 1. 데이터 준비 — data 폴더의 원본 CSV 4개를 메모리 DB에 올리고 SQL로 집계
# ------------------------------------------------------------
DATA_DIR = "data"                         # 원본 CSV를 넣어 둔 폴더
TABLES = ["app_events", "orders", "customers", "restaurants"]

@st.cache_resource
def get_db():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for name in TABLES:
        pd.read_csv(f"{DATA_DIR}/{name}.csv").to_sql(name, con, index=False)
    return con

@st.cache_data
def query(sql):
    return pd.read_sql(sql, get_db())

# 주 × 플랫폼 × 유입 경로별 세션 퍼널 (QA 계정 제외, 중복 이벤트 제거)
SQL_WEEKLY_FUNNEL = """
WITH e AS (
    SELECT *
      FROM (SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY session_id, event_datetime, event_name
                                      ORDER BY event_id) AS dup
              FROM app_events
             WHERE customer_id NOT LIKE 'QA%')
     WHERE dup = 1
), s AS (                                   -- 세션의 첫 이벤트로 플랫폼 · 유입 경로 · 주 정하기
    SELECT session_id, platform, traffic_source,
           DATE(MIN(event_datetime), 'weekday 0', '-6 days') AS 주시작일
      FROM e
     GROUP BY session_id
)
SELECT s.주시작일,
       s.platform       AS 플랫폼,
       s.traffic_source AS 유입경로,
       COUNT(DISTINCT e.session_id)                                                              AS 세션수,
       COUNT(DISTINCT CASE WHEN e.event_name = 'view_restaurant' THEN e.session_id END)   AS 조회세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'add_to_cart'      THEN e.session_id END)   AS 장바구니세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'begin_checkout'   THEN e.session_id END)   AS 결제시작세션,
       COUNT(DISTINCT CASE WHEN e.event_name = 'order_complete'   THEN e.session_id END)   AS 주문세션,
       SUM(CASE WHEN e.event_name = 'payment_fail' THEN 1 ELSE 0 END)                      AS 결제실패
  FROM e
  JOIN s ON e.session_id = s.session_id
 WHERE s.주시작일 < '2026-06-29'           -- 이틀치뿐인 마지막 주 제외
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

@st.cache_data
def load_data():
    data = query(SQL_WEEKLY_FUNNEL)
    data["주시작일"] = pd.to_datetime(data["주시작일"]).dt.date
    return data

df = load_data()

st.sidebar.header("필터")

# 기간: 주 시작일 목록에서 범위 고르기
weeks = sorted(df["주시작일"].unique())
start, end = st.sidebar.select_slider("기간 (주 시작일)", options=weeks, value=(weeks[0], weeks[-1]))

# 플랫폼 · 유입 경로: 여러 개 고르기 (처음엔 전부 선택)
platforms = sorted(df["플랫폼"].unique())
sel_platform = st.sidebar.multiselect("플랫폼", platforms, default=platforms)
sources = sorted(df["유입경로"].unique())
sel_source = st.sidebar.multiselect("유입 경로", sources, default=sources)

f = df[(df["주시작일"] >= start) & (df["주시작일"] <= end)
       & df["플랫폼"].isin(sel_platform) & df["유입경로"].isin(sel_source)]

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
group_col_label = st.radio("비교 기준", ["플랫폼", "유입경로"], horizontal=True)
group_col = "플랫폼" if group_col_label == "플랫폼" else "유입경로"

# 집단별 5단계 집계
step_cols = ["세션수", "조회세션", "장바구니세션", "결제시작세션", "주문세션"]
step_names = ["1.방문", "2.식당조회", "3.장바구니", "4.결제시작", "5.주문완료"]
col_mapping = dict(zip(step_names, step_cols))

grouped = f.groupby(group_col)[step_cols].sum().reset_index()

# 세션 수가 500개 미만인 집단 안내
low_session_groups = grouped[grouped["세션수"] < 500][group_col].tolist()
if low_session_groups:
    st.caption(f"⚠️ 경고: {', '.join(low_session_groups)} 집단의 세션 수가 500개 미만으로 값이 크게 흔들릴 수 있습니다.")

# 왼쪽: 누적 퍼널 데이터프레임 변환 (Wide -> Long)
melted_cum = grouped.melt(
    id_vars=[group_col],
    value_vars=step_cols,
    var_name="단계_원래명",
    value_name="값"
)
melted_cum.rename(columns={"값": "세션수"}, inplace=True)

# 단계 이름 매핑
reverse_steps = {v: k for k, v in steps.items()}
melted_cum["단계"] = melted_cum["단계_원래명"].map(reverse_steps)

# 오른쪽: 단계 전환율(직전 단계 대비 %) 계산
step_pairs = [
    ("2.식당조회", "1.방문", "조회세션", "세션수"),
    ("3.장바구니", "2.식당조회", "장바구니세션", "조회세션"),
    ("4.결제시작", "3.장바구니", "결제시작세션", "장바구니세션"),
    ("5.주문완료", "4.결제시작", "주문세션", "결제시작세션")
]

step_rates_list = []
for cur_name, prev_name, cur_col, prev_col in step_pairs:
    temp = grouped[[group_col, cur_col, prev_col]].copy()
    temp["단계"] = cur_name
    temp["기준세션"] = temp[prev_col]
    temp["단계전환율"] = (temp[cur_col] / temp[prev_col] * 100).round(1)
    # 분모가 0인 경우 처리
    temp["단계전환율"] = temp["단계전환율"].fillna(0)
    step_rates_list.append(temp[[group_col, "단계", "단계전환율", "기준세션"]])

step_rates_df = pd.concat(step_rates_list, ignore_index=True)

comp_left, comp_right = st.columns(2)

# 4-1. 왼쪽: 누적 전환율 퍼널 (px.funnel)
fig_funnel = px.funnel(
    melted_cum,
    x="세션수",
    y="단계",
    color=group_col,
    title=f"집단별 누적 퍼널 ({group_col_label} 기준)"
)
comp_left.plotly_chart(fig_funnel, width="stretch")

# 4-2. 오른쪽: 단계 전환율 막대 (barmode="group")
fig_bar = px.bar(
    step_rates_df,
    x="단계",
    y="단계전환율",
    color=group_col,
    barmode="group",
    text="단계전환율",
    hover_data=["기준세션"],
    title=f"집단별 단계 전환율 ({group_col_label} 기준)"
)
fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
fig_bar.update_layout(yaxis_title="단계 전환율 (%)", xaxis_title="")
comp_right.plotly_chart(fig_bar, width="stretch")

st.divider()

# ------------------------------------------------------------
# 5. 드릴다운: 언제부터, 무엇 때문일까 영역
# ------------------------------------------------------------
st.subheader("드릴다운: 언제부터, 무엇 때문일까")

d1, d2 = st.columns(2)

# 5-1. selectbox 2개 배치
available_groups = sorted(f[group_col].unique())
selected_drill_group = d1.selectbox("자세히 볼 집단", available_groups)

step_options = ["방문 → 식당조회", "식당조회 → 장바구니", "장바구니 → 결제시작", "결제시작 → 주문"]
selected_step_label = d2.selectbox("단계", step_options)

# 단계 매핑 설정 (분자, 분모 열 정의)
step_mapping_dict = {
    "방문 → 식당조회": ("조회세션", "세션수"),
    "식당조회 → 장바구니": ("장바구니세션", "조회세션"),
    "장바구니 → 결제시작": ("결제시작세션", "장바구니세션"),
    "결제시작 → 주문": ("주문세션", "결제시작세션")
}
num_col, den_col = step_mapping_dict[selected_step_label]

# 다른 축 설정
other_col = "유입경로" if group_col == "플랫폼" else "플랫폼"

# 차트 ① 데이터 처리: 고른 집단만 남긴 뒤 다른 축으로 쪼개어 주별 전환율 계산
f_drill = f[f[group_col] == selected_drill_group]
wp_drill = f_drill.groupby(["주시작일", other_col])[[num_col, den_col]].sum().reset_index()
wp_drill["전환율"] = (wp_drill[num_col] / wp_drill[den_col] * 100).round(1)
wp_drill["전환율"] = wp_drill["전환율"].fillna(0)

fig_drill_1 = px.line(
    wp_drill,
    x="주시작일",
    y="전환율",
    color=other_col,
    markers=True,
    title=f"① {selected_drill_group}의 주별 {selected_step_label} 전환율 — {other_col}별로 쪼개 보기"
)
fig_drill_1.update_layout(yaxis_title="전환율 (%)", xaxis_title="")
st.plotly_chart(fig_drill_1, width="stretch")
st.caption("모든 갈래가 같은 시점에 함께 움직였다면, 그 축은 원인이 아닙니다.")

# 차트 ② 데이터 처리: 같은 기간 결제실패 건수를 주별 막대로 (고른 집단 vs 그 외)
# f 전체에서 주시작일별로 그룹화하되, 고른 집단 여부(타겟 vs 그 외)를 추가
f_fail = f.copy()
f_fail["그룹구분"] = f_fail[group_col].apply(lambda x: selected_drill_group if x == selected_drill_group else "그 외")

fail_grouped = f_fail.groupby(["주시작일", "그룹구분"])["결제실패"].sum().reset_index()

# 색상 매핑 설정 (고른 집단: 진한 빨간색, 그 외: 회색)
color_map = {selected_drill_group: "#d62728", "그 외": "#bcbd22"} # 또는 적절한 회색 (#7f7f7f 등)
# 보편적인 회색 적용을 위해 color_discrete_map 사용
color_map = {selected_drill_group: "crimson", "그 외": "lightgray"}

fig_drill_2 = px.bar(
    fail_grouped,
    x="주시작일",
    y="결제실패",
    color="그룹구분",
    barmode="group",
    color_discrete_map=color_map,
    title=f"주별 결제실패 건수 비교 ({selected_drill_group} vs 그 외)"
)
fig_drill_2.update_layout(yaxis_title="결제실패 건수", xaxis_title="")
st.plotly_chart(fig_drill_2, width="stretch")
st.caption("문제가 생긴 시점과 함께 움직였다면 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")
