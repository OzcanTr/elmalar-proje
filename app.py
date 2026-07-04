import streamlit as st
import pandas as pd
import numpy as np
import borsapy as bp
from datetime import datetime, timedelta
import warnings
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import hashlib
import os

warnings.filterwarnings('ignore')

# ===================== SAYFA YAPILANDIRMASI =====================
st.set_page_config(
    page_title="BIST Sinyal Tarama V3",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ===================== YETKİLENDİRME =====================
def check_password():
    """Şifre kontrolü - Sadece yetkili kullanıcı girebilir"""

    # BU ŞİFREYİ DEĞİŞTİRİN!
    CORRECT_USERNAME = "Karabulut"
    CORRECT_PASSWORD = "Elmalar01*"  # Güçlü bir şifre belirleyin

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        # Login ekranı
        st.markdown("""
        <style>
            .login-container {
                max-width: 400px;
                margin: 100px auto;
                padding: 2rem;
                background: white;
                border-radius: 15px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            }
            .login-header {
                text-align: center;
                margin-bottom: 2rem;
            }
        </style>
        """, unsafe_allow_html=True)

        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown("## 🔐 BIST Sinyal Tarama V3")
        st.markdown("#### Lütfen giriş yapın")

        username = st.text_input("👤 Kullanıcı Adı", placeholder="Kullanıcı adınızı girin")
        password = st.text_input("🔒 Şifre", type="password", placeholder="Şifrenizi girin")

        if st.button("🚀 GİRİŞ YAP", use_container_width=True):
            if username == CORRECT_USERNAME and password == CORRECT_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Hatalı kullanıcı adı veya şifre!")

        st.markdown('</div>', unsafe_allow_html=True)
        return False

    return True


# ===================== CSS STİLLERİ =====================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        text-align: center;
        padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1.5rem;
        text-align: center;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    .positive { color: #28a745; font-weight: bold; }
    .negative { color: #dc3545; font-weight: bold; }
    .stButton>button {
        width: 100%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        padding: 0.75rem;
        border-radius: 10px;
        border: none;
    }
    .logout-btn {
        text-align: right;
        padding: 0.5rem;
    }
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .status-online {
        background: #d4edda;
        color: #155724;
    }
    .status-offline {
        background: #f8d7da;
        color: #721c24;
    }
</style>
""", unsafe_allow_html=True)

# ===================== SABİTLER (OPTİMİZE) =====================
LOOKBACK_DAYS = 150
FORWARD_STEPS = [5, 10, 15, 30, 60, 90]
MAX_WORKERS = 10

STRATEGIES = {
    'Esnek': {
        'RSI_max': 65, 'MA200_diff_min': -30, 'MACD_signal': False,
        'Stochastic_max': 80, 'ADX_min': 3, 'Volume_MA_ratio': 0.3,
        'Volume_trend_days': 2, 'Price_volume_correlation': 0.05,
        'MFI_max': 70, 'Min_Score': 0, 'Min_Volume_MA': 0,
    }
}

RISK_FILTERS = {
    'Min_Perf_Score': 65, 'Max_RSI': 60, 'Max_ADX': 45,
    'Min_Volume_MA': 0.8, 'Max_MFI': 65,
}


# ===================== CACHE FONKSİYONLARI =====================
@st.cache_data(ttl=3600)
def get_index_members_cached(index_code):
    try:
        idx = bp.Index(index_code)
        return sorted(set(idx.component_symbols))
    except:
        return []


@st.cache_data(ttl=3600)
def get_bist_lists():
    BIST30 = get_index_members_cached("XU030")
    BIST50 = get_index_members_cached("XU050")
    BIST100 = get_index_members_cached("XU100")

    BIST30_SET = set(BIST30)
    BIST50_SET = set(BIST50)
    BIST100_SET = set(BIST100)

    return {
        'BIST30': BIST30,
        'BIST50': BIST50,
        'BIST100': BIST100,
        'BIST30 DIŞI': sorted(BIST100_SET - BIST30_SET),
        'BIST50 DIŞI': sorted(BIST100_SET - BIST50_SET),
        'Takip Listesi': ["ASELS", "THYAO", "SISE", "EREGL", "BIMAS"]
    }


@st.cache_data(ttl=1800)
def get_data_cached(symbol, ref_date_str):
    ref_date = pd.to_datetime(ref_date_str)
    try:
        start = ref_date - pd.Timedelta(days=LOOKBACK_DAYS * 2)
        end = ref_date + pd.Timedelta(days=LOOKBACK_DAYS)
        symbol_clean = symbol.upper().strip()
        if not symbol_clean.endswith(".IS"):
            symbol_clean = symbol_clean + ".IS"

        ticker = bp.Ticker(symbol_clean)
        df = ticker.history(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))

        if df is None or len(df) == 0:
            return None

        df = df.reset_index()
        date_col = None
        for col in df.columns:
            if 'date' in col.lower() or 'index' in col.lower():
                date_col = col
                break

        if date_col is None:
            df = df.reset_index(drop=False)
            df = df.rename(columns={'index': 'Date'})
        else:
            df = df.rename(columns={date_col: 'Date'})

        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)

        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'open' in col_lower:
                col_map[col] = 'Open'
            elif 'high' in col_lower:
                col_map[col] = 'High'
            elif 'low' in col_lower:
                col_map[col] = 'Low'
            elif 'close' in col_lower or 'kapanis' in col_lower:
                col_map[col] = 'Close'
            elif 'volume' in col_lower or 'hacim' in col_lower:
                col_map[col] = 'Volume'

        df = df.rename(columns=col_map)
        required = ['Date', 'Open', 'High', 'Low', 'Close']
        for col in required:
            if col not in df.columns:
                return None

        if 'Volume' not in df.columns:
            df['Volume'] = 0

        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
        return df.sort_values('Date').reset_index(drop=True)
    except:
        return None


# ===================== TEKNİK GÖSTERGELER =====================

def calculate_indicators(df):
    for period in [5, 10, 20, 50, 100, 200]:
        df[f'MA{period}'] = df['Close'].rolling(window=period).mean()
        df[f'Volume_MA{period}'] = df['Volume'].rolling(window=period).mean()

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    low_14 = df['Low'].rolling(window=14).min()
    high_14 = df['High'].rolling(window=14).max()
    df['Stochastic'] = 100 * ((df['Close'] - low_14) / (high_14 - low_14))

    df['TR'] = np.maximum(df['High'] - df['Low'],
                          np.maximum(np.abs(df['High'] - df['Close'].shift()), np.abs(df['Low'] - df['Close'].shift())))
    df['DM_plus'] = np.where((df['High'] - df['High'].shift()) > (df['Low'].shift() - df['Low']),
                             np.maximum(df['High'] - df['High'].shift(), 0), 0)
    df['DM_minus'] = np.where((df['Low'].shift() - df['Low']) > (df['High'] - df['High'].shift()),
                              np.maximum(df['Low'].shift() - df['Low'], 0), 0)

    atr_14 = df['TR'].rolling(window=14).mean()
    df['DI_plus'] = 100 * (df['DM_plus'].rolling(window=14).mean() / atr_14)
    df['DI_minus'] = 100 * (df['DM_minus'].rolling(window=14).mean() / atr_14)
    dx = (np.abs(df['DI_plus'] - df['DI_minus']) / (df['DI_plus'] + df['DI_minus'])) * 100
    df['ADX'] = dx.rolling(window=14).mean()

    df['Volume_MA_ratio'] = df['Volume'] / df['Volume_MA20']

    for period in [2, 3, 5]:
        df[f'Volume_Trend_{period}'] = df['Volume'].rolling(window=period).apply(
            lambda x: 1 if x.iloc[-1] > x.mean() else 0)

    df['Price_Volume_Corr'] = df['Close'].rolling(window=20).corr(df['Volume'])
    df['Volume_Increase'] = ((df['Volume'] / df['Volume'].shift(10)) - 1) * 100

    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    money_flow = typical_price * df['Volume']
    positive_flow = money_flow.where(typical_price > typical_price.shift(), 0).rolling(14).sum()
    negative_flow = money_flow.where(typical_price < typical_price.shift(), 0).rolling(14).sum()
    money_ratio = positive_flow / negative_flow
    df['MFI'] = 100 - (100 / (1 + money_ratio))

    df['Price_Change_5'] = df['Close'].pct_change(periods=5) * 100
    df['Price_Change_10'] = df['Close'].pct_change(periods=10) * 100

    return df


def calculate_performance_score_v3(row):
    score = 0
    details = []
    rsi, adx, vol, mfi = row['RSI'], row['ADX'], row['Hacim/MA'], row['MFI']

    if 30 <= rsi <= 40:
        score += 30; details.append(f"RSI:{rsi:.0f}(İdeal)")
    elif 40 < rsi <= 50:
        score += 25; details.append(f"RSI:{rsi:.0f}(İyi)")
    elif 50 < rsi <= 55:
        score += 20; details.append(f"RSI:{rsi:.0f}(Kabul)")
    elif 55 < rsi <= 60:
        score += 15; details.append(f"RSI:{rsi:.0f}(Sınır)")
    elif 25 <= rsi < 30:
        score += 15; details.append(f"RSI:{rsi:.0f}(Aşırı düşük)")
    else:
        score += 5; details.append(f"RSI:{rsi:.0f}(Uç)")

    if adx < 15:
        score += 30; details.append(f"ADX:{adx:.0f}(Başlangıç)")
    elif 15 <= adx < 20:
        score += 25; details.append(f"ADX:{adx:.0f}(Hafif)")
    elif 20 <= adx < 25:
        score += 20; details.append(f"ADX:{adx:.0f}(Orta)")
    elif 25 <= adx < 30:
        score += 15; details.append(f"ADX:{adx:.0f}(Güçlü)")
    elif 30 <= adx < 35:
        score += 10; details.append(f"ADX:{adx:.0f}(Çok güçlü)")
    else:
        score += 5; details.append(f"ADX:{adx:.0f}(Aşırı)")

    if vol > 2.5:
        score += 25; details.append(f"Hcm:{vol:.1f}(Çok yüksek)")
    elif vol > 1.8:
        score += 22; details.append(f"Hcm:{vol:.1f}(Yüksek)")
    elif vol > 1.2:
        score += 18; details.append(f"Hcm:{vol:.1f}(Orta-yüksek)")
    elif vol > 1.0:
        score += 12; details.append(f"Hcm:{vol:.1f}(Orta)")
    elif vol > 0.8:
        score += 8; details.append(f"Hcm:{vol:.1f}(Düşük-orta)")
    else:
        score += 3; details.append(f"Hcm:{vol:.1f}(Düşük)")

    if 40 <= mfi <= 55:
        score += 15; details.append(f"MFI:{mfi:.0f}(İdeal)")
    elif 35 <= mfi <= 60:
        score += 12; details.append(f"MFI:{mfi:.0f}(İyi)")
    elif 30 <= mfi <= 65:
        score += 8; details.append(f"MFI:{mfi:.0f}(Kabul)")
    else:
        score += 3; details.append(f"MFI:{mfi:.0f}(Uç)")

    if vol > 1.5 and adx > 20: score += 5; details.append("Bonus(Hcm+Trend)")

    return min(score, 100), details


def check_signal(df, i, params):
    try:
        rsi = df['RSI'].iloc[i]
        if pd.isna(rsi) or rsi > params['RSI_max']: return False, "", 0, []

        close = df['Close'].iloc[i]
        ma200 = df['MA200'].iloc[i]
        if pd.isna(ma200): return False, "", 0, []

        ma200_diff = ((close - ma200) / ma200) * 100
        if ma200_diff < params['MA200_diff_min']: return False, "", 0, []

        stoch = df['Stochastic'].iloc[i]
        if pd.isna(stoch) or stoch > params['Stochastic_max']: return False, "", 0, []

        adx = df['ADX'].iloc[i]
        if pd.isna(adx) or adx < params['ADX_min']: return False, "", 0, []

        vol_ratio = df['Volume_MA_ratio'].iloc[i]
        if pd.isna(vol_ratio) or vol_ratio < params['Volume_MA_ratio']: return False, "", 0, []

        trend = df[f'Volume_Trend_{params["Volume_trend_days"]}'].iloc[i]
        if trend == 0: return False, "", 0, []

        corr = df['Price_Volume_Corr'].iloc[i]
        if pd.isna(corr) or corr < params['Price_volume_correlation']: return False, "", 0, []

        mfi = df['MFI'].iloc[i]
        if pd.isna(mfi) or mfi > params['MFI_max']: return False, "", 0, []

        return True, "✓", 0, []
    except:
        return False, "", 0, []


def find_ref_index(df, ref_date):
    ref_date = pd.to_datetime(ref_date).normalize()
    dates = df['Date'].dt.normalize()
    for i in range(len(df)):
        if dates.iloc[i] >= ref_date:
            return i
    return None


def get_value(df, i, col):
    try:
        val = df[col].iloc[i]
        return float(val) if not pd.isna(val) else None
    except:
        return None


def get_future(df, i, step):
    if i + step >= len(df): return None
    try:
        return float(df['Close'].iloc[i + step])
    except:
        return None


def calc_return(current, future):
    if current is None or future is None: return None
    return ((future - current) / current) * 100


def process_single_stock(hisse, ref_date_str):
    ref_date = pd.to_datetime(ref_date_str)
    try:
        df = get_data_cached(hisse, ref_date_str)
        if df is None: return None

        df = calculate_indicators(df)
        i = find_ref_index(df, ref_date)
        if i is None: return None

        current = get_value(df, i, 'Close')
        if current is None: return None

        params = STRATEGIES['Esnek']
        is_buy, msg, score, details = check_signal(df, i, params)

        if not is_buy: return None

        row = {
            "Hisse": hisse,
            "Tarih": df.iloc[i]['Date'].strftime('%Y-%m-%d'),
            "Kapanis": round(current, 2),
            "Puan": score,
            "RSI": round(get_value(df, i, 'RSI'), 1),
            "ADX": round(get_value(df, i, 'ADX'), 1),
            "Hacim/MA": round(get_value(df, i, 'Volume_MA_ratio'), 2),
            "MFI": round(get_value(df, i, 'MFI'), 1),
        }

        perf_score, perf_details = calculate_performance_score_v3(row)
        row['Perf_Skor'] = perf_score
        row['Perf_Detay'] = " | ".join(perf_details)

        for s in FORWARD_STEPS:
            f = get_future(df, i, s)
            ret = calc_return(current, f)
            row[f'+{s}_RET'] = round(ret, 2) if ret is not None else None

        if row['RSI'] > RISK_FILTERS['Max_RSI']: return None
        if row['ADX'] > RISK_FILTERS['Max_ADX']: return None
        if row['Hacim/MA'] < RISK_FILTERS['Min_Volume_MA']: return None
        if row['MFI'] > RISK_FILTERS['Max_MFI']: return None

        if row.get('Perf_Skor', 0) < RISK_FILTERS['Min_Perf_Score']: return None

        rets = []
        if row.get('+5_RET') is not None: rets.append(row['+5_RET'])
        if row.get('+10_RET') is not None: rets.append(row['+10_RET'])
        if row.get('+15_RET') is not None: rets.append(row['+15_RET'])

        if rets and sum(rets) / len(rets) <= 0: return None

        return row
    except:
        return None


def run_single_date_v3_parallel(hisseler, ref_date, max_workers=MAX_WORKERS):
    results = []
    ref_date_str = ref_date.strftime('%Y-%m-%d') if hasattr(ref_date, 'strftime') else ref_date

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_stock, h, ref_date_str): h for h in hisseler}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results


def get_business_days_between(start_date, end_date):
    business_days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            business_days.append(current)
        current += timedelta(days=1)
    return business_days


# ===================== GRAFİK FONKSİYONLARI (DÜZELTİLMİŞ) =====================

def create_performance_chart(all_signals):
    periods = []
    avg_returns = []
    win_rates = []

    for s in FORWARD_STEPS:
        rets = [r.get(f'+{s}_RET', 0) for r in all_signals if r.get(f'+{s}_RET') is not None]
        if rets:
            periods.append(f'{s} Gün')
            avg_returns.append(sum(rets) / len(rets))
            win_rates.append(sum(1 for r in rets if r > 0) / len(rets) * 100)

    fig = make_subplots(rows=1, cols=2, subplot_titles=('Ortalama Getiri (%)', 'Kazanma Oranı (%)'),
                        specs=[[{'type': 'bar'}, {'type': 'bar'}]])

    colors_ret = ['#28a745' if x > 0 else '#dc3545' for x in avg_returns]
    colors_win = ['#28a745' if x > 80 else '#ffc107' if x > 60 else '#dc3545' for x in win_rates]

    fig.add_trace(go.Bar(x=periods, y=avg_returns, marker_color=colors_ret,
                         text=[f'%{x:.1f}' for x in avg_returns], textposition='outside'), row=1, col=1)
    fig.add_trace(go.Bar(x=periods, y=win_rates, marker_color=colors_win,
                         text=[f'%{x:.0f}' for x in win_rates], textposition='outside'), row=1, col=2)

    fig.update_layout(height=400, showlegend=False, template='plotly_white',
                      margin=dict(t=40, b=20, l=20, r=20))
    fig.update_yaxes(title_text='Getiri (%)', row=1, col=1)
    fig.update_yaxes(title_text='Kazanma (%)', row=1, col=2)

    return fig


def create_signal_scatter(all_signals):
    df = pd.DataFrame(all_signals)
    df['+30_RET_clean'] = df['+30_RET'].fillna(0)

    fig = px.scatter(df, x='RSI', y='Perf_Skor', size='Hacim/MA', color='+30_RET_clean',
                     hover_name='Hisse', text='Hisse',
                     color_continuous_scale=['#dc3545', '#ffc107', '#28a745'],
                     title='Sinyal Kalite Haritası (N/A = 0)',
                     labels={'+30_RET_clean': '30G Getiri (%)', 'Perf_Skor': 'Performans Skoru'})

    fig.update_traces(textposition='top center', marker=dict(sizemode='area', sizeref=0.1))
    fig.update_layout(height=500, template='plotly_white')

    return fig


def create_waterfall_chart(all_signals):
    df = pd.DataFrame(all_signals)
    df['+30_RET_clean'] = df['+30_RET'].fillna(0)
    df_sorted = df.sort_values('+30_RET_clean', ascending=False)

    colors = ['#28a745' if x > 0 else '#ffc107' if x == 0 else '#dc3545' for x in df_sorted['+30_RET_clean']]

    fig = go.Figure(go.Bar(
        x=df_sorted['Hisse'], y=df_sorted['+30_RET_clean'],
        marker_color=colors,
        text=[f'%{x:.1f}' if pd.notna(x) else 'N/A' for x in df_sorted['+30_RET']],
        textposition='outside'
    ))

    fig.update_layout(title='30 Günlük Getiri Dağılımı (Sarı = Henüz Oluşmadı)', height=400,
                      template='plotly_white', xaxis_tickangle=-45)

    return fig


def create_date_heatmap(all_results):
    data = []
    for date_str, results in all_results.items():
        for r in results:
            data.append({
                'Tarih': date_str,
                'Hisse': r['Hisse'],
                '30G': r.get('+30_RET', 0) if r.get('+30_RET') is not None else 0
            })

    df = pd.DataFrame(data)
    if df.empty:
        return None

    pivot = df.pivot_table(values='30G', index='Hisse', columns='Tarih', aggfunc='mean')

    fig = px.imshow(pivot, text_auto='.0f', aspect='auto',
                    color_continuous_scale=['#dc3545', '#ffffff', '#28a745'],
                    title='Tarih & Hisse Bazında 30G Getiri (%)')

    fig.update_layout(height=max(300, len(pivot) * 30), template='plotly_white')

    return fig


# ===================== ANA UYGULAMA =====================

def main():
    # Şifre kontrolü
    if not check_password():
        return

    # Üst bar - Kullanıcı bilgisi ve çıkış
    col1, col2 = st.columns([6, 1])
    with col1:
        st.markdown(
            '<div class="main-header">📈 BIST SİNYAL TARAMA V3<br><small>Paralel İşlem | Gelişmiş Skor | Mobil Uyumlu</small></div>',
            unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="logout-btn">', unsafe_allow_html=True)
        if st.button("🚪 ÇIKIŞ", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ AYARLAR")
        st.info(f"🚀 **Paralel:** {MAX_WORKERS} thread\n📊 **Lookback:** {LOOKBACK_DAYS}g\n📱 **Mobil:** Uyumlu")

        st.markdown("**📊 Hisse Listesi**")
        listeler = get_bist_lists()
        liste_secim = st.selectbox("Liste Seçin", list(listeler.keys()))
        hisseler = listeler[liste_secim]
        st.markdown(f"*{len(hisseler)} hisse*")

        st.markdown("**📅 Tarih Aralığı**")
        tarih_tip = st.radio("Tarih Tipi", ["Tek Tarih", "Tarih Aralığı", "Ay Seçimi"], horizontal=True)

        if tarih_tip == "Tek Tarih":
            ref_date = st.date_input("Tarih", datetime(2025, 7, 7))
            start_date = end_date = ref_date
        elif tarih_tip == "Tarih Aralığı":
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Başlangıç", datetime(2025, 7, 7))
            with col2:
                end_date = st.date_input("Bitiş", datetime(2025, 7, 10))
        else:
            col1, col2 = st.columns(2)
            with col1:
                year = st.number_input("Yıl", 2020, 2030, 2025)
            with col2:
                month = st.number_input("Ay", 1, 12, 7)
            start_date = pd.Timestamp(year=year, month=month, day=1)
            end_date = pd.Timestamp(year=year, month=month + 1, day=1) - timedelta(
                days=1) if month < 12 else pd.Timestamp(year=year + 1, month=1, day=1) - timedelta(days=1)

        gun_sayisi = len(get_business_days_between(pd.to_datetime(start_date), pd.to_datetime(end_date)))
        tahmini_sure = gun_sayisi * len(hisseler) * 0.1 / MAX_WORKERS
        st.caption(f"⏱️ ~{tahmini_sure:.0f}s | 📅 {gun_sayisi} işlem günü")

        st.markdown("**🎯 Filtreler**")
        st.markdown(
            f"Perf.Skor ≥ {RISK_FILTERS['Min_Perf_Score']} | Hcm/MA ≥ {RISK_FILTERS['Min_Volume_MA']} | RSI ≤ {RISK_FILTERS['Max_RSI']}")

        st.markdown("---")
        tarama_btn = st.button("🔍 TARAMAYI BAŞLAT", use_container_width=True)

    # Ana içerik
    if tarama_btn:
        start_time = time.time()

        with st.spinner('🔍 Paralel tarama yapılıyor...'):
            business_days = get_business_days_between(pd.to_datetime(start_date), pd.to_datetime(end_date))

            all_results = {}
            all_signals = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, day in enumerate(business_days):
                elapsed = time.time() - start_time
                status_text.text(
                    f"📅 {day.strftime('%Y-%m-%d')} | ⚡ Paralel | ⏱️ {elapsed:.0f}s | {i + 1}/{len(business_days)}")

                results = run_single_date_v3_parallel(hisseler, day)
                if results:
                    all_results[day.strftime('%Y-%m-%d')] = results
                    all_signals.extend(results)

                progress_bar.progress((i + 1) / len(business_days))

            progress_bar.empty()
            status_text.empty()

        elapsed_total = time.time() - start_time

        if all_signals:
            df_all = pd.DataFrame(all_signals)

            st.markdown("### 📊 TARAMA SONUÇLARI")
            st.caption(f"⚡ {elapsed_total:.1f}s | Paralel: {MAX_WORKERS} thread | 📱 Mobil uyumlu")

            # Metrikler - None kontrolü
            rets_30 = df_all['+30_RET'].dropna()
            rets_60 = df_all['+60_RET'].dropna()

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Toplam Sinyal", len(all_signals))
            with col2:
                st.metric("30G Ort. Getiri", f"%{rets_30.mean():.1f}" if len(rets_30) > 0 else "N/A")
            with col3:
                win_30 = (rets_30 > 0).sum() if len(rets_30) > 0 else 0
                st.metric("30G Kazanma", f"%{win_30 / len(rets_30) * 100:.0f}" if len(rets_30) > 0 else "N/A")
            with col4:
                st.metric("Ort. Perf.Skor", f"{df_all['Perf_Skor'].mean():.0f}")
            with col5:
                st.metric("60G Ort. Getiri", f"%{rets_60.mean():.1f}" if len(rets_60) > 0 else "N/A")

            st.markdown("---")

            # Grafikler
            st.markdown("### 📈 PERFORMANS GRAFİKLERİ")

            tab1, tab2, tab3, tab4 = st.tabs(["📊 Genel", "🎯 Harita", "📉 Dağılım", "🗺️ Isı"])

            with tab1:
                st.plotly_chart(create_performance_chart(all_signals), use_container_width=True)
            with tab2:
                st.plotly_chart(create_signal_scatter(all_signals), use_container_width=True)
            with tab3:
                st.plotly_chart(create_waterfall_chart(all_signals), use_container_width=True)
            with tab4:
                fig = create_date_heatmap(all_results)
                if fig: st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # Sinyal Tablosu
            st.markdown("### 📋 SİNYAL TABLOSU")

            col1, col2, col3 = st.columns(3)
            with col1:
                min_perf = st.slider("Min Perf.Skor", 0, 100, 65)
            with col2:
                min_ret = st.slider("Min 30G (%)", -50, 200, -50)
            with col3:
                sort_by = st.selectbox("Sırala", ["Perf_Skor", "+30_RET", "+60_RET", "RSI", "Hacim/MA"])

            df_filtered = df_all[(df_all['Perf_Skor'] >= min_perf) & (df_all['+30_RET'].fillna(0) >= min_ret)]
            df_filtered = df_filtered.sort_values(sort_by, ascending=False)

            st.dataframe(
                df_filtered[
                    ['Hisse', 'Tarih', 'Kapanis', 'Perf_Skor', 'RSI', 'ADX', 'Hacim/MA', 'MFI', '+5_RET', '+10_RET',
                     '+15_RET', '+30_RET', '+60_RET', '+90_RET']],
                use_container_width=True, height=400,
                column_config={
                    '+30_RET': st.column_config.NumberColumn('30G', format='%.1f%%'),
                    '+60_RET': st.column_config.NumberColumn('60G', format='%.1f%%'),
                    '+90_RET': st.column_config.NumberColumn('90G', format='%.1f%%'),
                }
            )

            # CSV İndir
            st.markdown("---")
            csv = df_filtered.to_csv(index=False)
            st.download_button("📥 CSV İndir", csv,
                               f"BIST_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv", "text/csv")
        else:
            st.warning("⚠️ Hiç sinyal bulunamadı!")
    else:
        # Başlangıç ekranı
        st.markdown("### 🚀 Hoş Geldiniz!")
        st.markdown(f"""
        **BIST Sinyal Tarama V3** - Profesyonel Teknik Analiz Aracı

        🔐 **Güvenli:** Sadece yetkili kullanıcılar
        ⚡ **Hızlı:** {MAX_WORKERS}x paralel işlem
        📱 **Mobil:** Telefon/tablet uyumlu
        🌐 **İnternet:** Her yerden erişim

        **Başlamak için** sol panelden ayarları yapıp taramayı başlatın!
        """)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("⚡ Hız", f"{MAX_WORKERS}x")
        with col2:
            st.metric("🎯 Algoritma", "V3")
        with col3:
            st.metric("📱 Mobil", "✓")
        with col4:
            st.metric("🔐 Güvenlik", "Aktif")


if __name__ == "__main__":
    main()
