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
import os
import uuid
from collections import defaultdict
import numpy as np

warnings.filterwarnings('ignore')

st.set_page_config(page_title="BIST Sinyal Olayı Backtest Motoru V2.1", page_icon="🎯", layout="wide")

# ===================== TEST MODU =====================
TEST_MODE = False

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
    st.markdown("### 🎯 BIST Sinyal Olayı Backtest Motoru V2.1")
    st.markdown("#### Yetkili Giriş")
    
    msg = st.empty()
    user = st.text_input("👤 Kullanıcı", key=f"u_{st.session_state.login_counter}")
    pwd = st.text_input("🔒 Şifre", type="password", key=f"p_{st.session_state.login_counter}")
    
    if st.button("🚀 GİRİŞ", use_container_width=True, type="primary", key=f"b_{st.session_state.login_counter}"):
        try:
            correct_user = st.secrets["USER"]
            correct_pwd = st.secrets["PASSWORD"]
            if user == correct_user and pwd == correct_pwd:
                st.session_state.authenticated = True
                msg.success("✅ Başarılı!")
                time.sleep(0.3)
                st.rerun()
            else:
                st.session_state.login_counter += 1
                msg.error("❌ Hatalı!")
                time.sleep(0.3)
                st.rerun()
        except Exception as e:
            if TEST_MODE:
                st.warning("⚠️ TEST MODU: ADMIN/Elma*")
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
            else:
                st.error("❌ Giriş yapılandırması bulunamadı!")
                return False
    
    st.markdown('</div>', unsafe_allow_html=True)
    return False

# ===================== CSS =====================
st.markdown("""<style>
    .header { font-size:1.8rem; font-weight:700; text-align:center; padding:1rem;
              background:linear-gradient(135deg,#667eea,#764ba2); color:white;
              border-radius:15px; margin-bottom:1.5rem; }
    .score-high { background-color: #2ecc71; color: white; font-weight: bold; padding: 2px 8px; border-radius: 12px; }
    .score-mid { background-color: #f1c40f; padding: 2px 8px; border-radius: 12px; }
    .score-low { background-color: #e67e22; color: white; padding: 2px 8px; border-radius: 12px; }
    .score-bad { background-color: #e74c3c; color: white; padding: 2px 8px; border-radius: 12px; }
    .signal-event { background-color: #3498db; color: white; padding: 2px 8px; border-radius: 12px; }
</style>""", unsafe_allow_html=True)

# ===================== SABİTLER =====================
LOOKBACK = 150
LOOKBACK_MA = 100
MIN_HISTORY = 100
STEPS = [5,10,15,30,60,90]
FORWARD_DAYS = 90
SIGNAL_COOLDOWN = 10
CACHE_TTL = 300

cpu = os.cpu_count() or 4
WORKERS = min(12, cpu * 2)

# ===================== STRATEJİ PRESETLERİ =====================
STRATEGY_PRESETS = {
    "🎯 Erken Trend Avcısı V2.1": {
        'base_filters': {
            'RSI_max': 75, 'RSI_min': 20,
            'MA200_diff_min': -40, 'MA200_diff_max': 60,
            'ADX_min': 10,
            'Volume_MA_ratio': 0.3,
            'MFI_max': 80, 'MFI_min': 20,
            'Stochastic_max': 85, 'Stochastic_min': 5,
            'BB_Position_min': 0.02, 'BB_Position_max': 0.85,
            'CMF_min': -0.05,
        },
        'profiles': {
            'Erken': {'Min_Perf_Score': 40, 'Max_ADX': 28},
            'Orta': {'Min_Perf_Score': 50, 'Max_RSI': 62, 'Min_ADX': 12, 'Max_ADX': 32},
            'Sıkı': {'Min_Perf_Score': 60, 'Max_RSI': 58, 'Min_RSI': 30, 
                     'Min_ADX': 15, 'Max_ADX': 35, 'Min_Volume_MA': 0.5}
        },
        'desc': '🎯 V2.1: Sinyal olayı tabanlı backtest motoru (Final)'
    },
    "📊 Dengeli V2.1": {
        'base_filters': {
            'RSI_max': 75, 'RSI_min': 25,
            'MA200_diff_min': -35, 'MA200_diff_max': 70,
            'ADX_min': 12,
            'Volume_MA_ratio': 0.4,
            'MFI_max': 75, 'MFI_min': 25,
            'Stochastic_max': 80, 'Stochastic_min': 5,
            'BB_Position_min': 0.03, 'BB_Position_max': 0.80,
            'CMF_min': -0.05,
        },
        'profiles': {
            'Dengeli': {'Min_Perf_Score': 45, 'Max_RSI': 65, 'Min_ADX': 14, 'Max_ADX': 35}
        },
        'desc': '📊 Erken ve orta seviye sinyallerin dengeli karışımı'
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

@st.cache_data(ttl=CACHE_TTL)
def get_data_cached(symbol, start_date, end_date):
    try:
        sym = symbol.upper().strip()
        if not sym.endswith(".IS"): sym += ".IS"
        
        ticker = bp.Ticker(sym)
        df = ticker.history(start=start_date, end=end_date)
        
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

def get_data(symbol, date_str):
    try:
        ref = pd.to_datetime(date_str)
        today = datetime.now().date()
        if ref.date() > today:
            ref = pd.Timestamp(today)
        
        start = (ref - timedelta(days=LOOKBACK*2)).strftime('%Y-%m-%d')
        end = (ref + timedelta(days=FORWARD_DAYS)).strftime('%Y-%m-%d')
        
        if pd.to_datetime(end).date() > today:
            end = today.strftime('%Y-%m-%d')
        
        return get_data_cached(symbol, start, end)
    except:
        return None

# ===================== GÖSTERGE HESAPLAMALARI =====================
def calc_indicators(df):
    if df is None or len(df) < MIN_HISTORY:
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
    
    # RSI - WILDER
    d = clean_df['Close'].diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    clean_df['RSI'] = 100 - 100/(1+rs)
    clean_df['RSI'] = clean_df['RSI'].fillna(50)
    
    # STOCHASTIC - Fast %K
    high_14 = clean_df['High'].rolling(14).max()
    low_14 = clean_df['Low'].rolling(14).min()
    denom = (high_14 - low_14).replace(0, np.nan)
    clean_df['Stochastic'] = 100 * (clean_df['Close'] - low_14) / denom
    clean_df['Stochastic'] = clean_df['Stochastic'].fillna(50)
    
    # Slow %K
    clean_df['Stochastic_Slow'] = clean_df['Stochastic'].rolling(3).mean()
    clean_df['Stochastic_Slow'] = clean_df['Stochastic_Slow'].fillna(50)
    
    # ADX - WILDER
    tr = np.maximum(clean_df['High']-clean_df['Low'], 
                    np.maximum(abs(clean_df['High']-clean_df['Close'].shift()), 
                              abs(clean_df['Low']-clean_df['Close'].shift())))
    atr = pd.Series(tr, index=clean_df.index).ewm(alpha=1/14, adjust=False).mean()
    
    dp = np.where((clean_df['High']-clean_df['High'].shift())>(clean_df['Low'].shift()-clean_df['Low']), 
                  np.maximum(clean_df['High']-clean_df['High'].shift(),0),0)
    dm = np.where((clean_df['Low'].shift()-clean_df['Low'])>(clean_df['High']-clean_df['High'].shift()), 
                  np.maximum(clean_df['Low'].shift()-clean_df['Low'],0),0)
    
    dp_series = pd.Series(dp, index=clean_df.index)
    dm_series = pd.Series(dm, index=clean_df.index)
    
    di_plus = 100 * (dp_series.ewm(alpha=1/14, adjust=False).mean() / atr)
    di_minus = 100 * (dm_series.ewm(alpha=1/14, adjust=False).mean() / atr)
    
    denom_adx = (di_plus + di_minus).replace(0, np.nan)
    dx = 100 * abs(di_plus - di_minus) / denom_adx
    clean_df['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()
    clean_df['ADX'] = clean_df['ADX'].fillna(20)
    
    # ATR - WILDER
    true_range = pd.DataFrame({
        'hl': clean_df['High'] - clean_df['Low'],
        'hc': abs(clean_df['High'] - clean_df['Close'].shift()),
        'lc': abs(clean_df['Low'] - clean_df['Close'].shift())
    }).max(axis=1)
    clean_df['ATR'] = true_range.ewm(alpha=1/14, adjust=False).mean()
    clean_df['ATR'] = clean_df['ATR'].fillna(0)
    
    # VOLRATIO
    vma20 = clean_df['VMA20'].replace(0, np.nan)
    clean_df['VolRatio'] = clean_df['Volume'] / vma20
    clean_df['VolRatio'] = clean_df['VolRatio'].fillna(1)
    
    # MFI
    tp = (clean_df['High']+clean_df['Low']+clean_df['Close'])/3
    mf = tp * clean_df['Volume']
    pf = mf.where(tp>tp.shift(),0).rolling(14).sum()
    nf = mf.where(tp<tp.shift(),0).rolling(14).sum()
    ratio = pf / nf.replace(0, np.nan)
    clean_df['MFI'] = 100 - 100/(1+ratio)
    clean_df['MFI'] = clean_df['MFI'].fillna(50)
    
    # BOLLINGER BANDS
    clean_df['BB_Mid'] = clean_df['Close'].rolling(20).mean()
    clean_df['BB_Std'] = clean_df['Close'].rolling(20).std()
    clean_df['BB_Upper'] = clean_df['BB_Mid'] + 2 * clean_df['BB_Std']
    clean_df['BB_Lower'] = clean_df['BB_Mid'] - 2 * clean_df['BB_Std']
    bb_range = clean_df['BB_Upper'] - clean_df['BB_Lower']
    clean_df['BB_Position'] = np.where(
        bb_range > 0,
        (clean_df['Close'] - clean_df['BB_Lower']) / bb_range,
        0.5
    )
    clean_df['BB_Position'] = clean_df['BB_Position'].fillna(0.5)
    
    # OBV
    try:
        obv = [0]
        for i in range(1, len(clean_df)):
            if clean_df['Close'].iloc[i] > clean_df['Close'].iloc[i-1]:
                obv.append(obv[-1] + clean_df['Volume'].iloc[i])
            elif clean_df['Close'].iloc[i] < clean_df['Close'].iloc[i-1]:
                obv.append(obv[-1] - clean_df['Volume'].iloc[i])
            else:
                obv.append(obv[-1])
        clean_df['OBV'] = obv
    except:
        clean_df['OBV'] = 0
    
    # OBV_Normalized
    vma20 = clean_df['VMA20'].replace(0, np.nan)
    clean_df['OBV_Normalized'] = clean_df['OBV'] / vma20
    clean_df['OBV_Normalized'] = clean_df['OBV_Normalized'].fillna(0)
    
    # OBV Yüzdesel Değişim
    clean_df['OBV_Pct_Change_3'] = clean_df['OBV_Normalized'].pct_change(3) * 100
    clean_df['OBV_Pct_Change_3'] = clean_df['OBV_Pct_Change_3'].fillna(0)
    
    # CMF
    try:
        high_low = clean_df['High'] - clean_df['Low']
        high_low = high_low.replace(0, np.nan)
        mf_multiplier = ((clean_df['Close'] - clean_df['Low']) - (clean_df['High'] - clean_df['Close'])) / high_low
        mf_volume = mf_multiplier * clean_df['Volume']
        clean_df['CMF'] = mf_volume.rolling(20).sum() / clean_df['Volume'].rolling(20).sum()
        clean_df['CMF'] = clean_df['CMF'].fillna(0)
    except:
        clean_df['CMF'] = 0
    
    # SLOPE'LAR
    indicators = ['RSI', 'ADX', 'MFI', 'Stochastic', 'VolRatio', 'BB_Position', 'OBV_Normalized', 'CMF']
    for ind in indicators:
        if ind in clean_df.columns:
            clean_df[f'{ind}_Slope3'] = clean_df[ind].diff(3).fillna(0)
            clean_df[f'{ind}_Slope5'] = clean_df[ind].diff(5).fillna(0)
    
    return clean_df

# ===================== SKORLAMA FONKSİYONLARI =====================
def score_stock_early(r):
    s = 0
    adx = r.get('ADX', 20)
    rsi = r.get('RSI', 50)
    
    if adx < 30:
        if 42 <= rsi <= 52: s += 25
        elif 38 <= rsi < 42 or 52 < rsi <= 58: s += 20
        elif 35 <= rsi < 38 or 58 < rsi <= 65: s += 12
        elif 65 < rsi <= 72: s += 5
        else: s += 0
    else:
        if 45 <= rsi <= 60: s += 15
        elif 40 <= rsi < 45 or 60 < rsi <= 68: s += 10
        elif 68 < rsi <= 75: s += 5
        else: s += 0
    
    if 16 <= adx <= 22: s += 25
    elif 22 < adx <= 28: s += 20
    elif 28 < adx <= 35: s += 12
    elif 35 < adx <= 45: s += 5
    elif 12 <= adx < 16: s += 15
    else: s += 0
    
    vl = r.get('VolRatio', 1)
    if adx < 30:
        if 1.0 <= vl <= 1.4: s += 20
        elif 0.7 <= vl < 1.0 or 1.4 < vl <= 1.8: s += 15
        elif 1.8 < vl <= 2.5: s += 8
        elif vl > 2.5: s += 3
        else: s += 2
    else:
        if 0.8 <= vl <= 1.6: s += 15
        elif 0.5 <= vl < 0.8 or 1.6 < vl <= 2.0: s += 10
        elif vl > 2.0: s += 5
        else: s += 2
    
    mf = r.get('MFI', 50)
    if 45 <= mf <= 58: s += 15
    elif 40 <= mf < 45 or 58 < mf <= 65: s += 10
    elif 35 <= mf < 40 or 65 < mf <= 72: s += 5
    else: s += 0
    
    stoch = r.get('Stochastic', 50)
    if 15 <= stoch <= 35: s += 10
    elif 5 <= stoch < 15 or 35 < stoch <= 55: s += 7
    elif 55 < stoch <= 75: s += 3
    else: s += 0
    
    bb_pos = r.get('BB_Position', 0.5)
    if 0.1 <= bb_pos <= 0.35: s += 8
    elif 0.35 < bb_pos <= 0.55: s += 6
    elif 0.55 < bb_pos <= 0.7: s += 3
    else: s += 0
    
    return max(0, min(s, 100))

def money_flow_score_early(row):
    score = 0
    
    if 'OBV_Pct_Change_3' in row.index and not pd.isna(row.get('OBV_Pct_Change_3', 0)):
        obv_pct = row.get('OBV_Pct_Change_3', 0)
        if obv_pct > 5: score += 10
        elif obv_pct > 2: score += 6
        elif obv_pct > 0.5: score += 3
        elif obv_pct < -5: score -= 3
    
    if 'CMF' in row.index and not pd.isna(row.get('CMF', 0)):
        cmf = row.get('CMF', 0)
        if cmf > 0.05: score += 8
        elif cmf > 0: score += 4
        elif cmf < -0.05: score -= 3
    
    if 'CMF_Slope3' in row.index and not pd.isna(row.get('CMF_Slope3', 0)):
        cmf_slope = row.get('CMF_Slope3', 0)
        if cmf_slope > 0.01: score += 5
        elif cmf_slope > 0.003: score += 2
    
    return max(0, min(score, 15))

def consolidation_breakout_score_early(df, idx):
    if idx < 20:
        return 0
    
    score = 0
    
    try:
        atr_recent = df['ATR'].iloc[max(0, idx-9):idx+1].mean()
        atr_previous = df['ATR'].iloc[max(0, idx-19):max(0, idx-9)].mean()
        
        if atr_previous > 0:
            atr_ratio = atr_recent / atr_previous
            if atr_ratio < 0.75: score += 12
            elif atr_ratio < 0.85: score += 8
            elif atr_ratio < 0.95: score += 4
    except:
        pass
    
    try:
        vol_recent = df['Volume'].iloc[max(0, idx-4):idx+1].mean()
        vol_previous = df['Volume'].iloc[max(0, idx-9):max(0, idx-4)].mean()
        
        if vol_previous > 0:
            vol_ratio = vol_recent / vol_previous
            if vol_ratio > 1.6: score += 10
            elif vol_ratio > 1.2: score += 6
            elif vol_ratio > 1.0: score += 3
    except:
        pass
    
    try:
        high_20 = df['High'].iloc[max(0, idx-19):idx+1].max()
        low_20 = df['Low'].iloc[max(0, idx-19):idx+1].min()
        
        if low_20 > 0:
            range_pct = (high_20 - low_20) / low_20 * 100
            if range_pct < 6: score += 8
            elif range_pct < 10: score += 5
            elif range_pct < 15: score += 2
    except:
        pass
    
    try:
        current_close = df['Close'].iloc[idx]
        previous_high20 = df['High'].iloc[max(0, idx-20):idx].max()
        if not pd.isna(previous_high20) and current_close > previous_high20:
            score += 6
    except:
        pass
    
    return min(score, 30)

def trend_quality_early(row):
    score = 0
    
    try:
        ma20 = row.get('MA20', 0)
        ma50 = row.get('MA50', 0)
        ma200 = row.get('MA200', 0)
        
        if not pd.isna(ma20) and not pd.isna(ma50) and not pd.isna(ma200):
            if ma20 > ma50 > ma200: score += 5
            elif ma20 > ma50: score += 8
            elif ma20 > ma200: score += 3
    except:
        pass
    
    try:
        if 'Close' in row.index and 'MA20' in row.index:
            if row.get('Close', 0) > row.get('MA20', 0):
                score += 3
    except:
        pass
    
    return min(score, 15)

def calculate_signal_score(df, idx, weights, symbol=None, index_df=None, date_index_map=None, min_final_score=40):
    row = df.iloc[idx]
    
    # 1. Trend Quality (25%)
    tq_score = trend_quality_early(row)
    tq_norm = (tq_score / 15) * 100
    
    # 2. Money Flow (20%)
    money_score = money_flow_score_early(row)
    money_norm = (money_score / 15) * 100
    
    # 3. Momentum (20%)
    momentum_score = 0
    if 'ADX_Slope3' in row.index and not pd.isna(row['ADX_Slope3']):
        momentum_score += row['ADX_Slope3'] * 2
    if 'CMF_Slope3' in row.index and not pd.isna(row['CMF_Slope3']):
        momentum_score += row['CMF_Slope3'] * 20
    if 'OBV_Normalized_Slope3' in row.index and not pd.isna(row['OBV_Normalized_Slope3']):
        momentum_score += row['OBV_Normalized_Slope3'] * 2
    if 'RSI_Slope3' in row.index and not pd.isna(row['RSI_Slope3']):
        momentum_score += row['RSI_Slope3'] * 1.5
    if 'VolRatio_Slope3' in row.index and not pd.isna(row['VolRatio_Slope3']):
        momentum_score += row['VolRatio_Slope3'] * 1.5
    if 'BB_Position_Slope3' in row.index and not pd.isna(row['BB_Position_Slope3']):
        momentum_score += row['BB_Position_Slope3'] * 0.5
    
    momentum_score = max(-30, min(30, momentum_score))
    momentum_norm = max(0, min(100, (momentum_score / 30) * 50 + 50))
    
    # 4. Breakout (15%)
    breakout_score = consolidation_breakout_score_early(df, idx)
    breakout_norm = (breakout_score / 30) * 100
    
    # 5. Relative Strength (10%)
    rs_score = 0
    if index_df is not None and date_index_map is not None and idx >= 20:
        try:
            current_date = pd.Timestamp(df['Date'].iloc[idx]).normalize()
            if current_date in date_index_map:
                index_idx = date_index_map[current_date]
                current_price = df['Close'].iloc[idx]
                index_current = index_df['Close'].iloc[index_idx]
                
                rs_values = []
                for period in [5, 10, 20]:
                    if idx >= period and index_idx >= period:
                        stock_prev = df['Close'].iloc[idx - period]
                        index_prev = index_df['Close'].iloc[index_idx - period]
                        
                        if stock_prev > 0 and index_prev > 0:
                            stock_return = ((current_price - stock_prev) / stock_prev) * 100
                            index_return = ((index_current - index_prev) / index_prev) * 100
                            rs = stock_return - index_return
                            rs_values.append(rs)
                
                if rs_values:
                    avg_rs = np.mean(rs_values)
                    if avg_rs > 3: rs_score = 20
                    elif avg_rs > 1: rs_score = 15
                    elif avg_rs > 0: rs_score = 10
                    elif avg_rs > -1: rs_score = 5
                    else: rs_score = 0
        except:
            pass
    
    rs_norm = (rs_score / 20) * 100
    
    # 6. Risk Filter (10%)
    risk_score = 0
    bb_pos = row.get('BB_Position', 0.5)
    stoch = row.get('Stochastic', 50)
    rsi_val = row.get('RSI', 50)
    
    if bb_pos < 0.5:
        risk_score += 5
    if stoch < 50:
        risk_score += 5
    if rsi_val < 55:
        risk_score += 5
    risk_norm = (risk_score / 15) * 100
    
    # ========== CEZA SİSTEMİ ==========
    penalty = 0
    
    stoch = row.get('Stochastic', 50)
    bb_pos = row.get('BB_Position', 0.5)
    if stoch > 80 and bb_pos > 0.75:
        penalty += 5
    
    rsi_val = row.get('RSI', 50)
    if rsi_val > 65:
        penalty += 3
    
    ma200_diff = row.get('MA200_Mesafe%', 0)
    if pd.notna(ma200_diff) and ma200_diff > 30:
        penalty += 5
    
    vol_ratio = row.get('VolRatio', 1)
    if vol_ratio < 0.8:
        penalty += 3
    
    cmf = row.get('CMF', 0)
    if cmf < 0:
        penalty += 3
    
    final_score = (
        weights['w_trend'] * tq_norm +
        weights['w_money'] * money_norm +
        weights['w_momentum'] * momentum_norm +
        weights['w_breakout'] * breakout_norm +
        weights['w_rs'] * rs_norm +
        weights['w_risk'] * risk_norm
    )
    
    final_score -= penalty
    
    final_score = round(max(0, min(final_score, 100)), 1)
    
    if final_score < min_final_score:
        return None
    
    return {
        'Trend_Quality': round(tq_score, 1),
        'Money_Score': round(money_score, 1),
        'Momentum_Score': round(momentum_score, 1),
        'Breakout_Score': round(breakout_score, 1),
        'RS_Score': round(rs_score, 1),
        'Risk_Score': round(risk_score, 1),
        'Quality_Penalty': round(penalty, 1),
        'Final_Score': final_score
    }

# ===================== FİLTRE FONKSİYONLARI =====================
def check_signal(df, i, base_filters):
    try:
        rsi = df['RSI'].iloc[i]
        if pd.isna(rsi) or rsi > base_filters['RSI_max'] or rsi < base_filters['RSI_min']:
            return False
        
        if pd.isna(df['MA200'].iloc[i]):
            return False
        ma200_diff = ((df['Close'].iloc[i] - df['MA200'].iloc[i]) / df['MA200'].iloc[i]) * 100
        if ma200_diff < base_filters['MA200_diff_min'] or ma200_diff > base_filters['MA200_diff_max']:
            return False
        
        adx = df['ADX'].iloc[i]
        if pd.isna(adx) or adx < base_filters['ADX_min']:
            return False
        
        vol = df['VolRatio'].iloc[i]
        if pd.isna(vol) or vol < base_filters['Volume_MA_ratio']:
            return False
        
        mfi = df['MFI'].iloc[i]
        if pd.isna(mfi) or mfi > base_filters['MFI_max'] or mfi < base_filters['MFI_min']:
            return False
        
        stoch = df['Stochastic'].iloc[i]
        if pd.isna(stoch) or stoch > base_filters['Stochastic_max'] or stoch < base_filters['Stochastic_min']:
            return False
        
        bb = df['BB_Position'].iloc[i]
        if pd.isna(bb) or bb > base_filters['BB_Position_max'] or bb < base_filters['BB_Position_min']:
            return False
        
        cmf = df['CMF'].iloc[i]
        if pd.isna(cmf) or cmf < base_filters.get('CMF_min', -0.05):
            return False
        
        return True
    except:
        return False

def apply_filter(r, filters):
    if filters is None:
        return True
    try:
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
    except:
        return False

# ===================== TARAMA FONKSİYONU (OPTİMİZE) =====================
def scan_stock(sym, df_full, ref_date, base_filters, weights, profile=None, 
               index_df=None, date_index_map=None, min_final_score=40):
    """Tek bir hisse için sinyal taraması - OPTİMİZE"""
    try:
        if df_full is None or len(df_full) < MIN_HISTORY:
            return None
        
        df = calc_indicators(df_full)
        if df is None:
            return None
        
        ref = pd.to_datetime(ref_date).normalize()
        dates = df['Date'].dt.normalize()
        
        # ===== KRİTİK DÜZELTME: <= kullan (seçilen tarih dahil) =====
        # Seçilen tarihin kapanış verisine göre sinyal
        valid = np.where(dates <= ref)[0]
        if len(valid) == 0:
            return None
        idx = valid[-1]
        
        # Look-ahead bias koruması
        signal_df = df.iloc[:idx+1].copy()
        signal_idx = len(signal_df) - 1
        
        if not check_signal(signal_df, signal_idx, base_filters):
            return None
        
        signal_price = signal_df['Close'].iloc[signal_idx]
        signal_date = signal_df['Date'].iloc[signal_idx]
        
        ma200_diff = None
        if pd.notna(signal_df['MA200'].iloc[signal_idx]):
            ma200_diff = ((signal_price - signal_df['MA200'].iloc[signal_idx]) / signal_df['MA200'].iloc[signal_idx]) * 100
        
        clean_symbol = sym.replace(".IS", "")
        signal_id = f"{clean_symbol}_{signal_date.strftime('%Y%m%d')}"
        
        signal_event = {
            'Signal_ID': signal_id,
            'Hisse': sym,
            'Entry_Date': signal_date.strftime('%Y-%m-%d'),
            'Entry_Price': round(signal_price, 2),
            
            'RSI': round(signal_df['RSI'].iloc[signal_idx], 1),
            'ADX': round(signal_df['ADX'].iloc[signal_idx], 1),
            'VolRatio': round(signal_df['VolRatio'].iloc[signal_idx], 2),
            'MFI': round(signal_df['MFI'].iloc[signal_idx], 1),
            'Stochastic': round(signal_df['Stochastic'].iloc[signal_idx], 1),
            'BB_Position': round(signal_df['BB_Position'].iloc[signal_idx], 2),
            'CMF': round(signal_df['CMF'].iloc[signal_idx], 3),
            'MA200_Mesafe%': round(ma200_diff, 1) if ma200_diff is not None else None,
        }
        
        signal_row = signal_df.iloc[signal_idx].to_dict()
        signal_row.update(signal_event)
        signal_event['Perf_Skor'] = score_stock_early(signal_row)
        
        scores = calculate_signal_score(signal_df, signal_idx, weights, sym, 
                                        index_df, date_index_map, min_final_score)
        if scores is None:
            return None
        
        signal_event.update({
            'Trend_Quality': scores['Trend_Quality'],
            'Money_Score': scores['Money_Score'],
            'Momentum_Score': scores['Momentum_Score'],
            'Breakout_Score': scores['Breakout_Score'],
            'RS_Score': scores['RS_Score'],
            'Risk_Score': scores['Risk_Score'],
            'Quality_Penalty': scores['Quality_Penalty'],
            'Final_Score': scores['Final_Score']
        })
        
        if profile:
            if not apply_filter(signal_event, profile):
                return None
        
        # ===== PERFORMANS METRİKLERİ (ORİJİNAL DF ÜZERİNDEN) =====
        # Forward getiriler - sinyal gününden sonraki günler
        for s in STEPS:
            if idx + s < len(df):
                future_close = df['Close'].iloc[idx + s]
                if pd.notna(future_close) and signal_price != 0:
                    signal_event[f'+{s}G_Getiri%'] = round(((future_close - signal_price) / signal_price) * 100, 2)
                else:
                    signal_event[f'+{s}G_Getiri%'] = None
            else:
                signal_event[f'+{s}G_Getiri%'] = None
        
        for s in STEPS:
            if idx + s < len(df):
                future_window = df.iloc[idx:idx+s+1]
                max_price = future_window['High'].max()
                if pd.notna(max_price) and signal_price != 0:
                    signal_event[f'+{s}G_Max_Getiri%'] = round(((max_price - signal_price) / signal_price) * 100, 2)
                else:
                    signal_event[f'+{s}G_Max_Getiri%'] = None
            else:
                signal_event[f'+{s}G_Max_Getiri%'] = None
        
        # Max_DD - sinyal gününden sonra
        max_dd = 0
        if idx + 30 < len(df):
            low_valley = df['Low'].iloc[idx+1:idx+31].min()
            if signal_price > 0:
                max_dd = ((signal_price - low_valley) / signal_price) * 100
        
        signal_event['Max_DD_30G'] = round(max_dd, 1)
        
        if signal_event.get('+30G_Getiri%') is not None and max_dd > 0:
            signal_event['Risk_Ratio_30G'] = round(signal_event['+30G_Getiri%'] / max_dd, 2)
        else:
            signal_event['Risk_Ratio_30G'] = None
        
        # Hedef Analizi
        target_10 = signal_price * 1.10
        days_to_target_10 = None
        for i in range(idx + 1, min(idx + 90, len(df))):
            if df['High'].iloc[i] >= target_10:
                days_to_target_10 = i - idx
                break
        signal_event['Days_To_%10_Target'] = days_to_target_10
        
        target_20 = signal_price * 1.20
        days_to_target_20 = None
        for i in range(idx + 1, min(idx + 90, len(df))):
            if df['High'].iloc[i] >= target_20:
                days_to_target_20 = i - idx
                break
        signal_event['Days_To_%20_Target'] = days_to_target_20
        
        # Başarı Metriği
        if signal_event.get('+10G_Max_Getiri%') is not None and max_dd > 0:
            if signal_event['+10G_Max_Getiri%'] > 8 and max_dd < 5:
                signal_event['Is_Successful'] = 1
            else:
                signal_event['Is_Successful'] = 0
        else:
            signal_event['Is_Successful'] = None
        
        return signal_event
    except:
        return None

def run_scan_optimized(symbols, date, base_filters, weights, profile=None, 
                       index_df=None, date_index_map=None, min_final_score=40):
    """OPTİMİZE: Tüm veriler önceden çekiliyor"""
    results = []
    ds = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
    
    data_cache = {}
    for sym in symbols:
        try:
            df = get_data(sym, ds)
            if df is not None and len(df) >= MIN_HISTORY:
                data_cache[sym] = df
        except:
            continue
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {}
        for sym, df in data_cache.items():
            future = ex.submit(scan_stock, sym, df, date, base_filters, weights, 
                               profile, index_df, date_index_map, min_final_score)
            futures[future] = sym
        
        for future in as_completed(futures):
            try:
                r = future.result()
                if r:
                    results.append(r)
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

# ===================== COOLDOWN FONKSİYONU =====================
def is_cooldown_active(hisse, entry_date, signal_history, cooldown_days):
    """İşlem günü bazlı cooldown kontrolü"""
    if hisse not in signal_history:
        return False
    
    last_signal = signal_history[hisse].get('last_date')
    if last_signal is None:
        return False
    
    try:
        bdiff = np.busday_count(
            np.datetime64(last_signal),
            np.datetime64(entry_date)
        )
        return bdiff <= cooldown_days
    except:
        days_diff = (pd.to_datetime(entry_date) - pd.to_datetime(last_signal)).days
        return days_diff <= cooldown_days

# ===================== ANA UYGULAMA =====================
def main():
    if not check_password():
        return
    
    defaults = {
        "strategy_preset": "🎯 Erken Trend Avcısı V2.1",
        "df": None, "ok": False, "t": 0, "days": 0,
        "min_final_score": 40,
        "signal_history": defaultdict(dict)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    
    c1, c2, c3 = st.columns([7,1,1])
    with c1: st.markdown('<div class="header">🎯 BIST SİNYAL OLAYI BACKTEST MOTORU V2.1 (FİNAL)</div>', unsafe_allow_html=True)
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
        
        strategy = STRATEGY_PRESETS[preset]
        base_filters = strategy['base_filters']
        
        profile_names = list(strategy['profiles'].keys())
        selected_profile = st.selectbox("📊 Filtre Profili", ["Hiçbiri"] + profile_names)
        
        profile = strategy['profiles'].get(selected_profile) if selected_profile != "Hiçbiri" else None
        
        st.caption(strategy['desc'])
        st.caption(f"Temel filtreler: RSI {base_filters['RSI_min']}-{base_filters['RSI_max']}, "
                  f"ADX >{base_filters['ADX_min']}, CMF >{base_filters.get('CMF_min', -0.05)}")
        
        st.markdown("---")
        st.markdown("### 🎯 PUANLAMA AĞIRLIKLARI")
        
        col1, col2 = st.columns(2)
        with col1:
            w_trend = st.slider("Trend Quality", 0.0, 1.0, 0.25, 0.05, key="w_trend")
            w_money = st.slider("Money Flow", 0.0, 1.0, 0.20, 0.05, key="w_money")
            w_momentum = st.slider("Momentum", 0.0, 1.0, 0.20, 0.05, key="w_mom")
        with col2:
            w_breakout = st.slider("Breakout", 0.0, 1.0, 0.15, 0.05, key="w_breakout")
            w_rs = st.slider("RS", 0.0, 1.0, 0.10, 0.05, key="w_rs")
            w_risk = st.slider("Risk Filter", 0.0, 1.0, 0.10, 0.05, key="w_risk")
        
        total_w = w_trend + w_money + w_momentum + w_breakout + w_rs + w_risk
        if total_w > 0:
            weights = {
                'w_trend': w_trend/total_w,
                'w_money': w_money/total_w,
                'w_momentum': w_momentum/total_w,
                'w_breakout': w_breakout/total_w,
                'w_rs': w_rs/total_w,
                'w_risk': w_risk/total_w
            }
        else:
            weights = {'w_trend': 0.25, 'w_money': 0.20, 'w_momentum': 0.20, 
                      'w_breakout': 0.15, 'w_rs': 0.10, 'w_risk': 0.10}
        
        st.caption(f"📊 Mevcut ağırlıklar: "
                  f"Trend {weights['w_trend']*100:.0f}% | "
                  f"Money {weights['w_money']*100:.0f}% | "
                  f"Momentum {weights['w_momentum']*100:.0f}% | "
                  f"Breakout {weights['w_breakout']*100:.0f}% | "
                  f"RS {weights['w_rs']*100:.0f}% | "
                  f"Risk {weights['w_risk']*100:.0f}%")
        
        st.markdown("---")
        st.markdown("### 📊 SİNYAL FİLTRELERİ")
        
        min_final_score = st.slider(
            "Minimum Final Skor",
            min_value=0, max_value=100, value=st.session_state.min_final_score, step=5,
            help="Bu skorun altındaki sinyaller elenir"
        )
        st.session_state.min_final_score = min_final_score
        
        st.markdown("---")
        st.markdown("### 🔄 SİNYAL COOLDOWN")
        
        use_cooldown = st.checkbox("Cooldown aktif", value=True)
        cooldown_days = st.slider(
            "Cooldown işlem günü",
            min_value=0, max_value=30, value=SIGNAL_COOLDOWN, step=1,
            help="Aynı hisseden kaç işlem günü sonra tekrar sinyal alınabileceği"
        )
        
        st.markdown("---")
        
        lists = get_lists()
        secim = st.selectbox("📋 Liste", list(lists.keys()))
        symbols = lists[secim]
        st.caption(f"{len(symbols)} hisse")
        
        st.markdown("### 📅 Tarama Aralığı")
        tip = st.radio("Tip", ["Tek Tarih", "Tarih Aralığı", "Ay"], horizontal=True)
        
        if tip == "Tek Tarih":
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
        st.markdown(f"⏱️ ~**{days*len(symbols)*0.05/WORKERS:.0f}s**")
        
        btn = st.button("🔍 TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        
        with st.spinner('📊 BIST100 verisi hazırlanıyor...'):
            index_df = None
            date_index_map = None
            try:
                index_data = get_data('XU100', end.strftime('%Y-%m-%d'))
                if index_data is not None:
                    index_df = calc_indicators(index_data)
                    if index_df is not None:
                        date_index_map = {
                            pd.Timestamp(d).normalize(): i 
                            for i, d in enumerate(index_df['Date'])
                        }
            except:
                pass
        
        with st.spinner(f'🔍 {days} gün taranıyor... (Kapanış Sinyali)'):
            all_signals = []
            signal_history = st.session_state.signal_history
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | {i+1}/{days}")
                
                res = run_scan_optimized(symbols, day, base_filters, weights, profile, 
                                         index_df, date_index_map, min_final_score)
                if res:
                    for signal in res:
                        hisse = signal['Hisse']
                        entry_date = signal['Entry_Date']
                        
                        if use_cooldown:
                            if is_cooldown_active(hisse, entry_date, signal_history, cooldown_days):
                                continue
                        
                        all_signals.append(signal)
                        
                        signal_history[hisse] = {
                            'last_date': entry_date,
                            'last_score': signal['Final_Score']
                        }
                
                bar.progress((i+1)/days)
            
            st.session_state.signal_history = signal_history
            bar.empty()
            txt.empty()
        
        if all_signals:
            df = pd.DataFrame(all_signals)
            df = df.sort_values('Final_Score', ascending=False)
            
            st.session_state.df = df
            st.session_state.ok = True
            st.session_state.t = time.time() - t0
            st.session_state.days = days
        else:
            st.warning("⚠️ Sinyal olayı bulunamadı!")
            st.session_state.ok = False
    
    if st.session_state.get('ok') and st.session_state.df is not None:
        df = st.session_state.df
        
        st.markdown(f"### 📊 {len(df)} Sinyal Olayı | ⚡ {st.session_state.t:.1f}s | 📅 {st.session_state.days} gün")
        
        # ===== PERFORMANS METRİKLERİ =====
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("Toplam Sinyal", len(df))
        with c2: st.metric("Ort. Final Skor", f"{df['Final_Score'].mean():.0f}")
        
        unique_stocks = df['Hisse'].nunique()
        with c3: st.metric("📋 Benzersiz Hisse", f"{unique_stocks}")
        
        success_df = df[df['Is_Successful'].notna()]
        if len(success_df) > 0:
            success_rate = success_df['Is_Successful'].sum() / len(success_df) * 100
            with c4: st.metric("✅ Başarı (10G Max>8%, DD<5%)", f"%{success_rate:.0f}")
        else:
            with c4: st.metric("✅ Başarı Oranı", "Veri Yok")
        
        r30 = df['+30G_Getiri%'].dropna()
        with c5:
            if len(r30) > 0:
                st.metric("📈 30G Ort. Getiri", f"%{r30.mean():.1f}")
            else:
                st.metric("📈 30G Ort. Getiri", "Veri Yok")
        
        # ===== PORTFÖY METRİKLERİ =====
        st.markdown("### 📊 Portföy Metrikleri")
        
        gross_profit = df[df['+30G_Getiri%'] > 0]['+30G_Getiri%'].sum()
        gross_loss = abs(df[df['+30G_Getiri%'] < 0]['+30G_Getiri%'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        
        win_rate = (df['+30G_Getiri%'] > 0).sum() / len(df) * 100 if len(df) > 0 else 0
        avg_win = df[df['+30G_Getiri%'] > 0]['+30G_Getiri%'].mean() if (df['+30G_Getiri%'] > 0).sum() > 0 else 0
        avg_loss = abs(df[df['+30G_Getiri%'] < 0]['+30G_Getiri%'].mean()) if (df['+30G_Getiri%'] < 0).sum() > 0 else 0
        expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
        sharpe_like = df['+30G_Getiri%'].mean() / df['+30G_Getiri%'].std() if df['+30G_Getiri%'].std() > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📈 Profit Factor", f"{profit_factor:.2f}" if profit_factor != np.inf else "∞")
            st.metric("🎯 Win Rate", f"{win_rate:.1f}%")
        with col2:
            st.metric("💰 Avg Win", f"%{avg_win:.2f}")
            st.metric("📉 Avg Loss", f"%{avg_loss:.2f}")
        with col3:
            st.metric("⚖️ Expectancy", f"%{expectancy:.2f}")
            st.metric("📊 Sharpe-like", f"{sharpe_like:.2f}")
        
        st.markdown("### ⚠️ Ceza Dağılımı")
        if 'Quality_Penalty' in df.columns:
            fig_penalty = go.Figure()
            fig_penalty.add_trace(go.Histogram(
                x=df['Quality_Penalty'],
                nbinsx=10,
                marker_color='#e74c3c'
            ))
            fig_penalty.update_layout(
                title="Uygulanan Ceza Dağılımı",
                xaxis_title="Ceza Puanı",
                yaxis_title="Sinyal Sayısı",
                height=250
            )
            st.plotly_chart(fig_penalty, use_container_width=True)
        
        st.markdown("### ⏰ Sinyal Zamanlama Analizi")
        # DÜZELTİLDİ: Açıklama yeni mantığa göre
        st.info("📌 **Not:** Her sinyal seçilen tarihin kapanış verisine göre oluşturulur. "
                "Entry_Price = seçilen gün kapanış fiyatıdır. "
                "Sinyal, takip eden işlem günü için aday olarak değerlendirilir.")
        
        signal_dates = df['Entry_Date'].value_counts().sort_index()
        if len(signal_dates) > 0:
            fig_dates = go.Figure()
            fig_dates.add_trace(go.Bar(
                x=signal_dates.index,
                y=signal_dates.values,
                marker_color='#3498db'
            ))
            fig_dates.update_layout(
                title="Günlere Göre Sinyal Sayısı",
                xaxis_title="Tarih (Kapanış Günü)",
                yaxis_title="Sinyal Sayısı",
                height=300
            )
            st.plotly_chart(fig_dates, use_container_width=True)
        
        st.markdown("### 📊 Sinyal Performans Analizi")
        
        df['Score_Group'] = pd.cut(df['Final_Score'], bins=[0, 45, 55, 65, 75, 100], 
                                   labels=['0-45', '45-55', '55-65', '65-75', '75+'])
        
        perf_by_score = df.groupby('Score_Group')['+30G_Getiri%'].agg(['count', 'mean', 'std']).round(2)
        perf_by_score.columns = ['Sinyal Sayısı', 'Ort. Getiri %', 'Std']
        st.dataframe(perf_by_score, use_container_width=True)
        
        st.markdown("#### 🎯 Skor Grubuna Göre Başarı Oranı (10G Max>8%, DD<5%)")
        success_tmp = df[df['Is_Successful'].notna()]
        if len(success_tmp) > 0:
            success_by_score = success_tmp.groupby('Score_Group')['Is_Successful'].mean() * 100
            success_by_score = success_by_score.round(1)
        else:
            success_by_score = pd.Series(dtype=float)
        
        if len(success_by_score) > 0:
            fig_success = go.Figure()
            fig_success.add_trace(go.Bar(
                x=success_by_score.index,
                y=success_by_score.values,
                marker_color=['#e74c3c', '#f1c40f', '#2ecc71', '#3498db', '#9b59b6'],
                text=success_by_score.values,
                textposition='outside'
            ))
            fig_success.update_layout(
                title="Skor Grubuna Göre Başarı Oranı",
                xaxis_title="Final Skor Grubu",
                yaxis_title="Başarı Oranı %",
                height=300
            )
            st.plotly_chart(fig_success, use_container_width=True)
        else:
            st.info("Başarı oranı hesaplamak için yeterli veri yok.")
        
        st.markdown("### 🔄 Tekrar Sinyal Veren Hisseler")
        
        repeat_df = df.groupby('Hisse').agg(
            Sinyal=('Signal_ID', 'count'),
            Test=('Is_Successful', 'count'),
            Basari=('Is_Successful', 'sum'),
            Ort_Skor=('Final_Score', 'mean'),
            Ort_30G=('+30G_Getiri%', 'mean'),
            Ort_DD=('Max_DD_30G', 'mean')
        ).reset_index()
        
        repeat_df['Başarı_Oranı'] = (repeat_df['Basari'] / repeat_df['Test'] * 100).round(1)
        repeat_df = repeat_df.fillna(0)
        repeat_df = repeat_df.sort_values('Sinyal', ascending=False)
        
        display_repeat = repeat_df[['Hisse', 'Sinyal', 'Test', 'Başarı_Oranı', 'Ort_Skor', 'Ort_30G', 'Ort_DD']]
        display_repeat.columns = ['Hisse', 'Sinyal_Sayısı', 'Test_Sayısı', 'Başarı_Oranı', 'Ort_Skor', 'Ort_30G_Getiri', 'Ort_DD']
        st.dataframe(display_repeat.head(10), use_container_width=True)
        
        st.markdown("### 🎯 Hedef Analizi")
        
        target10_df = df[df['Days_To_%10_Target'].notna()].copy()
        if len(target10_df) > 0:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📊 %10 Hedefe Ulaşan Sinyal", f"{len(target10_df)} / {len(df)}")
                st.metric("⏱️ Ort. %10 Hedef Süresi", f"{target10_df['Days_To_%10_Target'].mean():.0f} gün")
            with col2:
                st.metric("📊 %20 Hedefe Ulaşan Sinyal", 
                         f"{len(df[df['Days_To_%20_Target'].notna()])} / {len(df)}")
                st.metric("⏱️ Ort. %20 Hedef Süresi", 
                         f"{df[df['Days_To_%20_Target'].notna()]['Days_To_%20_Target'].mean():.0f} gün")
        
        st.markdown("### 🛡️ Risk/Getiri Analizi")
        
        risk_df = df[['Hisse', 'Entry_Date', 'Final_Score', '+30G_Getiri%', 'Max_DD_30G', 'Risk_Ratio_30G']].dropna()
        if len(risk_df) > 0:
            risk_df = risk_df.sort_values('Risk_Ratio_30G', ascending=False)
            st.dataframe(risk_df.head(10), use_container_width=True)
            
            fig_risk = go.Figure()
            fig_risk.add_trace(go.Scatter(
                x=risk_df['Max_DD_30G'],
                y=risk_df['+30G_Getiri%'],
                mode='markers',
                marker=dict(
                    size=risk_df['Final_Score']/10,
                    color=risk_df['Final_Score'],
                    colorscale='Viridis',
                    showscale=True
                ),
                text=risk_df['Hisse'] + ' ' + risk_df['Entry_Date'],
                hoverinfo='text'
            ))
            fig_risk.update_layout(
                title="Risk/Getiri Dağılımı (Renk: Final Skor, Boyut: Skor)",
                xaxis_title="Max Drawdown %",
                yaxis_title="30G Getiri %",
                height=400
            )
            st.plotly_chart(fig_risk, use_container_width=True)
        
        st.markdown("### 📋 Sinyal Olayları Listesi")
        
        display_cols = ['Signal_ID', 'Hisse', 'Entry_Date', 'Entry_Price', 'Final_Score', 'Quality_Penalty',
                       'Trend_Quality', 'Money_Score', 'Momentum_Score', 'Breakout_Score', 
                       'RS_Score', 'Risk_Score', 'RSI', 'ADX', 'VolRatio', 'CMF',
                       '+30G_Getiri%', '+30G_Max_Getiri%', 'Max_DD_30G', 'Risk_Ratio_30G',
                       'Days_To_%10_Target', 'Is_Successful']
        
        available_cols = [col for col in display_cols if col in df.columns]
        
        def style_final_score(val):
            if val >= 75:
                return 'background-color: #9b59b6; color: white; font-weight: bold'
            elif val >= 60:
                return 'background-color: #2ecc71; color: white'
            elif val >= 45:
                return 'background-color: #f1c40f'
            else:
                return 'background-color: #e74c3c; color: white'
        
        styled_df = df[available_cols].style.map(style_final_score, subset=['Final_Score'])
        st.dataframe(styled_df, use_container_width=True, height=400)
        
        st.markdown("### 🏆 En İyi 5 Sinyal Olayı")
        top5 = df.nlargest(5, 'Final_Score')
        
        cols = st.columns(min(5, len(top5)))
        for i, (idx, row) in enumerate(top5.iterrows()):
            with cols[i]:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #9b59b6, #764ba2); 
                            padding: 15px; border-radius: 10px; color: white; text-align: center;">
                    <h3>{row['Hisse']}</h3>
                    <p style="font-size: 14px;">#{row['Signal_ID']}</p>
                    <p style="font-size: 20px; font-weight: bold;">{row['Final_Score']:.0f}</p>
                    <p style="font-size: 12px;">Sinyal Olayı</p>
                    <hr style="margin: 5px 0;">
                    <p style="font-size: 11px;">📅 {row['Entry_Date']}</p>
                    <p style="font-size: 12px;">💰 {row['Entry_Price']} TL</p>
                    <p style="font-size: 12px;">📊 RSI: {row.get('RSI', 'N/A')} | ADX: {row.get('ADX', 'N/A')}</p>
                    <p style="font-size: 11px;">📈 30G: %{row.get('+30G_Getiri%', 'N/A')}</p>
                    <p style="font-size: 10px;">🛡️ DD: {row.get('Max_DD_30G', 'N/A')}% | Risk: {row.get('Risk_Ratio_30G', 'N/A')}</p>
                    <p style="font-size: 10px;">🎯 %10 Hedef: {row.get('Days_To_%10_Target', 'N/A')} gün</p>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("### 📈 Ortalama Skor Bileşenleri")
        score_cols = ['Trend_Quality', 'Money_Score', 'Momentum_Score', 'Breakout_Score', 
                     'RS_Score', 'Risk_Score']
        available_score_cols = [col for col in score_cols if col in df.columns]
        
        if available_score_cols:
            score_data = df[available_score_cols].mean().reset_index()
            score_data.columns = ['Skor', 'Ortalama']
            
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=score_data['Skor'],
                y=score_data['Ortalama'],
                marker_color=['#667eea', '#764ba2', '#3498db', '#2ecc71', '#f1c40f', '#9b59b6'],
                text=score_data['Ortalama'].round(1),
                textposition='outside'
            ))
            fig3.update_layout(
                title="Ortalama Skor Bileşenleri",
                xaxis_title="Skor Türü",
                yaxis_title="Ortalama Değer",
                height=300
            )
            st.plotly_chart(fig3, use_container_width=True)
        
        # ===== İNDİRME =====
        c1, c2 = st.columns(2)
        with c1:
            csv_data = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                "📊 CSV İndir",
                csv_data,
                "sinyal_olaylari_backtest.csv",
                "text/csv"
            )
        with c2:
            export_df = df.head(5000) if len(df) > 5000 else df
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w:
                export_df.to_excel(w, index=False)
            st.download_button(
                "📑 Excel İndir",
                buf.getvalue(),
                "sinyal_olaylari_backtest.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    elif not btn:
        st.markdown("### 🎯 Sinyal Olayı Backtest Motoru V2.1 (FİNAL)")
        st.markdown("""
        **Event-Based Signal Backtest Engine - Final Sürüm:**

        **📌 KRİTİK: Sinyal Zamanlama Mantığı**
        - Seçilen tarih = **Kapanış günü**
        - Entry_Price = **Seçilen gün kapanış fiyatı**
        - Sinyal = **Kapanış sonrası oluşan durum**
        - Amaç = **Takip eden işlem günü için aday liste**
        - Örnek: 05.08.2026 seçildi → 05.08.2026 kapanış verisi → 06.08.2026 işlem planı

        **🔧 Son İyileştirmeler:**
        - ✅ **Tarih mantığı:** `<=` kullanıldı (seçilen gün dahil)
        - ✅ **Look-ahead bias koruması:** Sinyal anına kadar veri izolasyonu
        - ✅ **Önceden veri yükleme:** 10x-30x hız artışı
        - ✅ **İşlem günü bazlı cooldown:** `np.busday_count`
        - ✅ **Signal_ID temiz:** `.IS` kaldırıldı
        - ✅ **Başarı analizi:** Sadece test edilebilir sinyaller
        - ✅ **Portföy metrikleri:** Profit Factor, Expectancy, Sharpe-like
        - ✅ **Açıklama metni:** Yeni mantığa göre güncellendi

        **📊 Başarı Metriği:**
        - **Başarılı = +10G Max Getiri > 8% ve Max DD < 5%**

        **📈 Portföy Metrikleri:**
        - Profit Factor = Kazanç / Kayıp
        - Expectancy = (Kazanma Oranı × Ort. Kazanç) - (Kaybetme Oranı × Ort. Kayıp)
        - Sharpe-like = Ort. Getiri / Std. Getiri
        """)

if __name__ == "__main__":
    main()
