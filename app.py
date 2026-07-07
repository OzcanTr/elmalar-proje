import streamlit as st
import pandas as pd
import numpy as np
import borsapy as bp
from datetime import datetime, timedelta
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import BytesIO
import calendar
import plotly.graph_objects as go

warnings.filterwarnings('ignore')

st.set_page_config(page_title="BIST Sinyal Tarama Pro", page_icon="📈", layout="wide")

# ===================== TÜRKÇE TARİH SEÇİCİ =====================
TURKISH_MONTHS = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
TURKISH_DAYS = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]

def turkish_date_picker(label, default_date=None, key="tcal", min_date=None, max_date=None):
    if default_date is None:
        default_date = datetime.now().date()
    elif hasattr(default_date, 'date'):
        default_date = default_date.date()
    
    state_key = f"{key}_selected"
    if state_key not in st.session_state:
        st.session_state[state_key] = default_date
    
    st.markdown(f"**{label}**")
    
    try:
        selected_date = st.date_input(
            "Tarih seçin veya yazın (gg.aa.yyyy)",
            value=st.session_state[state_key],
            min_value=min_date,
            max_value=max_date,
            format="DD.MM.YYYY",
            key=f"{key}_datepicker"
        )
    except:
        selected_date = st.date_input(
            "Tarih seçin veya yazın",
            value=st.session_state[state_key],
            min_value=min_date,
            max_value=max_date,
            key=f"{key}_datepicker"
        )
    
    if selected_date != st.session_state[state_key]:
        st.session_state[state_key] = selected_date
        st.rerun()
    
    gun_adi = TURKISH_DAYS[st.session_state[state_key].weekday()]
    ay_adi = TURKISH_MONTHS[st.session_state[state_key].month - 1]
    st.caption(f"📅 **{st.session_state[state_key].day} {ay_adi} {st.session_state[state_key].year} ({gun_adi})**")
    
    return st.session_state[state_key]

# ===================== GİRİŞ =====================
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "login_counter" not in st.session_state:
        st.session_state.login_counter = 0
    
    if st.session_state.authenticated:
        return True
    
    st.markdown("""<style>
        .login-box { max-width:400px; margin:80px auto; padding:2rem; background:white; 
                    border-radius:20px; box-shadow:0 20px 60px rgba(0,0,0,0.15); text-align:center; }
    </style>""", unsafe_allow_html=True)
    
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.markdown("### 🔐 BIST Sinyal Tarama Pro")
    st.markdown("#### Yetkili Giriş")
    
    msg = st.empty()
    user = st.text_input("👤 Kullanıcı", key=f"u_{st.session_state.login_counter}")
    pwd = st.text_input("🔒 Şifre", type="password", key=f"p_{st.session_state.login_counter}")
    
    if st.button("🚀 GİRİŞ", use_container_width=True, type="primary", key=f"b_{st.session_state.login_counter}"):
        if user == "ADMIN" and pwd == "Elma*":
            st.session_state.authenticated = True
            msg.success("✅ Başarılı!")
            time.sleep(0.3)
            st.rerun()
        else:
            st.session_state.login_counter += 1
            msg.error("❌ Hatalı!")
            time.sleep(0.3)
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    return False

# ===================== CSS =====================
st.markdown("""<style>
    .header { font-size:1.8rem; font-weight:700; text-align:center; padding:1rem;
              background:linear-gradient(135deg,#667eea,#764ba2); color:white;
              border-radius:15px; margin-bottom:1.5rem; }
    .trend-up { background:#d4edda; color:#155724; padding:8px 15px; border-radius:20px; font-weight:bold; }
    .trend-flat { background:#fff3cd; color:#856404; padding:8px 15px; border-radius:20px; font-weight:bold; }
    .trend-down { background:#f8d7da; color:#721c24; padding:8px 15px; border-radius:20px; font-weight:bold; }
</style>""", unsafe_allow_html=True)

# ===================== SABİTLER =====================
LOOKBACK, STEPS, WORKERS = 200, [5,10,15,30,60,90], 10

# ===================== TREND FİLTRELERİ =====================
TREND_FILTERS = {
    "📈 Yükselen": {
        'tight_filters': {
            'Min_Perf_Score': 70,
            'Max_RSI': 52, 'Min_RSI': 38,
            'Max_ADX': 38, 'Min_ADX': 15,
            'Min_Volume_MA': 0.6, 'Max_Volume_MA': 1.4,
            'Max_MFI': 61, 'Min_MFI': 45,
            'Max_Stochastic': 58, 'Min_Stochastic': 5,
            'Max_BB_Position': 0.55, 'Min_BB_Position': 0.07,
        },
        'desc': '📈 Yükselen piyasa - Dengeli sıkı filtreler'
    },
    "📊 Yatay": {
        'tight_filters': {
            'Min_Perf_Score': 75,
            'Max_RSI': 50, 'Min_RSI': 40,
            'Max_ADX': 35, 'Min_ADX': 18,
            'Min_Volume_MA': 0.7, 'Max_Volume_MA': 1.3,
            'Max_MFI': 60, 'Min_MFI': 48,
            'Max_Stochastic': 50, 'Min_Stochastic': 5,
            'Max_BB_Position': 0.5, 'Min_BB_Position': 0.1,
        },
        'desc': '📊 Yatay piyasa - Daha sıkı filtreler'
    },
    "📉 Düşen": {
        'tight_filters': {
            'Min_Perf_Score': 80,
            'Max_RSI': 48, 'Min_RSI': 40,
            'Max_ADX': 30, 'Min_ADX': 20,
            'Min_Volume_MA': 0.8, 'Max_Volume_MA': 1.2,
            'Max_MFI': 60, 'Min_MFI': 50,
            'Max_Stochastic': 40, 'Min_Stochastic': 5,
            'Max_BB_Position': 0.45, 'Min_BB_Position': 0.15,
        },
        'desc': '📉 Düşen piyasa - En sıkı filtreler'
    }
}

# ===================== PİYASA TRENDİ TESPİTİ =====================
@st.cache_data(ttl=300)  # 5 dakika cache
def detect_market_trend():
    """BIST100 endeksinin trendini tespit et: Yükselen/Yatay/Düşen"""
    try:
        # XU100 endeksini çek
        ticker = bp.Ticker("XU100.IS")
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        df = ticker.history(start=start, end=end)
        
        if df is None or len(df) < 25:
            return "📈 Yükselen"  # Varsayılan
        
        df = df.reset_index()
        date_col = None
        for c in df.columns:
            if 'date' in c.lower() or 'index' in c.lower():
                date_col = c
                break
        if date_col is None:
            date_col = df.columns[0]
        
        df = df.rename(columns={date_col: 'Date'})
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Kapanış kolonunu bul
        close_col = None
        for c in df.columns:
            if 'close' in c.lower() or 'kapanis' in c.lower():
                close_col = c
                break
        if close_col is None:
            close_col = df.columns[-1]  # Son kolonu kapanış varsay
        
        closes = pd.to_numeric(df[close_col], errors='coerce').dropna()
        
        if len(closes) < 25:
            return "📈 Yükselen"
        
        # Son kapanış ve MA20
        last_close = closes.iloc[-1]
        ma20 = closes.rolling(20).mean().iloc[-1]
        
        # Trend belirleme
        diff_pct = ((last_close - ma20) / ma20) * 100
        
        if diff_pct > 2:
            return "📈 Yükselen"
        elif diff_pct < -2:
            return "📉 Düşen"
        else:
            return "📊 Yatay"
    except:
        return "📈 Yükselen"  # Hata durumunda varsayılan

# ===================== STRATEJİ PROFİLLERİ =====================
STRATEGY_PRESETS = {
    "🎯 Üç Aşamalı Dinamik": {
        'strategy': {
            'RSI_max': 70, 'RSI_min': 20,
            'MA200_diff_min': -35, 'MA200_diff_max': 30,
            'Stochastic_max': 85, 'Stochastic_min': 0,
            'ADX_min': 3, 'ADX_max': 50,
            'Volume_MA_ratio': 0.3, 'Volume_MA_max': 5.0,
            'MFI_max': 75, 'MFI_min': 20,
        },
        'mid_filters': {
            'Min_Perf_Score': 50,
            'Max_RSI': 55, 'Min_RSI': 35,
            'Max_ADX': 42, 'Min_ADX': 10,
            'Min_Volume_MA': 0.5, 'Max_Volume_MA': 2.0,
        },
        'support_filters': {
            'Max_MFI': 68, 'Min_MFI': 35,
            'Max_Stochastic': 70, 'Min_Stochastic': 5,
            'Max_BB_Position': 0.7, 'Min_BB_Position': 0.05,
        },
        # tight_filters trend'e göre dinamik olarak eklenecek
        'desc': '🎯 Dinamik trend filtreli - Piyasa şartlarına otomatik uyum sağlar'
    },
    "📊 Dengeli": {
        'strategy': {
            'RSI_max': 65, 'RSI_min': 25, 'MA200_diff_min': -30, 'MA200_diff_max': 20,
            'Stochastic_max': 80, 'Stochastic_min': 0, 'ADX_min': 3, 'ADX_max': 45,
            'Volume_MA_ratio': 0.5, 'MFI_max': 70, 'MFI_min': 25,
        },
        'filters': {
            'Min_Perf_Score': 55, 'Max_RSI': 62, 'Max_ADX': 45,
            'Min_Volume_MA': 0.6, 'Max_MFI': 68,
        },
        'desc': '📊 Orta seviye filtreler, dengeli sinyal sayısı ve kalite.'
    },
}

# ===================== VERİ & GÖSTERGELER =====================
@st.cache_data(ttl=3600)
def get_lists():
    try:
        b30 = sorted(set(bp.Index("XU030").component_symbols))
        b50 = sorted(set(bp.Index("XU050").component_symbols))
        b100 = sorted(set(bp.Index("XU100").component_symbols))
        return {'BIST30':b30, 'BIST50':b50, 'BIST100':b100, 'Takip':["ASELS","THYAO","SISE","EREGL","BIMAS"]}
    except:
        return {'Takip':["ASELS","THYAO","SISE","EREGL","BIMAS"]}

def get_data(symbol, date_str):
    try:
        ref = pd.to_datetime(date_str)
        sym = symbol.upper().strip()
        if not sym.endswith(".IS"): sym += ".IS"
        
        start = (ref - timedelta(days=LOOKBACK*2)).strftime('%Y-%m-%d')
        end = (ref + timedelta(days=LOOKBACK)).strftime('%Y-%m-%d')
        
        ticker = bp.Ticker(sym)
        df = ticker.history(start=start, end=end)
        
        if df is None or len(df) == 0:
            return None
        
        df = df.reset_index()
        
        date_col = None
        for c in df.columns:
            col_name = str(c).lower()
            if 'date' in col_name or 'index' in col_name or 'tarih' in col_name:
                date_col = c
                break
        
        if date_col is None:
            date_col = df.columns[0]
        
        df = df.rename(columns={date_col: 'Date'})
        
        try:
            df['Date'] = pd.to_datetime(df['Date'])
        except:
            try:
                df['Date'] = pd.to_datetime(df['Date'], unit='s')
            except:
                try:
                    df['Date'] = pd.to_datetime(df['Date'], unit='ms')
                except:
                    return None
        
        if hasattr(df['Date'].iloc[0], 'tz') and df['Date'].iloc[0].tz is not None:
            df['Date'] = df['Date'].dt.tz_localize(None)
        
        col_map = {}
        for c in df.columns:
            cl = str(c).lower()
            if 'open' in cl: col_map[c] = 'Open'
            elif 'high' in cl: col_map[c] = 'High'
            elif 'low' in cl: col_map[c] = 'Low'
            elif 'close' in cl or 'kapanis' in cl: col_map[c] = 'Close'
            elif 'volume' in cl or 'hacim' in cl: col_map[c] = 'Volume'
        
        if 'Close' not in col_map.values():
            remaining = [c for c in df.columns if c != 'Date']
            if len(remaining) >= 4:
                col_map = {
                    remaining[0]: 'Open', remaining[1]: 'High',
                    remaining[2]: 'Low', remaining[3]: 'Close'
                }
                if len(remaining) >= 5:
                    col_map[remaining[4]] = 'Volume'
        
        df = df.rename(columns=col_map)
        
        if not all(c in df.columns for c in ['Date', 'Open', 'High', 'Low', 'Close']):
            return None
        
        if 'Volume' not in df.columns:
            df['Volume'] = 0
        
        result = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            result[col] = pd.to_numeric(result[col], errors='coerce').astype(float)
        
        result = result.sort_values('Date').reset_index(drop=True)
        result = result.dropna(subset=['Open', 'High', 'Low', 'Close'])
        
        return result
    except:
        return None

def calc_indicators(df):
    if df is None or len(df) < 200:
        return None
    
    df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
    
    clean_df = pd.DataFrame()
    clean_df['Date'] = df['Date'].values
    clean_df['Open'] = df['Open'].values.astype(float)
    clean_df['High'] = df['High'].values.astype(float)
    clean_df['Low'] = df['Low'].values.astype(float)
    clean_df['Close'] = df['Close'].values.astype(float)
    clean_df['Volume'] = df['Volume'].values.astype(float)
    
    for p in [5,10,20,50,100,200]:
        clean_df[f'MA{p}'] = clean_df['Close'].rolling(p).mean()
        clean_df[f'VMA{p}'] = clean_df['Volume'].rolling(p).mean()
    
    d = clean_df['Close'].diff()
    g = d.where(d>0,0).rolling(14).mean()
    l = (-d.where(d<0,0)).rolling(14).mean()
    clean_df['RSI'] = 100-(100/(1+g/l))
    
    clean_df['Stochastic'] = 100*(clean_df['Close']-clean_df['Low'].rolling(14).min())/(clean_df['High'].rolling(14).max()-clean_df['Low'].rolling(14).min())
    
    tr = np.maximum(clean_df['High']-clean_df['Low'], np.maximum(abs(clean_df['High']-clean_df['Close'].shift()), abs(clean_df['Low']-clean_df['Close'].shift())))
    atr = pd.Series(tr).rolling(14).mean()
    dp = np.where((clean_df['High']-clean_df['High'].shift())>(clean_df['Low'].shift()-clean_df['Low']), np.maximum(clean_df['High']-clean_df['High'].shift(),0),0)
    dm = np.where((clean_df['Low'].shift()-clean_df['Low'])>(clean_df['High']-clean_df['High'].shift()), np.maximum(clean_df['Low'].shift()-clean_df['Low'],0),0)
    
    di_plus = 100*(pd.Series(dp).rolling(14).mean()/atr)
    di_minus = 100*(pd.Series(dm).rolling(14).mean()/atr)
    clean_df['ADX'] = (100*(abs(di_plus-di_minus)/(di_plus+di_minus))).rolling(14).mean()
    
    clean_df['VolRatio'] = clean_df['Volume']/clean_df['VMA20']
    
    tp = (clean_df['High']+clean_df['Low']+clean_df['Close'])/3
    mf = tp*clean_df['Volume']
    pf = mf.where(tp>tp.shift(),0).rolling(14).sum()
    nf = mf.where(tp<tp.shift(),0).rolling(14).sum()
    clean_df['MFI'] = 100-(100/(1+pf/nf))
    
    clean_df['BB_Mid'] = clean_df['Close'].rolling(20).mean()
    clean_df['BB_Std'] = clean_df['Close'].rolling(20).std()
    clean_df['BB_Upper'] = clean_df['BB_Mid'] + 2 * clean_df['BB_Std']
    clean_df['BB_Lower'] = clean_df['BB_Mid'] - 2 * clean_df['BB_Std']
    clean_df['BB_Position'] = (clean_df['Close'] - clean_df['BB_Lower']) / (clean_df['BB_Upper'] - clean_df['BB_Lower'])
    
    return clean_df

def score_stock(r):
    s = 0
    rs = r['RSI']
    if 38 <= rs <= 42: s += 30
    elif 42 < rs <= 48: s += 28
    elif 48 < rs <= 52: s += 22
    elif 35 <= rs < 38: s += 15
    elif 52 < rs <= 55: s += 10
    else: s += 3
    
    ad = r['ADX']
    if 14 <= ad < 20: s += 30
    elif 20 <= ad < 25: s += 28
    elif 25 <= ad < 30: s += 22
    elif 30 <= ad <= 38: s += 15
    else: s += 5
    
    vl = r['VolRatio']
    if 0.8 <= vl <= 1.2: s += 25
    elif 0.6 <= vl < 0.8: s += 20
    elif 1.2 < vl <= 1.4: s += 18
    else: s += 5
    
    mf = r['MFI']
    if 48 <= mf <= 58: s += 18
    elif 45 <= mf <= 61: s += 12
    else: s += 3
    
    stoch = r.get('Stochastic', 50)
    if 4 <= stoch <= 30: s += 15
    elif 30 < stoch <= 58: s += 8
    
    bb_pos = r.get('BB_Position', 0.5)
    if 0.07 <= bb_pos <= 0.3: s += 12
    elif 0.3 < bb_pos <= 0.55: s += 6
    
    return min(s, 100)

def check_signal(df, i, strategy, filters):
    try:
        rsi = df['RSI'].iloc[i]
        if pd.isna(rsi) or rsi > strategy['RSI_max'] or rsi < strategy['RSI_min']:
            return False
        
        if pd.isna(df['MA200'].iloc[i]):
            return False
        ma200_diff = ((df['Close'].iloc[i] - df['MA200'].iloc[i]) / df['MA200'].iloc[i]) * 100
        if ma200_diff < strategy['MA200_diff_min'] or ma200_diff > strategy['MA200_diff_max']:
            return False
        
        stoch = df['Stochastic'].iloc[i]
        stoch_min = strategy.get('Stochastic_min', 0)
        if pd.isna(stoch) or stoch > strategy['Stochastic_max'] or stoch < stoch_min:
            return False
        
        adx = df['ADX'].iloc[i]
        adx_max = strategy.get('ADX_max', 100)
        if pd.isna(adx) or adx < strategy['ADX_min'] or adx > adx_max:
            return False
        
        vol = df['VolRatio'].iloc[i]
        vol_max = strategy.get('Volume_MA_max', 999)
        if pd.isna(vol) or vol < strategy['Volume_MA_ratio'] or vol > vol_max:
            return False
        
        mfi = df['MFI'].iloc[i]
        mfi_min = strategy.get('MFI_min', 0)
        if pd.isna(mfi) or mfi > strategy['MFI_max'] or mfi < mfi_min:
            return False
        
        return True
    except:
        return False

def apply_filter(r, filters):
    if 'Max_RSI' in filters and r['RSI'] > filters['Max_RSI']: return False
    if 'Min_RSI' in filters and r['RSI'] < filters['Min_RSI']: return False
    if 'Max_ADX' in filters and r['ADX'] > filters['Max_ADX']: return False
    if 'Min_ADX' in filters and r['ADX'] < filters['Min_ADX']: return False
    if r['VolRatio'] < filters.get('Min_Volume_MA', 0): return False
    if 'Max_Volume_MA' in filters and r['VolRatio'] > filters['Max_Volume_MA']: return False
    if 'Max_MFI' in filters and r['MFI'] > filters['Max_MFI']: return False
    if 'Min_MFI' in filters and r['MFI'] < filters['Min_MFI']: return False
    if 'Max_Stochastic' in filters and r.get('Stochastic', 0) > filters['Max_Stochastic']: return False
    if 'Min_Stochastic' in filters and r.get('Stochastic', 100) < filters['Min_Stochastic']: return False
    if 'Max_BB_Position' in filters and r.get('BB_Position', 0) > filters['Max_BB_Position']: return False
    if 'Min_BB_Position' in filters and r.get('BB_Position', 1) < filters['Min_BB_Position']: return False
    if r['Perf_Skor'] < filters.get('Min_Perf_Score', 0): return False
    return True

def scan_stock(sym, date_str, strategy, filters, mid_filters=None, support_filters=None, tight_filters=None):
    try:
        df = get_data(sym, date_str)
        if df is None: return None
        
        df = calc_indicators(df)
        if df is None: return None
        
        ref = pd.to_datetime(date_str).normalize()
        dates = df['Date'].dt.normalize()
        idx = next((i for i,d in enumerate(dates) if d>=ref), None)
        if idx is None: return None
        
        if not check_signal(df, idx, strategy, filters): return None
        
        cur = df['Close'].iloc[idx]
        r = {
            'Hisse': sym,
            'Tarih': df.iloc[idx]['Date'].strftime('%Y-%m-%d'),
            'Kapanis': round(cur, 2),
            'RSI': round(df['RSI'].iloc[idx], 1),
            'ADX': round(df['ADX'].iloc[idx], 1),
            'VolRatio': round(df['VolRatio'].iloc[idx], 2),
            'MFI': round(df['MFI'].iloc[idx], 1),
            'Stochastic': round(df['Stochastic'].iloc[idx], 1),
            'BB_Position': round(df['BB_Position'].iloc[idx], 2),
        }
        
        if pd.notna(df['MA200'].iloc[idx]):
            r['MA200_Mesafe%'] = round(((cur - df['MA200'].iloc[idx]) / df['MA200'].iloc[idx]) * 100, 1)
        
        r['Perf_Skor'] = score_stock(r)
        
        # 2A - Temel Süzgeç
        if mid_filters and not apply_filter(r, mid_filters): return None
        
        # 2B - Destek Süzgeç
        if support_filters and not apply_filter(r, support_filters): return None
        
        # 3. Aşama - Trend'e göre dinamik sıkı filtre
        if tight_filters and not apply_filter(r, tight_filters): return None
        
        # Forward getiriler
        for s in STEPS:
            if idx + s < len(df):
                future_close = df['Close'].iloc[idx + s]
                if pd.notna(future_close) and cur != 0:
                    r[f'+{s}G_Getiri%'] = round(((future_close - cur) / cur) * 100, 2)
                else:
                    r[f'+{s}G_Getiri%'] = None
            else:
                r[f'+{s}G_Getiri%'] = None
        
        return r
    except:
        return None

def run_scan(symbols, date, strategy, filters, mid_filters=None, support_filters=None, tight_filters=None):
    results = []
    ds = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scan_stock, s, ds, strategy, filters, mid_filters, support_filters, tight_filters):s for s in symbols}
        for f in as_completed(futures):
            try:
                r = f.result()
                if r: results.append(r)
            except:
                pass
    return results

def get_bdays(start, end):
    days = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days

def get_last_business_day():
    """Son işlem gününü bul"""
    today = datetime.now().date()
    # Bugün hafta sonu ise Cuma'ya git
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    # Bugünün verisi henüz oluşmamış olabilir, dünü al
    yesterday = today - timedelta(days=1)
    while yesterday.weekday() >= 5:
        yesterday -= timedelta(days=1)
    return yesterday

# ===================== ANA UYGULAMA =====================
def main():
    if not check_password():
        return
    
    defaults = {
        "strategy_preset": "🎯 Üç Aşamalı Dinamik",
        "df": None, "ok": False, "t": 0, "days": 0,
        "selected_trend": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    
    # Otomatik trend tespiti
    auto_trend = detect_market_trend()
    
    c1, c2, c3 = st.columns([6,1,1])
    with c1: st.markdown('<div class="header">📈 BIST SİNYAL TARAMA PRO - DİNAMİK TREND</div>', unsafe_allow_html=True)
    with c2:
        if st.button("🔄 Sıfırla", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    with c3:
        if st.button("🚪 ÇIKIŞ", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    # Trend göstergesi
    trend_colors = {"📈 Yükselen": "trend-up", "📊 Yatay": "trend-flat", "📉 Düşen": "trend-down"}
    auto_color = trend_colors.get(auto_trend, "trend-up")
    st.markdown(f'<span class="{auto_color}">🤖 Otomatik Trend: {auto_trend}</span>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.markdown("### ⚙️ AYARLAR")
        
        preset = st.selectbox("🎯 Strateji Profili", list(STRATEGY_PRESETS.keys()), 
                             index=list(STRATEGY_PRESETS.keys()).index(st.session_state.strategy_preset))
        st.session_state.strategy_preset = preset
        
        strategy = STRATEGY_PRESETS[preset]['strategy']
        filters = STRATEGY_PRESETS[preset].get('filters', {})
        mid_filters = STRATEGY_PRESETS[preset].get('mid_filters', None)
        support_filters = STRATEGY_PRESETS[preset].get('support_filters', None)
        
        st.markdown("---")
        
        # === TREND SEÇİMİ ===
        st.markdown("### 📊 Piyasa Trendi")
        
        trend_options = list(TREND_FILTERS.keys())
        # Varsayılan: otomatik tespit edilen
        default_index = trend_options.index(auto_trend) if auto_trend in trend_options else 0
        
        selected_trend = st.selectbox(
            "Trend Seçimi",
            trend_options,
            index=default_index,
            help="Otomatik tespit edilen trendi değiştirebilirsiniz"
        )
        
        if selected_trend != auto_trend:
            st.info(f"👤 Manuel seçim: {selected_trend}")
        
        # Seçilen trende göre tight_filters
        tight_filters = TREND_FILTERS[selected_trend]['tight_filters']
        st.caption(TREND_FILTERS[selected_trend]['desc'])
        
        with st.expander("📋 Trend Filtre Detayı"):
            st.markdown(f"**Trend: {selected_trend}**")
            st.markdown(f"- RSI: {tight_filters.get('Min_RSI', '-')}-{tight_filters.get('Max_RSI', '-')}")
            st.markdown(f"- ADX: {tight_filters.get('Min_ADX', '-')}-{tight_filters.get('Max_ADX', '-')}")
            st.markdown(f"- VolRatio: {tight_filters.get('Min_Volume_MA', '-')}-{tight_filters.get('Max_Volume_MA', '-')}x")
            st.markdown(f"- MFI: {tight_filters.get('Min_MFI', '-')}-{tight_filters.get('Max_MFI', '-')}")
            st.markdown(f"- Stochastic: {tight_filters.get('Min_Stochastic', '-')}-{tight_filters.get('Max_Stochastic', '-')}")
            st.markdown(f"- BB: {tight_filters.get('Min_BB_Position', '-')}-{tight_filters.get('Max_BB_Position', '-')}")
            st.markdown(f"- Skor > {tight_filters.get('Min_Perf_Score', '-')}")
        
        st.markdown("---")
        
        lists = get_lists()
        secim = st.selectbox("Liste", list(lists.keys()))
        symbols = lists[secim]
        st.caption(f"{len(symbols)} hisse")
        
        st.markdown("### 📅 Tarama Aralığı")
        tip = st.radio("Tip", ["Bugün", "Tek Tarih", "Tarih Aralığı", "Ay"], horizontal=True)
        
        if tip == "Bugün":
            # Otomatik olarak son işlem gününü bul
            last_bday = get_last_business_day()
            d = last_bday
            start = end = d
            st.caption(f"📅 Son işlem günü: **{d.strftime('%d.%m.%Y')}** ({TURKISH_DAYS[d.weekday()]})")
        elif tip == "Tek Tarih":
            d = turkish_date_picker("Tarih Seçin", datetime(2026, 7, 1), "tek")
            start = end = d
        elif tip == "Tarih Aralığı":
            c1, c2 = st.columns(2)
            with c1: start = turkish_date_picker("Başlangıç", datetime(2026, 7, 1), "bas")
            with c2: end = turkish_date_picker("Bitiş", datetime(2026, 7, 31), "bit")
        else:
            c1, c2 = st.columns(2)
            with c1: y = st.selectbox("Yıl", range(2020, 2031), index=6, key="yy")
            with c2: m = st.selectbox("Ay", range(1, 13), format_func=lambda x: TURKISH_MONTHS[x-1], index=6, key="mm")
            start = datetime(y, m, 1).date()
            end = (datetime(y, m+1, 1) if m < 12 else datetime(y+1, 1, 1)).date() - timedelta(days=1)
        
        bdays = get_bdays(pd.to_datetime(start), pd.to_datetime(end))
        days = len(bdays)
        
        st.markdown("---")
        st.markdown(f"📊 **{days}** işlem günü | 📋 **{len(symbols)}** hisse")
        st.markdown(f"⏱️ ~**{days*len(symbols)*0.08/WORKERS:.0f}s**")
        
        btn = st.button("🔍 TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        
        with st.spinner(f'🔍 {days} gün taranıyor... Trend: {selected_trend}'):
            all_signals = []
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | {i+1}/{days}")
                res = run_scan(symbols, day, strategy, filters, mid_filters, support_filters, tight_filters)
                if res:
                    all_signals.extend(res)
                bar.progress((i+1)/days)
            
            bar.empty()
            txt.empty()
        
        if all_signals:
            df = pd.DataFrame(all_signals)
            df = df.sort_values('Perf_Skor', ascending=False)
            
            st.session_state.df = df
            st.session_state.ok = True
            st.session_state.t = time.time() - t0
            st.session_state.days = days
        else:
            st.warning("⚠️ Sinyal bulunamadı!")
            st.session_state.ok = False
    
    if st.session_state.get('ok'):
        df = st.session_state.df
        
        st.markdown(f"### 📊 {len(df)} Sinyal | ⚡ {st.session_state.t:.1f}s | 📅 {st.session_state.days} gün | Trend: {selected_trend}")
        
        c1, c2, c3, c4 = st.columns(4)
        
        with c1: st.metric("Sinyal", len(df))
        with c2: st.metric("Ort. Skor", f"{df['Perf_Skor'].mean():.0f}")
        
        r30 = df.get('+30G_Getiri%', pd.Series(dtype=float)).dropna()
        with c3:
            st.metric("30G Ort. Getiri", f"%{r30.mean():.1f}" if len(r30) > 0 else "Veri Yok")
        with c4:
            if len(r30) > 0:
                st.metric("30G Kazanma", f"%{(r30>0).sum()/len(r30)*100:.0f}")
            else:
                st.metric("30G Kazanma", "Veri Yok")
        
        st.markdown("### 📋 Sinyaller")
        st.dataframe(df, use_container_width=True, height=500)
        
        if '+30G_Getiri%' in df.columns and len(r30) > 0:
            col1, col2 = st.columns(2)
            with col1:
                fig = go.Figure()
                fig.add_trace(go.Histogram(x=r30, nbinsx=20, marker_color='#667eea'))
                fig.add_vline(x=0, line_dash="dash", line_color="red")
                fig.add_vline(x=r30.mean(), line_dash="dash", line_color="green")
                fig.update_layout(title="30G Getiri Dağılımı", xaxis_title="% Getiri", yaxis_title="Sinyal", showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                win_rate = (r30 > 0).sum() / len(r30) * 100
                st.markdown(f"""
                **30G İstatistikleri:**
                - Ortalama: **%{r30.mean():.1f}**
                - Medyan: %{r30.median():.1f}
                - Maks: %{r30.max():.1f} | Min: %{r30.min():.1f}
                - Kazanma: **%{win_rate:.0f}**
                - Risk/Getiri: {r30.mean()/r30.std():.2f}
                """)
        
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📊 CSV", df.to_csv(index=False), "sinyaller.csv", "text/csv")
        with c2:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w:
                df.to_excel(w, index=False)
            st.download_button("📑 Excel", buf.getvalue(), "sinyaller.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    elif not btn:
        st.markdown("### 🚀 Hoş Geldiniz!")
        st.markdown(f"""
        **🎯 Dinamik Trend Filtreli Strateji:**
        
        🤖 Otomatik Trend Tespiti: **{auto_trend}**
        
        | Trend | RSI | ADX | VolRatio | MFI | Stoch |
        |-------|-----|-----|----------|-----|-------|
        | 📈 Yükselen | 38-52 | 15-38 | 0.6-1.4 | 45-61 | 5-58 |
        | 📊 Yatay | 40-50 | 18-35 | 0.7-1.3 | 48-60 | 5-50 |
        | 📉 Düşen | 40-48 | 20-30 | 0.8-1.2 | 50-60 | 5-40 |
        
        **📅 Bugün** seçeneği ile otomatik son işlem gününü tarayabilirsiniz.
        """)

if __name__ == "__main__":
    main()
