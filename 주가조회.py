
from io import BytesIO
import re
import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import plotly.graph_objects as go
import feedparser
import urllib.parse 
import quote
from datetime import date
import datetime as dt


st.set_page_config(page_title="주가 조회 앱", layout="wide")
# ============================================================  

@st.cache_data(show_spinner=False, ttl=10 * 60)  # 뉴스는 10분 캐시 추천
def fetch_google_news_rss(query: str, hl: str = "ko", gl: str = "KR", ceid: str = "KR:ko", limit: int = 10):
    """
    Google News RSS에서 헤드라인 가져오기
    - query: 검색어 (예: "삼성전자", "삼성전자 주가", "018260")
    """
    q = quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:limit]:
        # published_parsed가 없을 수도 있어서 안전 처리
        published = ""
        if getattr(e, "published_parsed", None):
            published = dt(*e.published_parsed[:6]).strftime("%Y-%m-%d %H:%M")

        items.append({
            "title": e.title,
            "link": e.link,
            "source": getattr(getattr(e, "source", None), "title", ""),
            "published": published,
        })
    return items


def build_news_queries(company_name: str, stock_code: str):
    """
    검색 품질을 위해 쿼리를 2~3개로 시도
    """
    queries = [
        f"{company_name} 주가",
        f"{company_name} 실적",
        f"{company_name}",
    ]
    # 종목코드도 같이 넣고 싶으면(가끔 도움됨)
    if stock_code and stock_code.isdigit():
        queries.insert(1, f"{company_name} {stock_code}")
    return queries


# -------------------------
# 0단계: 종목코드 정규화/검증 (Yahoo 경로 차단하기 위하여 숫자 6글자만 허용)
# -------------------------
def normalize_and_validate_krx_code(code) -> str:
    s = str(code).strip()
    if not re.fullmatch(r"\d+", s):
        raise ValueError(
            "문자/기호가 포함된 종목코드는 지원하지 않습니다.\n"
            f"선택된 종목코드: {s}"
        )
    if len(s) > 6:
        raise ValueError(f"종목코드 길이가 6자리를 초과합니다: {s}")
    return s.zfill(6)


# -------------------------
# KRX 상장사 목록 로딩 (회사명 ↔ 종목코드)
# -------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60)  # krx 목록은 웹에서 가져올 때 검색할 때마다 새로 받음 -> 느림 -> 1시간동안 캐시해서 재사용 
def get_krx_company_list() -> pd.DataFrame:
    url = "http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
    df = pd.read_html(url, header=0, flavor="bs4", encoding="EUC-KR")[0]  # krx 자료가 euc-kr 인코딩임 
    df = df[["회사명", "종목코드"]].copy()
    df["종목코드"] = df["종목코드"].astype(str).str.strip()
    df = df[df["종목코드"].str.fullmatch(r"\d+", na=False)].copy()
    df["종목코드"] = df["종목코드"].str.zfill(6)  # 숫자코드만 남겨서 목록 품질 높임 
    return df


# -------------------------
# 유틸: MDD 값 계산
# -------------------------
def calc_mdd(close_series: pd.Series) -> float:
    """
    MDD(Max Drawdown) = (최저점 / 직전 고점) - 1 의 최소값
    예: -0.23 => -23% 최대 낙폭
    """
    running_max = close_series.cummax()   # cummax(): 누적 최대값(지금까지 최고가)를 계속 기록
    drawdown = close_series / running_max - 1.0 # 낙폭 계산 , 최고가 일 때 0, 그 이하로 내려가면 음수
    return float(drawdown.min())


# -------------------------
# 유틸: MDD 발생 구간(고점→저점) 찾기
# -------------------------
def find_mdd_period_iloc(close: pd.Series):
    """
    최대낙폭(MDD)이 발생한 '고점 위치(정수)'와 '저점 위치(정수)'를 반환
    반환: (peak_pos, trough_pos, mdd_value)
    - close는 index가 뭐든 상관없이 내부에서 0..N-1 기준으로 처리
    """
    s = close.reset_index(drop=True).astype(float)   # 무조건 0..N-1 새 인덱스부여

    running_max = s.cummax()
    drawdown = s / running_max - 1.0

    trough_pos = int(drawdown.idxmin())          # 저점의 '정수 위치'
    peak_pos = int(s.iloc[:trough_pos + 1].idxmax())  # 저점 이전 구간의 고점 '정수 위치'
    mdd_value = float(drawdown.iloc[trough_pos])

    return peak_pos, trough_pos, mdd_value



# -------------------------
# Figure에 MDD 구간 시각화 
# -------------------------
def add_mdd_highlight(
    fig: go.Figure,
    peak_date,
    trough_date,
    peak_price: float,
    trough_price: float,
    mdd_pct: float,
):
    # 1) 붉은 음영(고점→저점)
    fig.add_vrect(
        x0=peak_date, x1=trough_date,
        fillcolor="rgba(255, 0, 0, 0.10)",
        layer="below",
        line_width=0,
        annotation_text=f"MDD {mdd_pct:.2f}%",
        annotation_position="top left",
    )

    # 2) 고점/저점 마커
    fig.add_trace(go.Scatter(
        x=[peak_date],
        y=[peak_price],
        mode="markers+text",
        name="MDD Peak",
        text=[f"Peak<br>{peak_price:,.0f}"],
        textposition="top center",
        marker=dict(size=10, symbol="triangle-up"),
        cliponaxis=False,
        hovertemplate="<b>MDD Peak</b><br>%{x|%Y-%m-%d}<br>%{y:,.0f}<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=[trough_date],
        y=[trough_price],
        mode="markers+text",
        name="MDD Trough",
        text=[f"Trough<br>{trough_price:,.0f}"],
        textposition="bottom center",
        marker=dict(size=10, symbol="triangle-down"),
        cliponaxis=False,
        hovertemplate="<b>MDD Trough</b><br>%{x|%Y-%m-%d}<br>%{y:,.0f}<extra></extra>",
    ))


# ============================================================
# UI
# ============================================================
st.title("📊 주가 조회 ")

try:
    company_df = get_krx_company_list()
except Exception as e:
    st.error(f"상장사 명단 로딩 실패: {e}")
    st.stop()


# 왼쪽을 더 넓게(검색결과/선택 ui), 오른쪽을 좁게(옵션/기간 선택 ui)
left, right = st.columns([2, 1], vertical_alignment="top") 

with left:
    st.subheader("1) 회사 검색 & 선택")
    keyword = st.text_input("회사명을 검색하세요 (예: 삼성)", value="").strip()


# 삼성 검색하면 삼성전자 등 여러개 뜰 수 있음 -> startswith 우선 정렬
    if keyword:
        contains_df = company_df[company_df["회사명"].str.contains(keyword, na=False)].copy()
        starts_df = contains_df[contains_df["회사명"].str.startswith(keyword)].copy()
        rest_df = contains_df[~contains_df["회사명"].str.startswith(keyword)].copy()
        filtered = pd.concat([starts_df, rest_df], ignore_index=True)
    else:
        filtered = company_df.head(200).copy()

    if len(filtered) == 0:
        st.warning("검색 결과가 없습니다. 다른 키워드를 입력해보세요.")
        st.stop()

    filtered["표시"] = filtered["회사명"] + " (" + filtered["종목코드"] + ")"
    st.caption(f"검색 결과: {len(filtered)}개")
    picked = st.selectbox("조회할 회사를 선택하세요", options=filtered["표시"].tolist(), index=0)

    company_name = picked.split(" (")[0].strip()
    stock_code = picked.split("(")[-1].replace(")", "").strip()

with right:
    st.subheader("2) 옵션 & 기간")

    st.markdown("**차트 옵션**")
    show_close = st.checkbox("Close(종가)", value=True)
    show_ma20 = st.checkbox("MA20", value=True)
    show_ma60 = st.checkbox("MA60", value=False)
    show_vol = st.checkbox("Volume(거래량, 보조축)", value=False)

    st.markdown("**리스크 시각화(선택)**")
    show_mdd_zone = st.checkbox("MDD(최대낙폭) 구간 강조", value=True)

    st.markdown("**시각 효과(선택)**")
    use_animation = st.checkbox("Close 타임-플레이 애니메이션(가벼운 버전)", value=False)
   
    today = date.today()
    jan_1 = date(today.year, 1, 1)
    selected_dates = st.date_input(   #  date 기간 선택을 거꾸로 해도 st.date_input 이 자동으로 정렬함 
        "조회할 날짜를 입력하세요",
        (jan_1, today),
        format="MM.DD.YYYY",
    )

    confirm_btn = st.button("조회하기", type="primary")


# ============================================================
# 조회 로직
# ============================================================
if confirm_btn:
    try:
        with st.spinner("데이터를 수집하는 중..."):
            stock_code = normalize_and_validate_krx_code(stock_code)

            #  selected_dates가 1개(date)인지 2개(기간)인지 확실히 처리
            if isinstance(selected_dates, (tuple, list)):
                if len(selected_dates) != 2:
                    st.warning("기간 조회를 하려면 날짜를 2개(시작/종료) 선택해 주세요.")
                    st.stop()
                start_dt, end_dt = selected_dates
            else:
                st.warning("기간 조회를 하려면 날짜를 2개(시작/종료) 선택해 주세요.")
                st.stop()

            #  시작일 > 종료일이면 즉시 경고 : 메서드에서 정렬하지만 혹시 몰라 넣음 
            if start_dt > end_dt:
                st.warning("시작일이 종료일보다 늦습니다. 날짜를 다시 선택해 주세요.")
                st.stop()

            start_date = start_dt.strftime("%Y%m%d")
            end_date = end_dt.strftime("%Y%m%d")

            price_df = fdr.DataReader(stock_code, start_date, end_date)

        if price_df.empty:
            st.info("해당 기간의 주가 데이터가 없습니다.")
            st.stop()

        # Plotly x축용 date 컬럼 확보
        df = price_df.copy().reset_index()  # FDR 이 반환하는 index가 날짜임 -> date 컬럼으로 처리 
        if "Date" in df.columns:
            df.rename(columns={"Date": "date"}, inplace=True)
        elif "date" not in df.columns:
            df.rename(columns={df.columns[0]: "date"}, inplace=True)

        # MA 계산
        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA60"] = df["Close"].rolling(60).mean()

        # [가드] MA가 전부 NaN이면 자동 OFF + 안내
        if show_ma20 and df["MA20"].notna().sum() == 0:      # 기간이 10일이면 NAN
            st.info("선택 기간이 20일보다 짧아 MA20을 계산할 수 없어 MA20 표시를 껐어요.")
            show_ma20 = False
        if show_ma60 and df["MA60"].notna().sum() == 0:
            st.info("선택 기간이 60일보다 짧아 MA60을 계산할 수 없어 MA60 표시를 껐어요.")
            show_ma60 = False

        # [가드] 라인 최소 1개
        if not (show_close or show_ma20 or show_ma60):
            st.warning("Close/MA 중 최소 1개는 선택해야 차트를 그릴 수 있어요.")
            st.stop()

        # ============================================================
        # 요약 카드 (수익률 + MDD 포함)
        # ============================================================
        last_close = float(df["Close"].iloc[-1])
        first_close = float(df["Close"].iloc[0])
        return_pct = (last_close / first_close - 1) * 100

        
        # ----------------------------
        # 전일 대비 계산
        # ----------------------------
        if len(df) >= 2:
            prev_close = float(df["Close"].iloc[-2])
            diff = last_close - prev_close
            diff_pct = diff / prev_close * 100
        else:
            diff = 0.0
            diff_pct = 0.0

        is_up = diff > 0
        sign = "▲" if is_up else "▼"   

     
        max_close = float(df["Close"].max())
        min_close = float(df["Close"].min())

        mdd = calc_mdd(df["Close"])
        mdd_pct = mdd * 100

        daily_ret = df["Close"].pct_change()  # 일간수익률 만들고 
        vol = float(daily_ret.std() * 100) if daily_ret.notna().sum() >= 2 else float("nan")  # 표준편차를 % 로 표시 

        c1, c2, c3, c4, c5, c6 = st.columns(6)

        c1.metric(
            "현재가",
            f"{last_close:,.0f}",
            f"{sign} {abs(diff):,.0f} ({abs(diff_pct):.2f}%)"
        )

        c2.metric("기간 수익률", f"{return_pct:.2f}%")
        c3.metric("최고가(종가)", f"{max_close:,.0f}")
        c4.metric("최저가(종가)", f"{min_close:,.0f}")
        c5.metric("최대낙폭(MDD)", f"{mdd_pct:.2f}%")
        c6.metric("변동성(일간)", "-" if pd.isna(vol) else f"{vol:.2f}%")


        st.subheader(f"[{company_name}] 주가 데이터 (코드: {stock_code})")
        
        # =========================
        # 테이블 컬럼 한글화 + 인덱스 제거
        # =========================
        df_table = price_df.copy()

        df_table = df_table.rename(columns={
            "Open": "시가",
            "High": "고가",
            "Low": "저가",
            "Close": "종가",
            "Volume": "거래량",
            "Change": "등락률"
        })

        # Date index → 날짜 컬럼 / 기존 index 제거
        df_table = df_table.reset_index(drop=False)
        df_table = df_table.rename(columns={"Date": "날짜"})

        # 🔥 핵심: index 컬럼 완전 제거
        df_table = df_table[[
            "날짜", "시가", "고가", "저가", "종가", "거래량", "등락률"
        ]]

        st.dataframe(df_table.tail(10), width="stretch", hide_index=True)


        # ============================================================
        # 최근 흐름 요약 (1주 / 1개월 / 3개월)
        # ============================================================
        def period_return(close: pd.Series, n: int):
            if len(close) <= n:
                return None
            return (close.iloc[-1] / close.iloc[-n-1] - 1) * 100

        def format_return(val):
            if val is None:
                return "-"
            arrow = "🔺" if val > 0 else "🔻" if val < 0 else ""
            return f"{val:.2f}% {arrow}"
        
        ret_1w = period_return(df["Close"], 5)    # 1주일
        ret_1m = period_return(df["Close"], 20)   # 1개월
        ret_3m = period_return(df["Close"], 60)   # 3개월

        def delta_str(x):
            if x is None:
                return None
            sign = "▲" if x > 0 else "▼"
            return f"{sign} {abs(x):.2f}%"


        st.subheader("최근 흐름 요약")

        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**1주일**")
            st.markdown(f"<h2>{format_return(ret_1w)}</h2>", unsafe_allow_html=True)

        with c2:
            st.markdown("**1개월**")
            st.markdown(f"<h2>{format_return(ret_1m)}</h2>", unsafe_allow_html=True)

        with c3:
            st.markdown("**3개월**")
            st.markdown(f"<h2>{format_return(ret_3m)}</h2>", unsafe_allow_html=True)


        # ============================================================
        # Hover 템플릿: 날짜/종가/MA/거래량 한 번에
        # ============================================================
        has_volume = "Volume" in df.columns

        customdata = pd.DataFrame({
            "Volume": (df["Volume"] if has_volume else [None] * len(df))
        }).to_numpy()

        close_hover = (
            "<b>%{x|%Y-%m-%d}</b><br>"
            "Close: %{y:,.0f}<br>"
            "Volume: %{customdata[2]:,}<br>"
            "<extra></extra>"
        )

        fig = go.Figure()

        # 레이아웃 (rangeslider는 OFF로 고정)
        fig.update_layout(
            xaxis=dict(
                title="Date",
                rangeslider=dict(visible=False),
            ),
            yaxis=dict(title="Price"),
            yaxis2=dict(
                title="Volume",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=30, r=30, t=60, b=30),
            height=560,
            hovermode="x unified",   # x축 기준으로 hover 정보 통합 표시(마우스를 한 날짜에 올리면 됨)
            title=f"{company_name} 추이",
        )


        # 종가 
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["Close"],
            mode="lines",
            name="Close",
            visible=show_close,
            customdata=customdata,
            hovertemplate=close_hover,
        ))

        # MA 20 : 20일간의 이동평균선
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["MA20"],
            mode="lines",
            name="MA20",
            visible=show_ma20,
            hoverinfo="skip",
        ))
        
        # MA 60 : 60일간의 이동평균선
        fig.add_trace(go.Scatter(
            x=df["date"],
            y=df["MA60"],
            mode="lines",
            name="MA60",
            visible=show_ma60,
            hoverinfo="skip",
        ))

        # 거래량 (보조축)
        fig.add_trace(go.Bar(
            x=df["date"],
            y=(df["Volume"] if has_volume else [0] * len(df)),
            name="Volume",
            opacity=0.25,
            visible=(show_vol and has_volume),
            yaxis="y2",   # 볼륨바는 보조축 
            hoverinfo="skip",
        ))

        # ============================================================
        # MDD 구간 강조 
        # ============================================================
        if show_mdd_zone:
            peak_pos, trough_pos, mdd_val2 = find_mdd_period_iloc(df["Close"])
            mdd_pct2 = mdd_val2 * 100

            peak_date = df.iloc[peak_pos]["date"]
            trough_date = df.iloc[trough_pos]["date"]
            peak_price = float(df.iloc[peak_pos]["Close"])
            trough_price = float(df.iloc[trough_pos]["Close"])

            add_mdd_highlight(
                fig=fig,
                peak_date=peak_date,
                trough_date=trough_date,
                peak_price=peak_price,
                trough_price=trough_price,
                mdd_pct=mdd_pct2,
            )


        # ============================================================
        # Close 타임-플레이 애니메이션
        # ============================================================
        if use_animation:
            MAX_FRAMES = 260  # 프레임 너무 많으면 느려짐 -> 최근 1년치 정도로 제한
            df_anim = df.tail(MAX_FRAMES).copy()

            custom_anim = pd.DataFrame({
                "MA20": df_anim["MA20"],
                "MA60": df_anim["MA60"],
                "Volume": (df_anim["Volume"] if has_volume else [None] * len(df_anim))
            }).to_numpy()

            frames = []
            for i in range(10, len(df_anim) + 1):
                frames.append(go.Frame(
                    data=[
                        go.Scatter(
                            x=df_anim["date"].iloc[:i],
                            y=df_anim["Close"].iloc[:i],
                            customdata=custom_anim[:i],
                            hovertemplate=close_hover,
                        )
                    ],
                    traces=[0]
                ))

            fig.frames = frames

            fig.update_layout(
                updatemenus=[
                    dict(
                        type="buttons",
                        showactive=False,
                        x=0, y=1.15,
                        buttons=[
                            dict(label="▶ Play", method="animate",
                                 args=[None, {"frame": {"duration": 35, "redraw": True},
                                              "transition": {"duration": 0},
                                              "fromcurrent": True, "mode": "immediate"}]),
                            dict(label="⏸ Pause", method="animate",
                                 args=[[None], {"frame": {"duration": 0, "redraw": False},
                                                "mode": "immediate"}]),
                        ],
                    )
                ],
            )
            st.caption("※ Close 애니메이션은 성능을 위해 최근 약 1년(최대 260프레임)만 재생합니다.")

        st.plotly_chart(
            fig,
            use_container_width=True,
            key="main_price_chart"
        )


        # ============================================================
        # 주요 뉴스 헤드라인
        # ============================================================
        st.subheader("📰 주요 뉴스 헤드라인")

        queries = build_news_queries(company_name, stock_code)

        news_items = []
        for q in queries:
            news_items = fetch_google_news_rss(q, limit=10)
            if len(news_items) >= 5:  # 어느 정도 나오면 그 쿼리로 확정
                break

        if not news_items:
            st.info("관련 뉴스가 충분히 검색되지 않았어요. (검색어/종목명 변경 시 개선될 수 있음)")
        else:
            with st.expander(f"뉴스 보기 (검색어: {q})", expanded=True):
                for it in news_items:
                    meta = " · ".join([x for x in [it["source"], it["published"]] if x])
                    st.markdown(f"- [{it['title']}]({it['link']})")
                    if meta:
                        st.caption(meta)


        # ============================================================
        # 엑셀 다운로드
        # ============================================================
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            price_df.to_excel(writer, index=True, sheet_name="Sheet1")

        st.download_button(
            label="📥 엑셀 파일 다운로드",
            data=output.getvalue(),
            file_name=f"{company_name}_주가.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
