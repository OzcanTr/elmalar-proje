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

warnings.filterwarnings('ignore')

st.set_page_config(page_title="BIST Sinyal Olayı Backtest Motoru V2.4", page_icon="⚡", layout="wide")

# ===================== TEST MODU =====================
TEST_MODE = True

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
    
    if TEST_MODE:
        st.session_state.authenticated = True
        return True
    
    st.markdown("""<style>
        .login-box { max-width:400px; margin:80px auto; padding:2rem; background:white; 
                    border-radius:20px; box-shadow:0 20px 60px rgba(0,0,0,0.15); text-align:center; }
    </style>""", unsafe_allow_html=True)
    
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.markdown("### ⚡ BIST Sinyal Olayı Backtest Motoru V2.4")
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
            st.error("❌ Giriş yapılandırması bulunamadı! Lütfen secrets.toml dosyasını oluşturun veya TEST_MODE=True yapın.")
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
MIN_HISTORY = 120
STEPS = [5, 10, 15, 30, 60, 90]
FORWARD_DAYS = 60
MIN_FORWARD_DAYS = 5
SIGNAL_COOLDOWN = 10
CACHE_TTL = 86400  # 24 SAAT

cpu = os.cpu_count() or 4
WORKERS = min(16, cpu * 3)

# ===================== STRATEJİ PRESETLERİ (V2.4 - OPTİMİZE) =====================
STRATEGY_PRESETS = {
    "🎯 Veri Odaklı V2.4 (Optimize)": {
        'base_filters': {
            'RSI_max': 60, 'RSI_min': 25,
            'MA200_diff_min': -35, 'MA200_diff_max': 45,
            'ADX_min': 14,
            'Volume_MA_ratio': 0.5,
            'MFI_max': 70, 'MFI_min': 30,
            'Stochastic_max': 65, 'Stochastic_min': 5,
            'BB_Position_min': 0.03, 'BB_Position_max': 0.70,
            'CMF_min': -0.02,
        },
        'profiles': {
            'Erken': {'Min_Final_Score': 45, 'Min_ADX': 12},
            'Orta': {'Min_Final_Score': 55, 'Max_RSI': 55, 'Min_ADX': 16},
            'Sıkı': {'Min_Final_Score': 65, 'Max_RSI': 50, 'Min_RSI': 30, 
                     'Min_ADX': 20, 'Max_ADX': 35}
        },
        'desc': '🎯 Haziran 2025 verilerine göre optimize edildi'
    },
    "⚡ Hızlı Momentum & Breakout V2.3": {
        'base_filters': {
            'RSI_max': 65, 'RSI_min': 25,
            'MA200_diff_min': -40, 'MA200_diff_max': 60,
            'ADX_min': 10,
            'Volume_MA_ratio': 0.3,
            'MFI_max': 75, 'MFI_min': 25,
            'Stochastic_max': 75, 'Stochastic_min': 3,
            'BB_Position_min': 0.02, 'BB_Position_max': 0.75,
            'CMF_min': -0.05,
        },
        'profiles': {
            'Erken': {'Min_Final_Score': 40},
            'Orta': {'Min_Final_Score': 50, 'Max_RSI': 58, 'Min_ADX': 15},
            'Sıkı': {'Min_Final_Score': 60, 'Max_RSI': 52, 'Min_RSI': 30, 
                     'Min_ADX': 18, 'Max_ADX': 35}
        },
        'desc': '⚡ Orijinal V2.3 - En fazla sinyal'
    },
    "🔬 Hızlı Test": {
        'base_filters': {
            'RSI_max': 80, 'RSI_min': 15,
            'MA200_diff_min': -60, 'MA200_diff_max': 100,
            'ADX_min': 5,
            'Volume_MA_ratio': 0.2,
            'MFI_max': 90, 'MFI_min': 10,
            'Stochastic_max': 90, 'Stochastic_min': 2,
            'BB_Position_min': 0.01, 'BB_Position_max': 0.95,
            'CMF_min': -0.10,
        },
        'profiles': {},
        'desc': '🔬 Test için maksimum esneklik'
    }
}

# ===================== LİSTE =====================
@st.cache_data(ttl=3600)
def get_lists():
    try:
        b30 = sorted(set(bp.Index("XU030").component_symbols))
        b50 = sorted(set(bp.Index("XU050").component_symbols))
        b100 = sorted(set(bp.Index("XU100").component_symbols))
        return {'BIST30':b30, 'BIST50':b50, 'BIST100':b100, 'Takip':["ASELS","THYAO","SISE","EREGL","BIMAS"]}
    except:
        return {'Takip':["ASELS","THYAO","SISE","EREGL","BIMAS"]}

# ===================== HIZLI VERİ ÇEKME =====================
@st.cache_data(ttl=CACHE_TTL)
def get_data_fast(symbol, date_str):
    """Hızlı veri çekme"""
    try:
        ref = pd.to_datetime(date_str)
        today = datetime.now().date()
        
        if ref.date() > today:
            ref = pd.Timestamp(today)
        
        sym = symbol.upper().strip()
        if not sym.endswith(".IS"): sym += ".IS"
        
        start = (ref - timedelta(days=LOOKBACK*2)).strftime('%Y-%m-%d')
        
        days_until_today = (today - ref.date()).days
        
        if days_until_today >= MIN_FORWARD_DAYS:
            end = (ref + timedelta(days=FORWARD_DAYS)).strftime('%Y-%m-%d')
            if pd.to_datetime(end).date() > today:
                end = today.strftime('%Y-%m-%d')
        else:
            end = ref.strftime('%Y-%m-%d')
        
        ticker = bp.Ticker(sym)
        df = ticker.history(start=start, end=end)
        
        if df is None or len(df) == 0:
            return None
        
        df = df.reset_index()
        
        date_col = None
        for c in df.columns:
            if 'date' in str(c).lower() or 'index' in str(c).lower():
                date_col = c
                break
        
        if date_col is None:
            date_col = df.columns[0]
        
        df = df.rename(columns={date_col: 'Date'})
        df['Date'] = pd.to_datetime(df['Date'])
        
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
    except Exception as e:
        return None

# ===================== GÖSTERGE HESAPLAMA =====================
def calc_indicators_fast(df):
    """Hızlı gösterge hesaplama"""
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
    
    for p in [5, 10, 20, 50, 200]:
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
    
    # STOCHASTIC
    high_14 = clean_df['High'].rolling(14).max()
    low_14 = clean_df['Low'].rolling(14).min()
    denom = (high_14 - low_14).replace(0, np.nan)
    clean_df['Stochastic'] = 100 * (clean_df['Close'] - low_14) / denom
    clean_df['Stochastic'] = clean_df['Stochastic'].fillna(50)
    
    # ADX - WILDER
    tr = np.maximum(clean_df['High']-clean_df['Low'], 
                    np.maximum(abs(clean_df['High']-clean_df['Close'].shift()), 
                              abs(clean_df['Low']-clean_df['Close'].shift())))
    atr = pd.Series(tr).ewm(alpha=1/14, adjust=False).mean()
    
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
    
    # VolRatio
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
    
    # BB Position
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
    
    # MA200 Mesafe
    clean_df['MA200_Mesafe%'] = ((clean_df['Close'] - clean_df['MA200']) / clean_df['MA200']) * 100
    
    # Slope'lar
    indicators = ['RSI', 'ADX', 'Stochastic', 'VolRatio', 'BB_Position', 'MFI', 'CMF']
    for ind in indicators:
        if ind in clean_df.columns:
            clean_df[f'{ind}_Slope3'] = clean_df[ind].diff(3).fillna(0)
            clean_df[f'{ind}_Slope5'] = clean_df[ind].diff(5).fillna(0)
    
    return clean_df

# ===================== SKORLAMA (V2.4 - OPTİMİZE) =====================
def score_stock_v24_optimize(r):
    """V2.4 - Optimize skorlama (Haziran 2025 verilerine göre)"""
    s = 0
    adx = r.get('ADX', 20)
    rsi = r.get('RSI', 50)
    vol = r.get('VolRatio', 1)
    cmf = r.get('CMF', 0)
    stoch = r.get('Stochastic', 50)
    bb = r.get('BB_Position', 0.5)
    ma200_dist = r.get('MA200_Mesafe%', 0)
    
    # ===== TREND YÖNÜ SKORU =====
    ma5 = r.get('MA5', 0)
    ma10 = r.get('MA10', 0)
    ma20 = r.get('MA20', 0)
    close = r.get('Close', 0)
    ma50 = r.get('MA50', 0)
    ma200_val = r.get('MA200', 0)
    
    trend_score = 0
    if ma5 > ma10 > ma20:
        trend_score = 15
    elif ma5 > ma10 and ma10 <= ma20:
        trend_score = 10
    elif ma5 > ma20:
        trend_score = 7
    elif abs(ma5 - ma10) / (ma10 + 0.001) < 0.003:
        trend_score = 3
    elif ma5 < ma10 < ma20:
        trend_score = -10
    else:
        trend_score = 0
    
    s += trend_score
    
    # ===== MA50/200 FİLTRE/BONUS =====
    if close > ma50:
        s += 3
    if close > ma200_val:
        s += 5
    if 0 <= ma200_dist <= 10:
        s += 4
    elif ma200_dist > 40:
        s -= 4
    
    # ===== ANA KATMANLAR =====
    # Trend Quality (10%)
    if 16 <= adx <= 22: s += 10
    elif 22 < adx <= 28: s += 8
    elif 28 < adx <= 35: s += 5
    elif 12 <= adx < 16: s += 7
    else: s += 0
    
    # Money Flow (15%)
    if 45 <= rsi <= 58: s += 10
    elif 40 <= rsi < 45 or 58 < rsi <= 65: s += 7
    else: s += 0
    if cmf > 0.05: s += 5
    elif cmf > 0: s += 3
    
    # Momentum (15% - DÜŞÜRÜLDÜ)
    mom_score = 0
    if 'ADX_Slope3' in r and not pd.isna(r.get('ADX_Slope3', 0)):
        mom_score += r['ADX_Slope3'] * 2
    if 'CMF_Slope3' in r and not pd.isna(r.get('CMF_Slope3', 0)):
        mom_score += r['CMF_Slope3'] * 20
    if 'RSI_Slope3' in r and not pd.isna(r.get('RSI_Slope3', 0)):
        mom_score += r['RSI_Slope3'] * 1.5
    if 'VolRatio_Slope3' in r and not pd.isna(r.get('VolRatio_Slope3', 0)):
        mom_score += r['VolRatio_Slope3'] * 1.5
    
    mom_score = max(-30, min(30, mom_score))
    mom_norm = max(0, min(100, (mom_score / 30) * 50 + 50))
    s += mom_norm * 0.15
    
    # Breakout (25% - ARTIRILDI)
    br_score = 0
    if bb > 0.80: br_score += 12
    elif bb > 0.65: br_score += 8
    elif bb > 0.50: br_score += 5
    elif bb > 0.35: br_score += 3
    
    if stoch > 60: br_score += 8
    elif stoch > 40: br_score += 5
    elif stoch > 20: br_score += 3
    
    if vol > 1.0: br_score += 7
    elif vol > 0.7: br_score += 4
    
    s += br_score
    
    # Relative Strength (15%)
    rs_score = r.get('RS_Score', 0)
    s += rs_score * 0.75
    
    # ===== BONUSLAR =====
    if adx > 35:
        s += 8
    elif adx > 25:
        s += 5
    
    if vol > 1.2:
        s += 4
    
    if cmf > 0.10:
        s += 3
    
    if stoch < 30 and r.get('Stochastic_Slope3', 0) > 0:
        s += 4
    
    if 0.45 <= bb <= 0.65:
        s += 3
    
    # ===== CEZALAR =====
    penalty = 0
    if stoch > 85 and bb > 0.85: penalty += 3
    if rsi > 75: penalty += 2
    if ma200_dist > 50: penalty += 3
    if vol < 0.5: penalty += 2
    if cmf < -0.10: penalty += 2
    
    # V2.4 Ek Cezalar
    if adx < 18 and rsi > 55:
        penalty += 3
    if vol < 0.6 and bb > 0.65:
        penalty += 3
    
    final_score = max(0, min(100, s - penalty))
    
    return {
        'Base_Score': round(final_score, 1),
        'Momentum_Score': round(mom_score, 1),
        'Breakout_Score': round(br_score, 1),
        'RS_Score': round(rs_score, 1),
        'Trend_Score': round(trend_score, 1),
        'Quality_Penalty': round(penalty, 1),
        'ADX_Bonus': 8 if adx > 35 else (5 if adx > 25 else 0),
        'Vol_Bonus': 4 if vol > 1.2 else 0,
        'CMF_Bonus': 3 if cmf > 0.10 else 0,
        'Final_Score': final_score
    }

def calculate_signal_score_v24_optimize(df, idx, symbol=None, index_df=None, date_index_map=None, min_final_score=40):
    row = df.iloc[idx]
    
    # RS Score hesapla
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
    
    # Skor verilerini hazırla
    score_data = {
        'ADX': row.get('ADX', 20),
        'RSI': row.get('RSI', 50),
        'VolRatio': row.get('VolRatio', 1),
        'CMF': row.get('CMF', 0),
        'Stochastic': row.get('Stochastic', 50),
        'BB_Position': row.get('BB_Position', 0.5),
        'MA200_Mesafe%': row.get('MA200_Mesafe%', 0),
        'RS_Score': rs_score,
        'ADX_Slope3': row.get('ADX_Slope3', 0),
        'CMF_Slope3': row.get('CMF_Slope3', 0),
        'RSI_Slope3': row.get('RSI_Slope3', 0),
        'VolRatio_Slope3': row.get('VolRatio_Slope3', 0),
        'Stochastic_Slope3': row.get('Stochastic_Slope3', 0),
        'MA5': row.get('MA5', 0),
        'MA10': row.get('MA10', 0),
        'MA20': row.get('MA20', 0),
        'MA50': row.get('MA50', 0),
        'MA200': row.get('MA200', 0),
        'Close': row.get('Close', 0),
    }
    
    scores = score_stock_v24_optimize(score_data)
    
    # ===== V2.4 FİLTRELER =====
    
    # 1. Trend Score = -10 olanları ele (başarısızların %78'i)
    if scores['Trend_Score'] < 0:
        return None
    
    # 2. Trend Score = 15 ama zayıf sinyalleri ele
    if scores['Trend_Score'] == 15:
        adx = row.get('ADX', 0)
        bb = row.get('BB_Position', 0)
        
        # ADX düşük veya BB yüksek ise ele
        if adx < 18 or bb > 0.65:
            return None
    
    if scores['Final_Score'] < min_final_score:
        return None
    
    return scores

# ===================== FİLTRE =====================
def check_signal_fast(df, i, base_filters):
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
        if pd.isna(cmf) or cmf < base_filters.get('CMF_min', -0.02):
            return False
        
        return True
    except:
        return False

def apply_filter_fast(r, filters):
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
        if r['Final_Score'] < filters.get('Min_Final_Score', 0): return False
        return True
    except:
        return False

# ===================== BAŞARI METRİĞİ =====================
def is_successful(signal_event):
    max_return = signal_event.get('+30G_Max_Getiri%')
    max_dd = signal_event.get('Max_DD_30G', 0)
    
    if max_return is None or max_dd is None or max_dd == 0:
        return None
    
    rr = max_return / max_dd
    if rr > 2:
        return 1
    else:
        return 0

# ===================== TARAMA =====================
def scan_stock_fast(sym, df_full, ref_date, base_filters, profile=None, 
                    index_df=None, date_index_map=None, min_final_score=40):
    try:
        if df_full is None or len(df_full) < MIN_HISTORY:
            return None
        
        df = calc_indicators_fast(df_full)
        if df is None:
            return None
        
        ref = pd.to_datetime(ref_date).normalize()
        dates = df['Date'].dt.normalize()
        
        valid = np.where(dates <= ref)[0]
        if len(valid) == 0:
            return None
        idx = valid[-1]
        
        signal_df = df.iloc[:idx+1].copy()
        signal_idx = len(signal_df) - 1
        
        if not check_signal_fast(signal_df, signal_idx, base_filters):
            return None
        
        signal_price = signal_df['Close'].iloc[signal_idx]
        signal_date = signal_df['Date'].iloc[signal_idx]
        
        ma200_diff = None
        if pd.notna(signal_df['MA200'].iloc[signal_idx]):
            ma200_diff = ((signal_price - signal_df['MA200'].iloc[signal_idx]) / signal_df['MA200'].iloc[signal_idx]) * 100
        
        clean_symbol = sym.replace(".IS", "")
        signal_id = f"{clean_symbol}_{signal_date.strftime('%Y%m%d')}"
        
        scores = calculate_signal_score_v24_optimize(signal_df, signal_idx, sym, index_df, date_index_map, min_final_score)
        if scores is None:
            return None
        
        signal_event = {
            'Signal_ID': signal_id,
            'Hisse': sym,
            'Signal_Date': signal_date.strftime('%Y-%m-%d'),
            'Entry_Price': round(signal_price, 2),
            
            'RSI': round(signal_df['RSI'].iloc[signal_idx], 1),
            'ADX': round(signal_df['ADX'].iloc[signal_idx], 1),
            'VolRatio': round(signal_df['VolRatio'].iloc[signal_idx], 2),
            'MFI': round(signal_df['MFI'].iloc[signal_idx], 1),
            'Stochastic': round(signal_df['Stochastic'].iloc[signal_idx], 1),
            'BB_Position': round(signal_df['BB_Position'].iloc[signal_idx], 2),
            'CMF': round(signal_df['CMF'].iloc[signal_idx], 3),
            'MA200_Mesafe%': round(ma200_diff, 1) if ma200_diff is not None else None,
            
            'MA5': round(signal_df['MA5'].iloc[signal_idx], 2),
            'MA10': round(signal_df['MA10'].iloc[signal_idx], 2),
            'MA20': round(signal_df['MA20'].iloc[signal_idx], 2),
            'MA50': round(signal_df['MA50'].iloc[signal_idx], 2),
            'MA200': round(signal_df['MA200'].iloc[signal_idx], 2),
            
            'Base_Score': scores['Base_Score'],
            'Momentum_Score': scores['Momentum_Score'],
            'Breakout_Score': scores['Breakout_Score'],
            'RS_Score': scores['RS_Score'],
            'Trend_Score': scores['Trend_Score'],
            'ADX_Bonus': scores['ADX_Bonus'],
            'Vol_Bonus': scores['Vol_Bonus'],
            'CMF_Bonus': scores['CMF_Bonus'],
            'Quality_Penalty': scores['Quality_Penalty'],
            'Final_Score': scores['Final_Score']
        }
        
        if profile:
            if not apply_filter_fast(signal_event, profile):
                return None
        
        if len(df) > idx + 1:
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
            
            signal_event['Is_Successful'] = is_successful(signal_event)
        else:
            signal_event['Is_Successful'] = None
        
        return signal_event
    except Exception as e:
        return None

def run_scan_fast(symbols, date, base_filters, profile=None, 
                  index_df=None, date_index_map=None, min_final_score=40):
    results = []
    ds = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
    
    data_cache = {}
    for sym in symbols:
        try:
            df = get_data_fast(sym, ds)
            if df is not None and len(df) >= MIN_HISTORY:
                data_cache[sym] = df
        except:
            continue
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {}
        for sym, df in data_cache.items():
            future = ex.submit(scan_stock_fast, sym, df, date, base_filters, 
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

# ===================== COOLDOWN =====================
def is_cooldown_active(hisse, signal_date, signal_history, cooldown_days):
    if hisse not in signal_history:
        return False
    
    last_signal = signal_history[hisse].get('last_date')
    if last_signal is None:
        return False
    
    try:
        bdiff = np.busday_count(
            np.datetime64(last_signal),
            np.datetime64(signal_date)
        )
        return bdiff <= cooldown_days
    except:
        days_diff = (pd.to_datetime(signal_date) - pd.to_datetime(last_signal)).days
        return days_diff <= cooldown_days

# ===================== ANA UYGULAMA =====================
def main():
    if not check_password():
        return
    
    defaults = {
        "strategy_preset": "🎯 Veri Odaklı V2.4 (Optimize)",
        "df": None, "ok": False, "t": 0, "days": 0,
        "min_final_score": 40,
        "signal_history": defaultdict(dict)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    
    c1, c2, c3 = st.columns([7,1,1])
    with c1: st.markdown('<div class="header">⚡ BIST SİNYAL OLAYI BACKTEST MOTORU V2.4 (OPTİMİZE)</div>', unsafe_allow_html=True)
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
        
        st.markdown("---")
        st.markdown("### 📊 AĞIRLIKLAR (V2.4 - Optimize)")
        st.caption("""
        Trend Yönü: +Bonus | Trend Kalite: 10% | Money Flow: 15% | Momentum: 15% | Breakout: 25% | RS: 15%
        MA50/200: Filtre + Bonus
        **FİLTRELER:** Trend Score < 0 elenir | Trend Score 15 ve ADX<18 veya BB>0.65 elenir
        """)
        
        st.markdown("---")
        st.markdown("### 🔍 TEMEL FİLTRELER")
        
        col1, col2 = st.columns(2)
        with col1:
            rsi_min = st.number_input("RSI Min", 0, 100, base_filters['RSI_min'], 1)
        with col2:
            rsi_max = st.number_input("RSI Max", 0, 100, base_filters['RSI_max'], 1)
        
        adx_min = st.number_input("ADX Min", 0, 50, base_filters['ADX_min'], 1)
        vol_min = st.number_input("Min Volume", 0.0, 3.0, base_filters['Volume_MA_ratio'], 0.05)
        
        col1, col2 = st.columns(2)
        with col1:
            stoch_min = st.number_input("Stoch Min", 0, 100, base_filters['Stochastic_min'], 1)
        with col2:
            stoch_max = st.number_input("Stoch Max", 0, 100, base_filters['Stochastic_max'], 1)
        
        col1, col2 = st.columns(2)
        with col1:
            bb_min = st.number_input("BB Min", 0.0, 1.0, base_filters['BB_Position_min'], 0.01)
        with col2:
            bb_max = st.number_input("BB Max", 0.0, 1.0, base_filters['BB_Position_max'], 0.01)
        
        cmf_min = st.number_input("CMF Min", -0.5, 0.5, base_filters.get('CMF_min', -0.02), 0.01)
        
        col1, col2 = st.columns(2)
        with col1:
            ma200_min = st.number_input("MA200 Min %", -100, 0, base_filters['MA200_diff_min'], 1)
        with col2:
            ma200_max = st.number_input("MA200 Max %", 0, 200, base_filters['MA200_diff_max'], 1)
        
        current_filters = {
            'RSI_max': rsi_max, 'RSI_min': rsi_min,
            'MA200_diff_min': ma200_min, 'MA200_diff_max': ma200_max,
            'ADX_min': adx_min,
            'Volume_MA_ratio': vol_min,
            'MFI_max': base_filters.get('MFI_max', 70),
            'MFI_min': base_filters.get('MFI_min', 30),
            'Stochastic_max': stoch_max, 'Stochastic_min': stoch_min,
            'BB_Position_min': bb_min, 'BB_Position_max': bb_max,
            'CMF_min': cmf_min,
        }
        
        st.markdown("---")
        st.markdown("### 📊 PROFİL FİLTRELERİ")
        
        profile_names = list(strategy['profiles'].keys())
        selected_profile = st.selectbox("📊 Filtre Profili", ["Hiçbiri"] + profile_names)
        profile = strategy['profiles'].get(selected_profile) if selected_profile != "Hiçbiri" else None
        
        if profile:
            st.caption("📌 **Mevcut Profil:** " + selected_profile)
            for key, value in profile.items():
                st.caption(f"  • {key}: {value}")
        
        st.markdown("---")
        st.markdown("### 📊 SİNYAL FİLTRELERİ")
        
        min_final_score = st.slider(
            "Minimum Final Skor",
            0, 100, st.session_state.min_final_score, 5
        )
        st.session_state.min_final_score = min_final_score
        
        st.markdown("---")
        st.markdown("### 🔄 SİNYAL COOLDOWN")
        
        use_cooldown = st.checkbox("Cooldown aktif", value=True)
        cooldown_days = st.slider(
            "Cooldown işlem günü",
            0, 30, SIGNAL_COOLDOWN, 1
        )
        
        st.markdown("---")
        
        lists = get_lists()
        secim = st.selectbox("📋 Liste", list(lists.keys()))
        symbols = lists[secim]
        st.caption(f"{len(symbols)} hisse")
        
        st.markdown("### 📅 Tarama Aralığı")
        tip = st.radio("Tip", ["Tek Tarih", "Tarih Aralığı", "Ay"], horizontal=True)
        
        if tip == "Tek Tarih":
            d = turkish_date_picker("Tarih Seçin", datetime(2025, 6, 1), "tek")
            start = end = d
            
        elif tip == "Tarih Aralığı":
            c1, c2 = st.columns(2)
            with c1:
                start = turkish_date_picker("Başlangıç", datetime(2025, 6, 1), "bas")
            with c2:
                end = turkish_date_picker("Bitiş", datetime(2025, 6, 30), "bit")
                
        else:
            c1, c2 = st.columns(2)
            with c1:
                y = st.selectbox("Yıl", range(2020, 2031), index=5, key="yy")
            with c2:
                m = st.selectbox("Ay", range(1, 13), format_func=lambda x: TURKISH_MONTHS[x-1], index=5, key="mm")
            start = datetime(y, m, 1).date()
            end = (datetime(y, m+1, 1) if m < 12 else datetime(y+1, 1, 1)).date() - timedelta(days=1)
        
        bdays = get_bdays(pd.to_datetime(start), pd.to_datetime(end))
        days = len(bdays)
        
        today = datetime.now().date()
        if isinstance(end, datetime):
            end_date = end.date()
        else:
            end_date = end
        
        if end_date > today:
            st.warning(f"⚠️ Seçilen bitiş tarihi ({end_date}) bugünden ({today}) ileri!")
            st.info(f"📌 Sistem bugünün tarihine ({today}) kadar olan verileri kullanacak.")
            end = today
            bdays = get_bdays(pd.to_datetime(start), pd.to_datetime(end))
            days = len(bdays)
        
        st.markdown("---")
        st.markdown(f"📊 **{days}** işlem günü | 📋 **{len(symbols)}** hisse")
        st.markdown(f"⏱️ ~**{days*len(symbols)*0.03/WORKERS:.0f}s**")
        
        btn = st.button("⚡ TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        
        with st.spinner('📊 BIST100 verisi hazırlanıyor...'):
            index_df = None
            date_index_map = None
            try:
                index_data = get_data_fast('XU100', end.strftime('%Y-%m-%d'))
                if index_data is not None:
                    index_df = calc_indicators_fast(index_data)
                    if index_df is not None:
                        date_index_map = {
                            pd.Timestamp(d).normalize(): i 
                            for i, d in enumerate(index_df['Date'])
                        }
            except:
                pass
        
        with st.spinner(f'⚡ {days} gün taranıyor... (V2.4 Optimize)'):
            all_signals = []
            signal_history = st.session_state.signal_history
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | {i+1}/{days}")
                
                res = run_scan_fast(symbols, day, current_filters, profile, 
                                    index_df, date_index_map, min_final_score)
                if res:
                    for signal in res:
                        hisse = signal['Hisse']
                        signal_date = signal['Signal_Date']
                        
                        if use_cooldown:
                            if is_cooldown_active(hisse, signal_date, signal_history, cooldown_days):
                                continue
                        
                        all_signals.append(signal)
                        
                        signal_history[hisse] = {
                            'last_date': signal_date,
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
            st.warning("⚠️ Sinyal olayı bulunamadı! Lütfen filtreleri gevşetin veya tarih aralığını değiştirin.")
            st.session_state.ok = False
    
    if st.session_state.get('ok') and st.session_state.df is not None:
        df = st.session_state.df
        
        st.markdown(f"### 📊 {len(df)} Sinyal Olayı | ⚡ {st.session_state.t:.1f}s | 📅 {st.session_state.days} gün")
        
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("Toplam Sinyal", len(df))
        with c2: st.metric("Ort. Final Skor", f"{df['Final_Score'].mean():.0f}")
        
        unique_stocks = df['Hisse'].nunique()
        with c3: st.metric("📋 Benzersiz Hisse", f"{unique_stocks}")
        
        success_df = df[df['Is_Successful'].notna()]
        if len(success_df) > 0:
            success_rate = success_df['Is_Successful'].sum() / len(success_df) * 100
            with c4: st.metric("✅ Başarı Oranı (RR>2)", f"%{success_rate:.0f}")
        else:
            with c4: st.metric("✅ Başarı Oranı", "Veri Yok")
        
        r30 = df['+30G_Getiri%'].dropna()
        with c5:
            if len(r30) > 0:
                st.metric("📈 30G Ort. Getiri", f"%{r30.mean():.1f}")
            else:
                st.metric("📈 30G Ort. Getiri", "Veri Yok")
        
        # MA Trend Analizi
        st.markdown("### 📈 MA Trend Analizi")
        ma_cols = ['MA5', 'MA10', 'MA20', 'MA50', 'MA200']
        if all(col in df.columns for col in ma_cols):
            ma_data = df[ma_cols].mean().reset_index()
            ma_data.columns = ['MA', 'Ortalama']
            
            fig_ma = go.Figure()
            fig_ma.add_trace(go.Bar(
                x=ma_data['MA'],
                y=ma_data['Ortalama'],
                marker_color=['#3498db', '#2ecc71', '#f1c40f', '#e67e22', '#e74c3c'],
                text=ma_data['Ortalama'].round(2),
                textposition='outside'
            ))
            fig_ma.update_layout(
                title="Ortalama Hareketli Ortalama Değerleri",
                xaxis_title="MA Türü",
                yaxis_title="Ortalama Fiyat",
                height=250
            )
            st.plotly_chart(fig_ma, use_container_width=True)
        
        # Bonus dağılımı
        st.markdown("### 🎯 Bonus Dağılımı")
        bonus_cols = ['ADX_Bonus', 'Vol_Bonus', 'CMF_Bonus']
        if all(col in df.columns for col in bonus_cols):
            bonus_data = df[bonus_cols].sum()
            fig_bonus = go.Figure()
            fig_bonus.add_trace(go.Bar(
                x=bonus_data.index,
                y=bonus_data.values,
                marker_color=['#3498db', '#2ecc71', '#f1c40f'],
                text=bonus_data.values,
                textposition='outside'
            ))
            fig_bonus.update_layout(
                title="Toplam Bonus Dağılımı",
                xaxis_title="Bonus Türü",
                yaxis_title="Toplam Bonus Puanı",
                height=250
            )
            st.plotly_chart(fig_bonus, use_container_width=True)
        
        # Skor dağılımı
        st.markdown("### 📊 Skor Bileşenleri")
        score_cols = ['Base_Score', 'Momentum_Score', 'Breakout_Score', 'RS_Score', 'Trend_Score']
        available_cols = [col for col in score_cols if col in df.columns]
        
        if available_cols:
            score_data = df[available_cols].mean().reset_index()
            score_data.columns = ['Skor', 'Ortalama']
            
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=score_data['Skor'],
                y=score_data['Ortalama'],
                marker_color=['#667eea', '#764ba2', '#3498db', '#2ecc71', '#f1c40f'],
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
        
        # Tekrar sinyal analizi
        st.markdown("### 🔄 Tekrar Sinyal Veren Hisseler")
        
        repeat_df = df.groupby('Hisse').agg(
            Sinyal=('Signal_ID', 'count'),
            Test=('Is_Successful', 'count'),
            Basari=('Is_Successful', 'sum'),
            Ort_Skor=('Final_Score', 'mean'),
            Ort_30G=('+30G_Getiri%', 'mean'),
            Ort_DD=('Max_DD_30G', 'mean')
        ).reset_index()
        
        def calculate_success_rate(row):
            test = row['Test']
            basari = row['Basari']
            
            if pd.isna(test) or pd.isna(basari):
                return 0.0
            if test == 0:
                return 0.0
            
            test = float(test)
            basari = float(basari)
            
            return round((basari / test * 100), 1)
        
        repeat_df['Başarı_Oranı'] = repeat_df.apply(calculate_success_rate, axis=1)
        
        repeat_df = repeat_df.fillna(0)
        repeat_df = repeat_df.sort_values('Sinyal', ascending=False)
        
        display_repeat = repeat_df[['Hisse', 'Sinyal', 'Test', 'Başarı_Oranı', 'Ort_Skor', 'Ort_30G', 'Ort_DD']]
        display_repeat.columns = ['Hisse', 'Sinyal_Sayısı', 'Test_Sayısı', 'Başarı_Oranı', 'Ort_Skor', 'Ort_30G_Getiri', 'Ort_DD']
        st.dataframe(display_repeat.head(10), use_container_width=True)
        
        # Sinyal listesi
        st.markdown("### 📋 Sinyal Olayları Listesi")
        
        display_cols = ['Signal_ID', 'Hisse', 'Signal_Date', 'Entry_Price', 'Final_Score',
                       'Base_Score', 'Momentum_Score', 'Breakout_Score', 'RS_Score', 'Trend_Score',
                       'ADX_Bonus', 'Vol_Bonus', 'CMF_Bonus', 'Quality_Penalty',
                       'RSI', 'ADX', 'VolRatio', 'CMF', 'BB_Position',
                       'MA5', 'MA10', 'MA20', 'MA50', 'MA200',
                       '+30G_Getiri%', 'Max_DD_30G', 'Is_Successful']
        
        available_cols = [col for col in display_cols if col in df.columns]
        
        def style_final_score(val):
            if val >= 70:
                return 'background-color: #9b59b6; color: white; font-weight: bold'
            elif val >= 60:
                return 'background-color: #2ecc71; color: white'
            elif val >= 50:
                return 'background-color: #f1c40f'
            else:
                return 'background-color: #e74c3c; color: white'
        
        styled_df = df[available_cols].style.map(style_final_score, subset=['Final_Score'])
        st.dataframe(styled_df, use_container_width=True, height=400)
        
        # İndirme
        c1, c2 = st.columns(2)
        with c1:
            csv_data = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                "📊 CSV İndir",
                csv_data,
                "sinyal_olaylari_v24_optimize.csv",
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
                "sinyal_olaylari_v24_optimize.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    elif not btn:
        st.markdown("### ⚡ Sinyal Olayı Backtest Motoru V2.4 (Optimize)")
        st.markdown("""
        **V2.4 Optimize Sürüm - Haziran 2025 Verilerine Göre:**

        **📊 Değişiklikler:**
        | Özellik | Önceki | Yeni |
        |---------|--------|------|
        | Momentum Ağırlığı | 25% | **15%** |
        | Breakout Ağırlığı | 20% | **25%** |
        | Trend Score < 0 | Dahil | **Otomatik Elenir** |
        | Trend Score 15 | Normal | **ADX<18 veya BB>0.65 ise elenir** |
        | RSI Aralığı | 25-65 | **25-60** |
        | ADX Min | 10 | **14** |
        | CMF Min | -0.05 | **-0.02** |
        | BB Max | 0.75 | **0.70** |

        **📈 MA Kullanımı:**
        | MA | Kullanım Amacı |
        |----|----------------|
        | **MA5** | Çok kısa vadeli trend |
        | **MA10** | Kısa vadeli trend |
        | **MA20** | Ana kısa/orta trend yönü |
        | **MA50** | Trend filtresi |
        | **MA200** | Uzun vadeli filtre |

        **⚡ Hız:**
        - İlk tarama: ~15-20 saniye (100 hisse)
        - Sonraki taramalar (24 saat içinde): **~2-3 saniye**
        """)

if __name__ == "__main__":
    main()
