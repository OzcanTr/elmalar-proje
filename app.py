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
from io import BytesIO
import calendar

warnings.filterwarnings('ignore')

# ===================== SAYFA YAPILANDIRMASI =====================
st.set_page_config(
    page_title="BIST Sinyal Tarama V3",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================== TÜRKÇE TARİH SEÇİCİ (HİBRİT) =====================
TURKISH_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
]

def parse_turkish_date(date_str):
    """gg.aa.yyyy veya gg/aa/yyyy formatını datetime.date'e çevirir"""
    for sep in ['.', '/']:
        try:
            parts = date_str.split(sep)
            if len(parts) == 3:
                gun, ay, yil = map(int, parts)
                return datetime(yil, ay, gun).date()
        except:
            pass
    return None

def hybrid_date_selector(label, default_date=None, key_prefix=""):
    """
    Hibrit tarih seçici: Manuel giriş (gg.aa.yyyy) + Türkçe takvim
    """
    if default_date is None:
        default_date = datetime.now()
    
    st.markdown(f"**{label}**")
    
    # Manuel giriş
    manuel_tarih_str = st.text_input(
        "📝 Tarih (gg.aa.yyyy)",
        value=default_date.strftime('%d.%m.%Y') if default_date else "",
        key=f"{key_prefix}_manuel",
        placeholder="Örn: 15.07.2025"
    )
    
    manuel_tarih = parse_turkish_date(manuel_tarih_str)
    
    # Takvim seçimi
    with st.expander("📅 Takvimden Seç", expanded=(manuel_tarih is None)):
        col1, col2, col3 = st.columns([1, 1.5, 1])
        
        with col1:
            gun = st.selectbox(
                "Gün",
                options=list(range(1, 32)),
                index=default_date.day - 1 if default_date else 0,
                key=f"{key_prefix}_gun"
            )
        
        with col2:
            ay_index = default_date.month - 1 if default_date else 0
            ay = st.selectbox(
                "Ay",
                options=list(range(1, 13)),
                format_func=lambda x: TURKISH_MONTHS[x-1],
                index=ay_index,
                key=f"{key_prefix}_ay"
            )
        
        with col3:
            yil = st.selectbox(
                "Yıl",
                options=list(range(2020, 2031)),
                index=default_date.year - 2020 if default_date and 2020 <= default_date.year <= 2030 else 5,
                key=f"{key_prefix}_yil"
            )
        
        takvim_tarih = None
        try:
            max_day = calendar.monthrange(yil, ay)[1]
            if gun > max_day:
                st.warning(f"⚠️ {TURKISH_MONTHS[ay-1]} {yil} ayında {max_day} gün vardır.")
            else:
                takvim_tarih = datetime(yil, ay, gun).date()
        except:
            pass
    
    # Öncelik: Manuel giriş > Takvim > Varsayılan
    secilen_tarih = manuel_tarih or takvim_tarih or default_date.date()
    
    st.caption(f"✅ Seçilen: **{secilen_tarih.strftime('%d %B %Y')}**")
    return secilen_tarih

# ===================== YETKİLENDİRME =====================
def check_password():
    CORRECT_USERNAME = "ADMIN"
    CORRECT_PASSWORD = "Elma*"
    
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "login_error" not in st.session_state:
        st.session_state.login_error = False
    if "login_counter" not in st.session_state:
        st.session_state.login_counter = 0
    
    if st.session_state.authenticated:
        return True
    
    st.markdown("""
    <style>
        .login-container {
            max-width: 400px; margin: 80px auto; padding: 2.5rem;
            background: white; border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.15); text-align: center;
        }
        .login-icon { font-size: 4rem; margin-bottom: 1rem; }
        .login-title { font-size: 1.8rem; font-weight: 700; color: #1a1a2e; margin-bottom: 0.5rem; }
        .login-subtitle { font-size: 1rem; color: #666; margin-bottom: 2rem; }
        .stTextInput>div>div>input { text-align: center; font-size: 1.1rem; padding: 0.75rem; }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<div class="login-icon">🔐</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-title">BIST Sinyal Tarama</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-subtitle">Version 3.0 | Yetkili Giriş</div>', unsafe_allow_html=True)
    
    message_placeholder = st.empty()
    
    username = st.text_input("👤 Kullanıcı Adı", key=f"user_{st.session_state.login_counter}", placeholder="Kullanıcı adınız")
    password = st.text_input("🔒 Şifre", type="password", key=f"pass_{st.session_state.login_counter}", placeholder="Şifreniz")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        login_button = st.button("🚀 GİRİŞ YAP", use_container_width=True, type="primary", key=f"btn_{st.session_state.login_counter}")
    
    if login_button:
        if username == CORRECT_USERNAME and password == CORRECT_PASSWORD:
            st.session_state.login_error = False
            st.session_state.authenticated = True
            message_placeholder.success("✅ Giriş başarılı! Yönlendiriliyorsunuz...")
            time.sleep(0.5)
            st.rerun()
        else:
            st.session_state.login_error = True
            st.session_state.login_counter += 1
            message_placeholder.error("❌ Hatalı kullanıcı adı veya şifre!")
            time.sleep(0.3)
            st.rerun()
    
    if st.session_state.login_error and not login_button:
        message_placeholder.error("❌ Hatalı kullanıcı adı veya şifre!")
    
    st.markdown('</div>', unsafe_allow_html=True)
    return False

# ===================== CSS STİLLERİ =====================
st.markdown("""
<style>
    .main-header {
        font-size: 2rem; font-weight: 700; text-align: center; padding: 1rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; border-radius: 15px; margin-bottom: 1.5rem;
    }
    .stButton>button {
        width: 100%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; font-weight: bold; padding: 0.75rem;
        border-radius: 10px; border: none; font-size: 1rem;
    }
    .metric-value { font-size: 1.8rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ===================== SABİTLER =====================
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
    BIST30_SET, BIST50_SET, BIST100_SET = set(BIST30), set(BIST50), set(BIST100)
    return {
        'BIST30': BIST30, 'BIST50': BIST50, 'BIST100': BIST100,
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
            symbol_clean += ".IS"
        
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
            df = df.rename(columns={'index': 'Date'})
        else:
            df = df.rename(columns={date_col: 'Date'})
        
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        
        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'open' in col_lower: col_map[col] = 'Open'
            elif 'high' in col_lower: col_map[col] = 'High'
            elif 'low' in col_lower: col_map[col] = 'Low'
            elif 'close' in col_lower or 'kapanis' in col_lower: col_map[col] = 'Close'
            elif 'volume' in col_lower or 'hacim' in col_lower: col_map[col] = 'Volume'
        
        df = df.rename(columns=col_map)
        if not all(c in df.columns for c in ['Date', 'Open', 'High', 'Low', 'Close']):
            return None
        if 'Volume' not in df.columns:
            df['Volume'] = 0
        
        return df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].sort_values('Date').reset_index(drop=True)
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
    
    df['TR'] = np.maximum(df['High'] - df['Low'], np.maximum(np.abs(df['High'] - df['Close'].shift()), np.abs(df['Low'] - df['Close'].shift())))
    df['DM_plus'] = np.where((df['High'] - df['High'].shift()) > (df['Low'].shift() - df['Low']), np.maximum(df['High'] - df['High'].shift(), 0), 0)
    df['DM_minus'] = np.where((df['Low'].shift() - df['Low']) > (df['High'] - df['High'].shift()), np.maximum(df['Low'].shift() - df['Low'], 0), 0)
    
    atr_14 = df['TR'].rolling(window=14).mean()
    df['DI_plus'] = 100 * (df['DM_plus'].rolling(window=14).mean() / atr_14)
    df['DI_minus'] = 100 * (df['DM_minus'].rolling(window=14).mean() / atr_14)
    dx = (np.abs(df['DI_plus'] - df['DI_minus']) / (df['DI_plus'] + df['DI_minus'])) * 100
    df['ADX'] = dx.rolling(window=14).mean()
    
    df['Volume_MA_ratio'] = df['Volume'] / df['Volume_MA20']
    for period in [2, 3, 5]:
        df[f'Volume_Trend_{period}'] = df['Volume'].rolling(window=period).apply(lambda x: 1 if x.iloc[-1] > x.mean() else 0)
    
    df['Price_Volume_Corr'] = df['Close'].rolling(window=20).corr(df['Volume'])
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    money_flow = typical_price * df['Volume']
    positive_flow = money_flow.where(typical_price > typical_price.shift(), 0).rolling(14).sum()
    negative_flow = money_flow.where(typical_price < typical_price.shift(), 0).rolling(14).sum()
    df['MFI'] = 100 - (100 / (1 + (positive_flow / negative_flow)))
    
    return df

def calculate_performance_score_v3(row):
    score, details = 0, []
    rsi, adx, vol, mfi = row['RSI'], row['ADX'], row['Hacim/MA'], row['MFI']
    
    if 30 <= rsi <= 40: score += 30; details.append(f"RSI:{rsi:.0f}(İdeal)")
    elif 40 < rsi <= 50: score += 25; details.append(f"RSI:{rsi:.0f}(İyi)")
    elif 50 < rsi <= 55: score += 20; details.append(f"RSI:{rsi:.0f}(Kabul)")
    elif 55 < rsi <= 60: score += 15; details.append(f"RSI:{rsi:.0f}(Sınır)")
    elif 25 <= rsi < 30: score += 15; details.append(f"RSI:{rsi:.0f}(Aşırı düşük)")
    else: score += 5; details.append(f"RSI:{rsi:.0f}(Uç)")
    
    if adx < 15: score += 30; details.append(f"ADX:{adx:.0f}(Başlangıç)")
    elif 15 <= adx < 20: score += 25; details.append(f"ADX:{adx:.0f}(Hafif)")
    elif 20 <= adx < 25: score += 20; details.append(f"ADX:{adx:.0f}(Orta)")
    elif 25 <= adx < 30: score += 15; details.append(f"ADX:{adx:.0f}(Güçlü)")
    else: score += 5; details.append(f"ADX:{adx:.0f}(Aşırı)")
    
    if vol > 2.5: score += 25; details.append(f"Hcm:{vol:.1f}(Çok yüksek)")
    elif vol > 1.8: score += 22; details.append(f"Hcm:{vol:.1f}(Yüksek)")
    elif vol > 1.2: score += 18; details.append(f"Hcm:{vol:.1f}(Orta-yüksek)")
    elif vol > 1.0: score += 12; details.append(f"Hcm:{vol:.1f}(Orta)")
    elif vol > 0.8: score += 8; details.append(f"Hcm:{vol:.1f}(Düşük-orta)")
    else: score += 3; details.append(f"Hcm:{vol:.1f}(Düşük)")
    
    if 40 <= mfi <= 55: score += 15; details.append(f"MFI:{mfi:.0f}(İdeal)")
    elif 35 <= mfi <= 60: score += 12; details.append(f"MFI:{mfi:.0f}(İyi)")
    else: score += 3; details.append(f"MFI:{mfi:.0f}(Uç)")
    
    if vol > 1.5 and adx > 20: score += 5; details.append("Bonus(Hcm+Trend)")
    return min(score, 100), details

def check_signal(df, i, params):
    try:
        rsi = df['RSI'].iloc[i]
        if pd.isna(rsi) or rsi > params['RSI_max']: return False, "", 0, []
        close, ma200 = df['Close'].iloc[i], df['MA200'].iloc[i]
        if pd.isna(ma200) or ((close - ma200) / ma200) * 100 < params['MA200_diff_min']: return False, "", 0, []
        stoch, adx = df['Stochastic'].iloc[i], df['ADX'].iloc[i]
        if pd.isna(stoch) or stoch > params['Stochastic_max']: return False, "", 0, []
        if pd.isna(adx) or adx < params['ADX_min']: return False, "", 0, []
        vol_ratio = df['Volume_MA_ratio'].iloc[i]
        if pd.isna(vol_ratio) or vol_ratio < params['Volume_MA_ratio']: return False, "", 0, []
        if df[f'Volume_Trend_{params["Volume_trend_days"]}'].iloc[i] == 0: return False, "", 0, []
        corr, mfi = df['Price_Volume_Corr'].iloc[i], df['MFI'].iloc[i]
        if pd.isna(corr) or corr < params['Price_volume_correlation']: return False, "", 0, []
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

def process_single_stock(hisse, ref_date_str):
    ref_date = pd.to_datetime(ref_date_str)
    try:
        df = get_data_cached(hisse, ref_date_str)
        if df is None: return None
        df = calculate_indicators(df)
        i = find_ref_index(df, ref_date)
        if i is None: return None
        current = df['Close'].iloc[i]
        if pd.isna(current): return None
        
        params = STRATEGIES['Esnek']
        is_buy, _, _, _ = check_signal(df, i, params)
        if not is_buy: return None
        
        row = {
            "Hisse": hisse, "Tarih": df.iloc[i]['Date'].strftime('%Y-%m-%d'),
            "Kapanis": round(current, 2), "RSI": round(df['RSI'].iloc[i], 1),
            "ADX": round(df['ADX'].iloc[i], 1), "Hacim/MA": round(df['Volume_MA_ratio'].iloc[i], 2),
            "MFI": round(df['MFI'].iloc[i], 1),
        }
        perf_score, perf_details = calculate_performance_score_v3(row)
        row['Perf_Skor'] = perf_score
        row['Perf_Detay'] = " | ".join(perf_details)
        
        for s in FORWARD_STEPS:
            if i + s < len(df):
                future = df['Close'].iloc[i + s]
                row[f'+{s}_RET'] = round(((future - current) / current) * 100, 2)
            else:
                row[f'+{s}_RET'] = None
        
        if row['RSI'] > RISK_FILTERS['Max_RSI'] or row['ADX'] > RISK_FILTERS['Max_ADX']: return None
        if row['Hacim/MA'] < RISK_FILTERS['Min_Volume_MA'] or row['MFI'] > RISK_FILTERS['Max_MFI']: return None
        if perf_score < RISK_FILTERS['Min_Perf_Score']: return None
        
        return row
    except:
        return None

def run_single_date_v3_parallel(hisseler, ref_date):
    results = []
    ref_date_str = ref_date.strftime('%Y-%m-%d') if hasattr(ref_date, 'strftime') else ref_date
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_stock, h, ref_date_str): h for h in hisseler}
        for future in as_completed(futures):
            result = future.result()
            if result: results.append(result)
    return results

def get_business_days_between(start_date, end_date):
    business_days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            business_days.append(current)
        current += timedelta(days=1)
    return business_days

# ===================== GRAFİKLER (KISALTILDI) =====================
def create_performance_chart(all_signals):
    periods, avg_returns, win_rates = [], [], []
    for s in FORWARD_STEPS:
        rets = [r[f'+{s}_RET'] for r in all_signals if r.get(f'+{s}_RET') is not None]
        if rets:
            periods.append(f'{s}G')
            avg_returns.append(sum(rets)/len(rets))
            win_rates.append(sum(1 for r in rets if r > 0)/len(rets)*100)
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Ortalama Getiri (%)', 'Kazanma Oranı (%)'))
    fig.add_trace(go.Bar(x=periods, y=avg_returns, marker_color=['#28a745' if x > 0 else '#dc3545' for x in avg_returns]), row=1, col=1)
    fig.add_trace(go.Bar(x=periods, y=win_rates, marker_color=['#28a745' if x > 60 else '#ffc107' for x in win_rates]), row=1, col=2)
    fig.update_layout(height=400, showlegend=False, template='plotly_white')
    return fig

# ===================== ANA UYGULAMA =====================
def main():
    if not check_password():
        return
    
    col1, col2 = st.columns([8, 1])
    with col1:
        st.markdown('<div class="main-header">📈 BIST SİNYAL TARAMA V3<br><small>Türkçe Tarih Seçici | Paralel İşlem</small></div>', unsafe_allow_html=True)
    with col2:
        if st.button("🚪 ÇIKIŞ", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key != 'authenticated': del st.session_state[key]
            st.session_state.authenticated = False
            st.rerun()
    
    with st.sidebar:
        st.markdown("### ⚙️ AYARLAR")
        listeler = get_bist_lists()
        liste_secim = st.selectbox("Liste Seçin", list(listeler.keys()))
        hisseler = listeler[liste_secim]
        st.markdown(f"*{len(hisseler)} hisse*")
        
        st.markdown("**📅 Tarih**")
        tarih_tip = st.radio("Tip", ["Tek Tarih", "Tarih Aralığı", "Ay"], horizontal=True)
        
        if tarih_tip == "Tek Tarih":
            ref_date = hybrid_date_selector("Tarih Seçin", datetime(2025, 7, 7), "tek")
            start_date = end_date = ref_date
        elif tarih_tip == "Tarih Aralığı":
            start_date = hybrid_date_selector("Başlangıç", datetime(2025, 7, 7), "bas")
            end_date = hybrid_date_selector("Bitiş", datetime(2025, 7, 10), "bit")
            if start_date > end_date:
                st.warning("⚠️ Başlangıç, bitişten büyük olamaz!")
                start_date, end_date = end_date, start_date
        else:
            c1, c2 = st.columns(2)
            with c1: yil = st.selectbox("Yıl", range(2020, 2031), index=5)
            with c2: ay = st.selectbox("Ay", range(1,13), format_func=lambda x: TURKISH_MONTHS[x-1], index=6)
            start_date = datetime(yil, ay, 1).date()
            end_date = (datetime(yil, ay+1, 1) if ay < 12 else datetime(yil+1, 1, 1)).date() - timedelta(days=1)
        
        gun = len(get_business_days_between(pd.to_datetime(start_date), pd.to_datetime(end_date)))
        st.caption(f"⏱️ ~{gun*len(hisseler)*0.1/MAX_WORKERS:.0f}s | {gun} işlem günü")
        
        tarama_btn = st.button("🔍 TARAMAYI BAŞLAT", use_container_width=True)
    
    if tarama_btn:
        start_time = time.time()
        with st.spinner('🔍 Paralel tarama...'):
            business_days = get_business_days_between(pd.to_datetime(start_date), pd.to_datetime(end_date))
            all_results, all_signals = {}, []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, day in enumerate(business_days):
                status_text.text(f"📅 {day.strftime('%d.%m.%Y')} | ⚡ {time.time()-start_time:.0f}s")
                results = run_single_date_v3_parallel(hisseler, day)
                if results:
                    all_results[day.strftime('%Y-%m-%d')] = results
                    all_signals.extend(results)
                progress_bar.progress((i+1)/len(business_days))
            
            progress_bar.empty(), status_text.empty()
        
        if all_signals:
            st.session_state.df_all = pd.DataFrame(all_signals)
            st.session_state.scan_completed = True
            st.session_state.scan_time = time.time() - start_time
        else:
            st.warning("⚠️ Sinyal bulunamadı!")
            st.session_state.scan_completed = False
    
    if st.session_state.get('scan_completed', False):
        df_all = st.session_state.df_all
        st.markdown("### 📊 TARAMA SONUÇLARI")
        st.caption(f"⚡ {st.session_state.scan_time:.1f}s")
        
        rets_30 = df_all['+30_RET'].dropna()
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Sinyal", len(df_all))
        with c2: st.metric("30G Ort.", f"%{rets_30.mean():.1f}" if len(rets_30)>0 else "N/A")
        with c3: st.metric("30G Kazanma", f"%{(rets_30>0).sum()/len(rets_30)*100:.0f}" if len(rets_30)>0 else "N/A")
        
        st.plotly_chart(create_performance_chart(df_all.to_dict('records')), use_container_width=True)
        
        st.markdown("### 📋 SİNYAL TABLOSU")
        st.dataframe(df_all[['Hisse','Tarih','Kapanis','Perf_Skor','RSI','ADX','Hacim/MA','MFI','+5_RET','+10_RET','+15_RET','+30_RET','+60_RET','+90_RET']],
                     use_container_width=True, height=400)
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📊 CSV İndir", df_all.to_csv(index=False), "sinyaller.csv", "text/csv")
        with col2:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_all.to_excel(writer, index=False)
            st.download_button("📑 EXCEL İndir", output.getvalue(), "sinyaller.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    elif not tarama_btn:
        st.markdown("### 🚀 Hoş Geldiniz!")

if __name__ == "__main__":
    main()
