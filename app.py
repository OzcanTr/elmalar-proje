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
    st.info("💡 **Demo:** Kullanıcı: `ADMIN` | Şifre: `Elma*`")
    return False

# ===================== CSS =====================
st.markdown("""<style>
    .header { font-size:1.8rem; font-weight:700; text-align:center; padding:1rem;
              background:linear-gradient(135deg,#667eea,#764ba2); color:white;
              border-radius:15px; margin-bottom:1.5rem; }
</style>""", unsafe_allow_html=True)

# ===================== SABİTLER =====================
LOOKBACK, STEPS, WORKERS = 200, [5,10,15,30,60,90], 10

DEFAULT_STRATEGY = {
    'RSI_max': 65,
    'RSI_min': 25,
    'MA200_diff_min': -30,
    'MA200_diff_max': 20,
    'Stochastic_max': 80,
    'ADX_min': 3,
    'Volume_MA_ratio': 0.5,
    'MFI_max': 70,
    'MACD_Hist_Up': False,
}

DEFAULT_FILTERS = {
    'Min_Perf_Score': 55,
    'Max_RSI': 62,
    'Max_ADX': 45,
    'Min_Volume_MA': 0.6,
    'Max_MFI': 68,
    'Min_MACD_Hist': -0.1,
    'Max_BB_Position': 0.7,
}

STRATEGY_PRESETS = {
    "Dengeli (Önerilen)": {
        'strategy': DEFAULT_STRATEGY.copy(),
        'filters': DEFAULT_FILTERS.copy()
    },
    "Agresif (Çok Sinyal)": {
        'strategy': {**DEFAULT_STRATEGY, 'RSI_max': 70, 'MA200_diff_max': 30, 'Volume_MA_ratio': 0.3},
        'filters': {**DEFAULT_FILTERS, 'Min_Perf_Score': 45, 'Max_RSI': 65, 'Min_Volume_MA': 0.4, 'Max_MFI': 72}
    },
    "Muhafazakar (Az Sinyal)": {
        'strategy': {**DEFAULT_STRATEGY, 'RSI_max': 60, 'MA200_diff_max': 10, 'Volume_MA_ratio': 0.8},
        'filters': {**DEFAULT_FILTERS, 'Min_Perf_Score': 70, 'Max_RSI': 55, 'Min_Volume_MA': 1.0, 'Max_MFI': 60}
    }
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
                    remaining[0]: 'Open',
                    remaining[1]: 'High',
                    remaining[2]: 'Low',
                    remaining[3]: 'Close'
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
    
    ema12 = clean_df['Close'].ewm(span=12).mean()
    ema26 = clean_df['Close'].ewm(span=26).mean()
    clean_df['MACD'] = ema12 - ema26
    clean_df['MACD_Signal'] = clean_df['MACD'].ewm(span=9).mean()
    clean_df['MACD_Hist'] = clean_df['MACD'] - clean_df['MACD_Signal']
    clean_df['MACD_Hist_Up'] = clean_df['MACD_Hist'] > clean_df['MACD_Hist'].shift(1)
    
    clean_df['BB_Mid'] = clean_df['Close'].rolling(20).mean()
    clean_df['BB_Std'] = clean_df['Close'].rolling(20).std()
    clean_df['BB_Upper'] = clean_df['BB_Mid'] + 2 * clean_df['BB_Std']
    clean_df['BB_Lower'] = clean_df['BB_Mid'] - 2 * clean_df['BB_Std']
    clean_df['BB_Position'] = (clean_df['Close'] - clean_df['BB_Lower']) / (clean_df['BB_Upper'] - clean_df['BB_Lower'])
    
    clean_df['OBV'] = (np.sign(clean_df['Close'].diff()) * clean_df['Volume']).cumsum()
    clean_df['OBV_MA'] = clean_df['OBV'].rolling(20).mean()
    clean_df['OBV_Trend'] = clean_df['OBV'] > clean_df['OBV_MA']
    
    return clean_df

def score_stock(r):
    s = 0
    rs = r['RSI']
    if 30 <= rs <= 40: s += 30
    elif 40 < rs <= 50: s += 25
    elif 50 < rs <= 55: s += 20
    elif 55 < rs <= 60: s += 15
    elif 25 <= rs < 30: s += 15
    else: s += 5
    
    ad = r['ADX']
    if ad < 15: s += 30
    elif 15 <= ad < 20: s += 25
    elif 20 <= ad < 25: s += 20
    elif 25 <= ad < 30: s += 15
    else: s += 5
    
    vl = r['VolRatio']
    if vl > 2.5: s += 25
    elif vl > 1.8: s += 22
    elif vl > 1.2: s += 18
    elif vl > 1.0: s += 12
    elif vl > 0.8: s += 8
    elif vl > 0.6: s += 5
    else: s += 2
    
    mf = r['MFI']
    if 40 <= mf <= 55: s += 15
    elif 35 <= mf <= 60: s += 12
    elif 30 <= mf <= 65: s += 8
    elif 25 <= mf <= 68: s += 5
    else: s += 2
    
    bb_pos = r.get('BB_Position', 0.5)
    if 0.0 <= bb_pos <= 0.2: s += 12
    elif 0.2 < bb_pos <= 0.4: s += 8
    elif 0.4 < bb_pos <= 0.6: s += 5
    
    if r.get('OBV_Trend', False): s += 5
    
    ma200_dist = r.get('MA200_Mesafe%', 0)
    if -10 <= ma200_dist <= 5: s += 8
    elif 5 < ma200_dist <= 15: s += 5
    
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
        if pd.isna(stoch) or stoch > strategy['Stochastic_max']:
            return False
        
        adx = df['ADX'].iloc[i]
        if pd.isna(adx) or adx < strategy['ADX_min']:
            return False
        
        vol = df['VolRatio'].iloc[i]
        if pd.isna(vol) or vol < strategy['Volume_MA_ratio']:
            return False
        
        mfi = df['MFI'].iloc[i]
        if pd.isna(mfi) or mfi > strategy['MFI_max']:
            return False
        
        return True
    except:
        return False

def scan_stock(sym, date_str, strategy, filters):
    try:
        df = get_data(sym, date_str)
        if df is None: return None
        
        df = calc_indicators(df)
        if df is None: return None
        
        ref = pd.to_datetime(date_str).normalize()
        dates = df['Date'].dt.normalize()
        idx = next((i for i,d in enumerate(dates) if d>=ref), None)
        if idx is None or not check_signal(df, idx, strategy, filters): return None
        
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
        
        for s in STEPS:
            if idx+s < len(df):
                r[f'+{s}G_Getiri%'] = round(((df['Close'].iloc[idx+s] - cur) / cur) * 100, 2)
        
        if r['RSI'] > filters['Max_RSI']: return None
        if r['ADX'] > filters['Max_ADX']: return None
        if r['VolRatio'] < filters['Min_Volume_MA']: return None
        if r['MFI'] > filters['Max_MFI']: return None
        if r['Perf_Skor'] < filters['Min_Perf_Score']: return None
        
        return r
    except:
        return None

def run_scan(symbols, date, strategy, filters):
    results = []
    ds = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scan_stock, s, ds, strategy, filters):s for s in symbols}
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

# ===================== ANA UYGULAMA =====================
def main():
    if not check_password():
        return
    
    defaults = {
        "strategy_preset": "Dengeli (Önerilen)",
        "df": None,
        "ok": False,
        "t": 0,
        "days": 0
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    
    c1, c2, c3 = st.columns([7,1,1])
    with c1: st.markdown('<div class="header">📈 BIST SİNYAL TARAMA PRO v2</div>', unsafe_allow_html=True)
    with c2:
        if st.button("🔄 Sıfırla", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    with c3:
        if st.button("🚪 ÇIKIŞ", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    with st.sidebar:
        st.markdown("### ⚙️ AYARLAR")
        
        preset = st.selectbox("🎯 Strateji Profili", list(STRATEGY_PRESETS.keys()), 
                             index=list(STRATEGY_PRESETS.keys()).index(st.session_state.strategy_preset))
        st.session_state.strategy_preset = preset
        
        strategy = STRATEGY_PRESETS[preset]['strategy']
        filters = STRATEGY_PRESETS[preset]['filters']
        
        st.caption({
            "Dengeli (Önerilen)": "📊 Orta seviye filtreler, dengeli sinyal sayısı",
            "Agresif (Çok Sinyal)": "🚀 Gevşek filtreler, daha fazla sinyal",
            "Muhafazakar (Az Sinyal)": "🛡️ Sıkı filtreler, yüksek kaliteli sinyaller"
        }[preset])
        
        st.markdown("---")
        
        lists = get_lists()
        secim = st.selectbox("Liste", list(lists.keys()))
        symbols = lists[secim]
        st.caption(f"{len(symbols)} hisse")
        
        st.markdown("### 📅 Tarama Aralığı")
        tip = st.radio("Tip", ["Tek Tarih", "Tarih Aralığı", "Ay"], horizontal=True)
        
        if tip == "Tek Tarih":
            d = turkish_date_picker("Tarih Seçin", datetime(2025,7,7), "tek")
            start = end = d
        elif tip == "Tarih Aralığı":
            c1, c2 = st.columns(2)
            with c1:
                start = turkish_date_picker("Başlangıç", datetime(2025,7,1), "bas")
            with c2:
                end = turkish_date_picker("Bitiş", datetime(2025,7,31), "bit")
        else:
            c1, c2 = st.columns(2)
            with c1: y = st.selectbox("Yıl", range(2020, 2031), index=5, key="yy")
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
        
        with st.spinner(f'🔍 {days} gün taranıyor...'):
            all_signals = []
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | {i+1}/{days}")
                res = run_scan(symbols, day, strategy, filters)
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
            st.warning("⚠️ Sinyal bulunamadı! Filtreleri gevşetmeyi deneyin (Agresif profil)")
            st.session_state.ok = False
    
    if st.session_state.get('ok'):
        df = st.session_state.df
        
        st.markdown(f"### 📊 {len(df)} Sinyal | ⚡ {st.session_state.t:.1f}s | 📅 {st.session_state.days} gün")
        
        # Metrikler
        c1, c2, c3, c4, c5 = st.columns(5)
        
        with c1:
            st.metric("Sinyal", len(df))
        with c2:
            st.metric("Ort. Skor", f"{df['Perf_Skor'].mean():.0f}")
        
        r30 = df['+30G_Getiri%'].dropna()
        with c3:
            st.metric("30G Ort. Getiri", f"%{r30.mean():.1f}" if len(r30) > 0 else "N/A")
        with c4:
            if len(r30) > 0:
                st.metric("30G Kazanma", f"%{(r30>0).sum()/len(r30)*100:.0f}")
            else:
                st.metric("30G Kazanma", "N/A")
        with c5:
            st.metric("Profil", st.session_state.strategy_preset.split()[0])
        
        # Tüm sinyaller tablosu - BASİT GÖSTERİM
        st.markdown("### 📋 Tüm Sinyaller")
        st.dataframe(df, use_container_width=True, height=500)
        
        # Getiri analizi
        if '+30G_Getiri%' in df.columns:
            returns_30 = df['+30G_Getiri%'].dropna()
            
            if len(returns_30) > 0:
                st.markdown("### 📈 Performans Analizi")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    fig = go.Figure()
                    fig.add_trace(go.Histogram(
                        x=returns_30, 
                        nbinsx=20, 
                        marker_color='#667eea',
                        name='Getiri Dağılımı'
                    ))
                    fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Başabaş")
                    fig.add_vline(x=returns_30.mean(), line_dash="dash", line_color="green", 
                                 annotation_text=f"Ort: %{returns_30.mean():.1f}")
                    fig.update_layout(
                        title="30 Günlük Getiri Dağılımı",
                        xaxis_title="% Getiri",
                        yaxis_title="Sinyal Sayısı",
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    win_rate = (returns_30 > 0).sum() / len(returns_30) * 100
                    avg_win = returns_30[returns_30 > 0].mean() if len(returns_30[returns_30 > 0]) > 0 else 0
                    avg_loss = returns_30[returns_30 < 0].mean() if len(returns_30[returns_30 < 0]) > 0 else 0
                    
                    st.markdown(f"""
                    **30 Günlük Getiri İstatistikleri:**
                    
                    | Metrik | Değer |
                    |--------|-------|
                    | Ortalama | **%{returns_30.mean():.1f}** |
                    | Medyan | %{returns_30.median():.1f} |
                    | Maksimum | %{returns_30.max():.1f} |
                    | Minimum | %{returns_30.min():.1f} |
                    | Std Sapma | %{returns_30.std():.1f} |
                    | Kazanma Oranı | **%{win_rate:.0f}** |
                    | Ort. Kazanç | %{avg_win:.1f} |
                    | Ort. Kayıp | %{avg_loss:.1f} |
                    | Risk/Getiri | {returns_30.mean()/returns_30.std():.2f} |
                    """)
        
        # En iyi 10
        st.markdown("### 🏆 En İyi 10 Sinyal")
        top10 = df.head(10)
        st.dataframe(top10, use_container_width=True)
        
        # Export
        st.markdown("### 💾 Dışa Aktar")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📊 CSV İndir", df.to_csv(index=False), f"sinyaller_{preset.split()[0].lower()}.csv", "text/csv")
        with c2:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w:
                df.to_excel(w, index=False)
            st.download_button("📑 Excel İndir", buf.getvalue(), f"sinyaller_{preset.split()[0].lower()}.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    elif not btn:
        st.markdown("### 🚀 Hoş Geldiniz!")
        st.markdown("""
        **Özellikler:**
        - 🎯 3 strateji profili (Dengeli / Agresif / Muhafazakar)
        - 📅 Tarih aralığı tarama
        - 📊 Performans analizi ve getiri histogramı
        - 📋 Tam sinyal dökümü
        - 💾 CSV/Excel export
        
        **Başlamak için** sidebar'dan ayarları yapıp **TARAMA BAŞLAT** butonuna tıklayın.
        """)

if __name__ == "__main__":
    main()
