import streamlit as st
import pandas as pd
import numpy as np
import borsapy as bp
from datetime import datetime, timedelta
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import BytesIO
import plotly.graph_objects as go
import os
from collections import defaultdict
import logging

warnings.filterwarnings('ignore')

# Logging ayarları
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="BIST Sinyal Olayı Backtest Motoru V2.5", page_icon="⚡", layout="wide")

# ===================== TEST MODU =====================
TEST_MODE = True
DEFAULT_USER = "ADMIN"
DEFAULT_PASSWORD = "Elma*"

# ===================== TÜRKÇE TARİH SEÇİCİ =====================
TURKISH_MONTHS = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
TURKISH_DAYS = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]

def turkish_date_picker(label, default_date=None, key="tcal", min_date=None, max_date=None):
    if default_date is None:
        default_date = datetime.now().date() - timedelta(days=1)
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
    st.markdown("### ⚡ BIST Sinyal Olayı Backtest Motoru V2.5")
    st.markdown("#### Yetkili Giriş")
    
    msg = st.empty()
    user = st.text_input("👤 Kullanıcı", key=f"u_{st.session_state.login_counter}")
    pwd = st.text_input("🔒 Şifre", type="password", key=f"p_{st.session_state.login_counter}")
    
    if st.button("🚀 GİRİŞ", use_container_width=True, type="primary", key=f"b_{st.session_state.login_counter}"):
        try:
            correct_user = st.secrets.get("USER", DEFAULT_USER)
            correct_pwd = st.secrets.get("PASSWORD", DEFAULT_PASSWORD)
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
            st.error(f"❌ Giriş yapılandırması bulunamadı! Hata: {e}")
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
CACHE_TTL = 86400

cpu = os.cpu_count() or 4
WORKERS = min(40, cpu * 5)  # I/O ağırlıklı

# ===================== STRATEJİ PRESETLERİ =====================
STRATEGY_PRESETS = {
    "🎯 Veri Odaklı V2.5 (Optimize)": {
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
        'desc': '🎯 V2.5 - Optimize mimari'
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
        'desc': '⚡ Orijinal V2.3'
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
    except Exception as e:
        logger.warning(f"Liste alınamadı: {e}")
        return {'Takip':["ASELS","THYAO","SISE","EREGL","BIMAS"]}

# ===================== VERİ ÇEKME =====================
@st.cache_data(ttl=CACHE_TTL)
def get_data_range(symbol, start_str, end_str):
    """Tarih aralığı için tek seferde veri çek"""
    try:
        sym = symbol.upper().strip()
        if not sym.endswith(".IS"): sym += ".IS"
        
        ticker = bp.Ticker(sym)
        df = ticker.history(start=start_str, end=end_str)
        
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
        logger.warning(f"Veri çekme hatası ({symbol}): {e}")
        return None

# ===================== GÖSTERGE HESAPLAMA =====================
def calc_indicators_optimized(df, index_df=None, date_index_map=None):
    """Tek seferde tüm göstergeleri hesapla (RS Score dahil)"""
    if df is None or len(df) < MIN_HISTORY:
        return None
    
    df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
    
    clean_df = pd.DataFrame(index=df.index)
    clean_df['Date'] = df['Date'].values
    clean_df['Open'] = df['Open'].values.astype(float)
    clean_df['High'] = df['High'].values.astype(float)
    clean_df['Low'] = df['Low'].values.astype(float)
    clean_df['Close'] = df['Close'].values.astype(float)
    clean_df['Volume'] = df['Volume'].values.astype(float)
    
    close = clean_df['Close']
    high = clean_df['High']
    low = clean_df['Low']
    volume = clean_df['Volume']
    
    # MA'lar
    for p in [5, 10, 20, 50, 200]:
        clean_df[f'MA{p}'] = close.rolling(p).mean()
    
    # VMA'lar
    for p in [5, 10, 20]:
        clean_df[f'VMA{p}'] = volume.rolling(p).mean()
    
    # RSI - Wilder
    d = close.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    clean_df['RSI'] = 100 - 100/(1+rs)
    
    # Stochastic
    high_14 = high.rolling(14).max()
    low_14 = low.rolling(14).min()
    clean_df['Stochastic'] = 100 * (close - low_14) / (high_14 - low_14).replace(0, np.nan)
    
    # ADX - Wilder (index korunarak)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    
    atr = tr.ewm(alpha=1/14, adjust=False).mean()
    
    up_move = high - high.shift()
    down_move = low.shift() - low
    
    dp = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=df.index)
    dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=df.index)
    
    di_plus = 100 * (dp.ewm(alpha=1/14, adjust=False).mean() / atr)
    di_minus = 100 * (dm.ewm(alpha=1/14, adjust=False).mean() / atr)
    
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus).replace(0, np.nan)
    clean_df['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()
    
    # VolRatio
    vma20 = clean_df['VMA20'].replace(0, np.nan)
    clean_df['VolRatio'] = volume / vma20
    
    # MFI
    tp = (high + low + close) / 3
    mf = tp * volume
    pf = mf.where(tp > tp.shift(), 0).rolling(14).sum()
    nf = mf.where(tp < tp.shift(), 0).rolling(14).sum()
    clean_df['MFI'] = 100 - 100/(1 + pf / nf.replace(0, np.nan))
    
    # BB Position
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_range = bb_upper - bb_lower
    clean_df['BB_Position'] = np.where(bb_range > 0, (close - bb_lower) / bb_range, 0.5)
    clean_df['BB_Mid'] = bb_mid
    clean_df['BB_Upper'] = bb_upper
    clean_df['BB_Lower'] = bb_lower
    
    # CMF
    high_low = high - low
    mf_multiplier = ((close - low) - (high - close)) / high_low.replace(0, np.nan)
    mf_volume = mf_multiplier * volume
    clean_df['CMF'] = mf_volume.rolling(20).sum() / volume.rolling(20).sum()
    
    # MA200 Mesafe
    clean_df['MA200_Mesafe%'] = ((close - clean_df['MA200']) / clean_df['MA200']) * 100
    
    # RS Score'u indikatör aşamasında hesapla
    clean_df['RS_5'] = close.pct_change(5) * 100
    clean_df['RS_10'] = close.pct_change(10) * 100
    clean_df['RS_20'] = close.pct_change(20) * 100
    
    clean_df['RS_Score'] = 0
    if index_df is not None and date_index_map is not None:
        try:
            for i in clean_df.index:
                if i < 20:
                    continue
                current_date = pd.Timestamp(clean_df['Date'].iloc[i]).normalize()
                if current_date in date_index_map:
                    index_idx = date_index_map[current_date]
                    if index_idx < 20:
                        continue
                    
                    rs_values = []
                    for period in [5, 10, 20]:
                        stock_ret = clean_df[f'RS_{period}'].iloc[i]
                        if pd.notna(stock_ret) and index_idx >= period:
                            index_start = index_df['Close'].iloc[index_idx - period]
                            if index_start > 0:
                                index_ret = ((index_df['Close'].iloc[index_idx] - index_start) / index_start) * 100
                                rs_values.append(stock_ret - index_ret)
                    
                    if rs_values:
                        avg_rs = np.mean(rs_values)
                        if avg_rs > 3: clean_df.loc[i, 'RS_Score'] = 20
                        elif avg_rs > 1: clean_df.loc[i, 'RS_Score'] = 15
                        elif avg_rs > 0: clean_df.loc[i, 'RS_Score'] = 10
                        elif avg_rs > -1: clean_df.loc[i, 'RS_Score'] = 5
        except Exception as e:
            logger.warning(f"RS Score hesaplama hatası: {e}")
    
    # Slope'lar
    for ind in ['RSI', 'ADX', 'Stochastic', 'VolRatio', 'BB_Position', 'MFI', 'CMF']:
        if ind in clean_df.columns:
            clean_df[f'{ind}_Slope3'] = clean_df[ind].diff(3)
            clean_df[f'{ind}_Slope5'] = clean_df[ind].diff(5)
    
    return clean_df

# ===================== SKORLAMA =====================
def score_stock_v25_optimize(r):
    """V2.5 Optimize skorlama"""
    s = 0
    adx = r.get('ADX', 20) or 20
    rsi = r.get('RSI', 50) or 50
    vol = r.get('VolRatio', 1) or 1
    cmf = r.get('CMF', 0) or 0
    stoch = r.get('Stochastic', 50) or 50
    bb = r.get('BB_Position', 0.5) or 0.5
    ma200_dist = r.get('MA200_Mesafe%', 0) or 0
    
    ma5 = r.get('MA5', 0) or 0
    ma10 = r.get('MA10', 0) or 0
    ma20 = r.get('MA20', 0) or 0
    close = r.get('Close', 0) or 0
    ma50 = r.get('MA50', 0) or 0
    ma200_val = r.get('MA200', 0) or 0
    
    # Trend yönü
    if ma5 > ma10 > ma20:
        trend_score = 15
    elif ma5 > ma10:
        trend_score = 10
    elif ma5 > ma20:
        trend_score = 7
    elif ma5 < ma10 < ma20:
        trend_score = -10
    else:
        trend_score = 0
    
    s += trend_score
    
    # MA50/200 bonus
    if close > ma50: s += 3
    if close > ma200_val: s += 5
    if 0 <= ma200_dist <= 10: s += 4
    elif ma200_dist > 40: s -= 4
    
    # Trend kalitesi
    if 16 <= adx <= 22: s += 10
    elif 22 < adx <= 28: s += 8
    elif 28 < adx <= 35: s += 5
    elif 12 <= adx < 16: s += 7
    
    # Money flow
    if 45 <= rsi <= 58: s += 10
    elif 40 <= rsi < 45 or 58 < rsi <= 65: s += 7
    if cmf > 0.05: s += 5
    elif cmf > 0: s += 3
    
    # Momentum
    mom_score = 0
    for ind, mult in [('ADX', 2), ('CMF', 20), ('RSI', 1.5), ('VolRatio', 1.5)]:
        slope_key = f'{ind}_Slope3'
        if slope_key in r and not pd.isna(r.get(slope_key)):
            mom_score += r[slope_key] * mult
    
    mom_score = max(-30, min(30, mom_score or 0))
    mom_norm = max(0, min(100, (mom_score / 30) * 50 + 50))
    s += mom_norm * 0.15
    
    # Breakout
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
    
    # RS Score (indikatör aşamasında hesaplandı)
    rs_score = r.get('RS_Score', 0) or 0
    s += rs_score * 0.75
    
    # Bonuslar
    if adx > 35: s += 8
    elif adx > 25: s += 5
    if vol > 1.2: s += 4
    if cmf > 0.10: s += 3
    if (stoch or 50) < 30 and (r.get('Stochastic_Slope3') or 0) > 0: s += 4
    if 0.45 <= bb <= 0.65: s += 3
    
    # Cezalar
    penalty = 0
    if stoch > 85 and bb > 0.85: penalty += 3
    if rsi > 75: penalty += 2
    if ma200_dist > 50: penalty += 3
    if vol < 0.5: penalty += 2
    if cmf < -0.10: penalty += 2
    if adx < 18 and rsi > 55: penalty += 3
    if vol < 0.6 and bb > 0.65: penalty += 3
    
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

# ===================== FİLTRELER =====================
def check_signal_fast(df, idx, base_filters):
    """Tek bir indekste sinyal kontrolü"""
    try:
        row = df.iloc[idx]
        
        rsi = row['RSI']
        if pd.isna(rsi) or rsi > base_filters['RSI_max'] or rsi < base_filters['RSI_min']:
            return False
        
        if pd.isna(row['MA200']):
            return False
        
        ma200_diff = row['MA200_Mesafe%']
        if pd.isna(ma200_diff) or ma200_diff < base_filters['MA200_diff_min'] or ma200_diff > base_filters['MA200_diff_max']:
            return False
        
        adx = row['ADX']
        if pd.isna(adx) or adx < base_filters['ADX_min']:
            return False
        
        vol = row['VolRatio']
        if pd.isna(vol) or vol < base_filters['Volume_MA_ratio']:
            return False
        
        mfi = row['MFI']
        if pd.isna(mfi) or mfi > base_filters['MFI_max'] or mfi < base_filters['MFI_min']:
            return False
        
        stoch = row['Stochastic']
        if pd.isna(stoch) or stoch > base_filters['Stochastic_max'] or stoch < base_filters['Stochastic_min']:
            return False
        
        bb = row['BB_Position']
        if pd.isna(bb) or bb > base_filters['BB_Position_max'] or bb < base_filters['BB_Position_min']:
            return False
        
        cmf = row['CMF']
        if pd.isna(cmf) or cmf < base_filters.get('CMF_min', -0.02):
            return False
        
        return True
    except Exception as e:
        logger.warning(f"Sinyal kontrol hatası: {e}")
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
        if r['Final_Score'] < filters.get('Min_Final_Score', 0): return False
        return True
    except Exception as e:
        logger.warning(f"Filtre hatası: {e}")
        return False

# ===================== BAŞARI METRİĞİ =====================
def is_successful(signal_event):
    max_return = signal_event.get('+30G_Max_Getiri%')
    max_dd = signal_event.get('Max_DD_30G', 0)
    
    if max_return is None or max_dd is None or max_dd == 0:
        return None
    
    return 1 if max_return / max_dd > 2 else 0

# ===================== TARAMA =====================
def scan_stock_all_dates(sym, df_full, bdays, base_filters, profile, 
                         index_df, date_index_map, min_final_score):
    """Bir hisseyi tüm iş günleri için tara"""
    results = []
    
    try:
        if df_full is None or len(df_full) < MIN_HISTORY:
            return results
        
        df = calc_indicators_optimized(df_full, index_df, date_index_map)
        if df is None:
            return results
        
        df_dates = df['Date'].dt.normalize()
        
        for day in bdays:
            ref = pd.Timestamp(day).normalize()
            
            valid_idx = df_dates[df_dates <= ref].index
            if len(valid_idx) == 0:
                continue
            
            idx = valid_idx[-1]
            
            if idx < MIN_HISTORY:
                continue
            
            if pd.isna(df['RSI'].iloc[idx]) or pd.isna(df['ADX'].iloc[idx]):
                continue
            
            if not check_signal_fast(df, idx, base_filters):
                continue
            
            signal_price = df['Close'].iloc[idx]
            signal_date = df['Date'].iloc[idx]
            
            row = df.iloc[idx]
            score_data = {
                'ADX': row['ADX'],
                'RSI': row['RSI'],
                'VolRatio': row['VolRatio'],
                'CMF': row['CMF'],
                'Stochastic': row['Stochastic'],
                'BB_Position': row['BB_Position'],
                'MA200_Mesafe%': row['MA200_Mesafe%'],
                'RS_Score': row['RS_Score'],  # İndikatör aşamasında hesaplandı
                'ADX_Slope3': row['ADX_Slope3'],
                'CMF_Slope3': row['CMF_Slope3'],
                'RSI_Slope3': row['RSI_Slope3'],
                'VolRatio_Slope3': row['VolRatio_Slope3'],
                'Stochastic_Slope3': row['Stochastic_Slope3'],
                'MA5': row['MA5'],
                'MA10': row['MA10'],
                'MA20': row['MA20'],
                'MA50': row['MA50'],
                'MA200': row['MA200'],
                'Close': signal_price,
            }
            
            scores = score_stock_v25_optimize(score_data)
            
            if scores['Trend_Score'] < 0:
                continue
            if scores['Trend_Score'] == 15:
                if (row['ADX'] or 20) < 18 or (row['BB_Position'] or 0) > 0.65:
                    continue
            if scores['Final_Score'] < min_final_score:
                continue
            
            clean_symbol = sym.replace(".IS", "")
            signal_id = f"{clean_symbol}_{signal_date.strftime('%Y%m%d')}"
            
            signal_event = {
                'Signal_ID': signal_id,
                'Hisse': sym,
                'Signal_Date': signal_date.strftime('%Y-%m-%d'),
                'Entry_Price': round(signal_price, 2),
                'RSI': round(row['RSI'], 1) if pd.notna(row['RSI']) else None,
                'ADX': round(row['ADX'], 1) if pd.notna(row['ADX']) else None,
                'VolRatio': round(row['VolRatio'], 2) if pd.notna(row['VolRatio']) else None,
                'MFI': round(row['MFI'], 1) if pd.notna(row['MFI']) else None,
                'Stochastic': round(row['Stochastic'], 1) if pd.notna(row['Stochastic']) else None,
                'BB_Position': round(row['BB_Position'], 2) if pd.notna(row['BB_Position']) else None,
                'CMF': round(row['CMF'], 3) if pd.notna(row['CMF']) else None,
                'MA200_Mesafe%': round(row['MA200_Mesafe%'], 1) if pd.notna(row['MA200_Mesafe%']) else None,
                'MA5': round(row['MA5'], 2) if pd.notna(row['MA5']) else None,
                'MA10': round(row['MA10'], 2) if pd.notna(row['MA10']) else None,
                'MA20': round(row['MA20'], 2) if pd.notna(row['MA20']) else None,
                'MA50': round(row['MA50'], 2) if pd.notna(row['MA50']) else None,
                'MA200': round(row['MA200'], 2) if pd.notna(row['MA200']) else None,
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
            
            if profile and not apply_filter_fast(signal_event, profile):
                continue
            
            # İleri bar hesaplamaları (bar sayısı, takvim günü değil)
            total_len = len(df)
            if total_len > idx + 1:
                for s in STEPS:
                    if idx + s < total_len:
                        future_close = df['Close'].iloc[idx + s]
                        if pd.notna(future_close) and signal_price != 0:
                            signal_event[f'+{s}B_Getiri%'] = round(((future_close - signal_price) / signal_price) * 100, 2)
                        else:
                            signal_event[f'+{s}B_Getiri%'] = None
                    else:
                        signal_event[f'+{s}B_Getiri%'] = None
                
                for s in STEPS:
                    if idx + s < total_len:
                        max_price = df['High'].iloc[idx:idx+s+1].max()
                        if pd.notna(max_price) and signal_price != 0:
                            signal_event[f'+{s}B_Max_Getiri%'] = round(((max_price - signal_price) / signal_price) * 100, 2)
                        else:
                            signal_event[f'+{s}B_Max_Getiri%'] = None
                    else:
                        signal_event[f'+{s}B_Max_Getiri%'] = None
                
                max_dd = 0
                if idx + 30 < total_len:
                    low_valley = df['Low'].iloc[idx+1:idx+31].min()
                    if signal_price > 0:
                        max_dd = ((signal_price - low_valley) / signal_price) * 100
                signal_event['Max_DD_30B'] = round(max_dd, 1)
                
                if signal_event.get('+30B_Getiri%') is not None and max_dd > 0:
                    signal_event['Risk_Ratio_30B'] = round(signal_event['+30B_Getiri%'] / max_dd, 2)
                else:
                    signal_event['Risk_Ratio_30B'] = None
                
                for target_pct, key in [(1.10, 'Bars_To_%10'), (1.20, 'Bars_To_%20')]:
                    target_price = signal_price * target_pct
                    days = None
                    for i in range(idx + 1, min(idx + 90, total_len)):
                        if df['High'].iloc[i] >= target_price:
                            days = i - idx
                            break
                    signal_event[key] = days
                
                signal_event['Is_Successful'] = is_successful(signal_event)
            else:
                for s in STEPS:
                    signal_event[f'+{s}B_Getiri%'] = None
                    signal_event[f'+{s}B_Max_Getiri%'] = None
                signal_event['Max_DD_30B'] = None
                signal_event['Risk_Ratio_30B'] = None
                signal_event['Bars_To_%10'] = None
                signal_event['Bars_To_%20'] = None
                signal_event['Is_Successful'] = None
            
            results.append(signal_event)
    
    except Exception as e:
        logger.warning(f"Tarama hatası ({sym}): {e}")
    
    return results

def run_scan_optimized(symbols, bdays, base_filters, profile=None,
                       index_df=None, date_index_map=None, min_final_score=40):
    """Optimize tarama: hisse bazlı"""
    all_signals = []
    
    start_date = bdays[0] - timedelta(days=LOOKBACK*2)
    end_date = bdays[-1] + timedelta(days=FORWARD_DAYS)
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    today = datetime.now().strftime('%Y-%m-%d')
    if end_str > today:
        end_str = today
    
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {}
        for sym in symbols:
            future = ex.submit(
                process_single_stock, 
                sym, start_str, end_str, bdays, base_filters, 
                profile, index_df, date_index_map, min_final_score
            )
            futures[future] = sym
        
        for future in as_completed(futures):
            sym = futures[future]
            try:
                results = future.result()
                if results:
                    all_signals.extend(results)
            except Exception as e:
                logger.error(f"Thread hatası ({sym}): {e}")
    
    return all_signals

def process_single_stock(sym, start_str, end_str, bdays, base_filters, 
                         profile, index_df, date_index_map, min_final_score):
    """Tek hisse için veri çek ve tüm günleri tara"""
    try:
        df = get_data_range(sym, start_str, end_str)
        if df is None:
            return []
        
        return scan_stock_all_dates(sym, df, bdays, base_filters, profile,
                                    index_df, date_index_map, min_final_score)
    except Exception as e:
        logger.error(f"Hisse işleme hatası ({sym}): {e}")
        return []

# ===================== COOLDOWN (DÜZELTİLMİŞ) =====================
def apply_cooldown_filter(all_signals, signal_history, cooldown_days):
    """Sıralı cooldown filtresi"""
    # Önce tarihe göre sırala (cooldown için kritik)
    all_signals = sorted(all_signals, key=lambda x: (x['Signal_Date'], x['Hisse']))
    
    filtered_signals = []
    for signal in all_signals:
        hisse = signal['Hisse']
        signal_date = signal['Signal_Date']
        
        if hisse in signal_history:
            last_signal = signal_history[hisse].get('last_date')
            if last_signal is not None:
                try:
                    if isinstance(last_signal, str):
                        last_signal = pd.Timestamp(last_signal)
                    signal_dt = pd.Timestamp(signal_date)
                    
                    # İş günü farkını hesapla
                    bdiff = np.busday_count(
                        np.datetime64(last_signal.date()), 
                        np.datetime64(signal_dt.date())
                    )
                    
                    if bdiff <= cooldown_days:
                        continue  # Cooldown aktif, bu sinyali atla
                except Exception as e:
                    logger.warning(f"Cooldown hesaplama hatası: {e}")
        
        filtered_signals.append(signal)
        
        # Sinyali kaydet (Timestamp olarak)
        signal_history[hisse] = {
            'last_date': pd.Timestamp(signal_date),
            'last_score': signal['Final_Score']
        }
    
    return filtered_signals, signal_history

# ===================== YARDIMCI FONKSİYONLAR =====================
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
        "strategy_preset": "🎯 Veri Odaklı V2.5 (Optimize)",
        "df": None, "ok": False, "t": 0, "days": 0,
        "min_final_score": 40,
        "signal_history": defaultdict(dict)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    
    c1, c2, c3 = st.columns([7,1,1])
    with c1: st.markdown('<div class="header">⚡ BIST SİNYAL OLAYI BACKTEST MOTORU V2.5</div>', unsafe_allow_html=True)
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
        st.markdown("### 📊 V2.5 Optimizasyonlar")
        st.caption("""
        ✅ Hisse bazlı veri çekme
        ✅ İndikatörler tek seferde
        ✅ RS Score önceden hesaplanır
        ✅ Cooldown sıralı çalışır
        ✅ Bar bazlı isimlendirme (+30B)
        ✅ Hata loglaması aktif
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
        min_final_score = st.slider("Minimum Final Skor", 0, 100, st.session_state.min_final_score, 5)
        st.session_state.min_final_score = min_final_score
        
        st.markdown("---")
        st.markdown("### 🔄 SİNYAL COOLDOWN")
        use_cooldown = st.checkbox("Cooldown aktif", value=True)
        cooldown_days = st.slider("Cooldown işlem günü", 0, 30, SIGNAL_COOLDOWN, 1)
        
        st.markdown("---")
        
        lists = get_lists()
        secim = st.selectbox("📋 Liste", list(lists.keys()))
        symbols = lists[secim]
        st.caption(f"{len(symbols)} hisse")
        
        st.markdown("### 📅 Tarama Aralığı")
        tip = st.radio("Tip", ["Tek Tarih", "Tarih Aralığı", "Ay"], horizontal=True)
        
        yesterday = datetime.now().date() - timedelta(days=1)
        while yesterday.weekday() >= 5:
            yesterday -= timedelta(days=1)
        
        if tip == "Tek Tarih":
            d = turkish_date_picker("Tarih Seçin", yesterday, "tek")
            start = end = d
        elif tip == "Tarih Aralığı":
            c1, c2 = st.columns(2)
            with c1:
                start = turkish_date_picker("Başlangıç", yesterday - timedelta(days=30), "bas")
            with c2:
                end = turkish_date_picker("Bitiş", yesterday, "bit")
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
            st.warning(f"⚠️ Bitiş tarihi bugünden ileri! Bugüne ({today}) kadar taranacak.")
            end = today
            bdays = get_bdays(pd.to_datetime(start), pd.to_datetime(end))
            days = len(bdays)
        
        st.markdown("---")
        st.markdown(f"📊 **{days}** işlem günü | 📋 **{len(symbols)}** hisse")
        st.markdown(f"⏱️ ~**{len(symbols)*1.5/WORKERS:.0f}s** (optimize)")
        
        btn = st.button("⚡ TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        
        with st.spinner('📊 BIST100 verisi hazırlanıyor...'):
            index_df = None
            date_index_map = None
            try:
                start_idx = bdays[0] - timedelta(days=LOOKBACK*2)
                end_idx = bdays[-1] + timedelta(days=FORWARD_DAYS)
                index_data = get_data_range('XU100', start_idx.strftime('%Y-%m-%d'), 
                                           min(end_idx, datetime.now()).strftime('%Y-%m-%d'))
                if index_data is not None:
                    index_df = calc_indicators_optimized(index_data)
                    if index_df is not None:
                        date_index_map = {
                            pd.Timestamp(d).normalize(): i 
                            for i, d in enumerate(index_df['Date'])
                        }
            except Exception as e:
                logger.error(f"Endeks verisi hatası: {e}")
        
        with st.spinner(f'⚡ {days} gün taranıyor... (V2.5)'):
            all_signals = run_scan_optimized(
                symbols, bdays, current_filters, profile,
                index_df, date_index_map, min_final_score
            )
        
        # Cooldown filtresi (sıralı çalışır)
        if use_cooldown and all_signals:
            signal_history = st.session_state.signal_history
            all_signals, signal_history = apply_cooldown_filter(
                all_signals, signal_history, cooldown_days
            )
            st.session_state.signal_history = signal_history
        
        if all_signals:
            df = pd.DataFrame(all_signals)
            
            # Eksik sütunları doldur
            expected_columns = [
                '+5B_Getiri%', '+10B_Getiri%', '+15B_Getiri%', 
                '+30B_Getiri%', '+60B_Getiri%', '+90B_Getiri%',
                '+5B_Max_Getiri%', '+10B_Max_Getiri%', '+15B_Max_Getiri%',
                '+30B_Max_Getiri%', '+60B_Max_Getiri%', '+90B_Max_Getiri%',
                'Max_DD_30B', 'Risk_Ratio_30B',
                'Bars_To_%10', 'Bars_To_%20',
                'Is_Successful'
            ]
            for col in expected_columns:
                if col not in df.columns:
                    df[col] = None
            
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
        
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("Toplam Sinyal", len(df))
        with c2: st.metric("Ort. Final Skor", f"{df['Final_Score'].mean():.0f}")
        with c3: st.metric("📋 Benzersiz Hisse", f"{df['Hisse'].nunique()}")
        
        if 'Is_Successful' in df.columns:
            success_df = df[df['Is_Successful'].notna()]
            if len(success_df) > 0:
                success_rate = success_df['Is_Successful'].sum() / len(success_df) * 100
                with c4: st.metric("✅ Başarı Oranı", f"%{success_rate:.0f}")
            else:
                with c4: st.metric("✅ Başarı Oranı", "Veri Yok")
        
        if '+30B_Getiri%' in df.columns:
            r30 = df['+30B_Getiri%'].dropna()
            with c5:
                if len(r30) > 0:
                    st.metric("📈 30B Ort. Getiri", f"%{r30.mean():.1f}")
                else:
                    st.metric("📈 30B Ort. Getiri", "Veri Yok")
        
        # Grafikler
        st.markdown("### 📈 MA Trend Analizi")
        ma_cols = ['MA5', 'MA10', 'MA20', 'MA50', 'MA200']
        if all(col in df.columns for col in ma_cols):
            ma_data = df[ma_cols].mean().reset_index()
            ma_data.columns = ['MA', 'Ortalama']
            
            fig_ma = go.Figure()
            fig_ma.add_trace(go.Bar(
                x=ma_data['MA'], y=ma_data['Ortalama'],
                marker_color=['#3498db', '#2ecc71', '#f1c40f', '#e67e22', '#e74c3c'],
                text=ma_data['Ortalama'].round(2), textposition='outside'
            ))
            fig_ma.update_layout(title="Ortalama MA Değerleri", height=250)
            st.plotly_chart(fig_ma, use_container_width=True)
        
        # Sinyal listesi
        st.markdown("### 📋 Sinyal Olayları")
        display_cols = ['Signal_ID', 'Hisse', 'Signal_Date', 'Entry_Price', 'Final_Score',
                       'RSI', 'ADX', 'VolRatio', 'CMF', 'BB_Position',
                       '+30B_Getiri%', 'Max_DD_30B', 'Is_Successful']
        available_cols = [col for col in display_cols if col in df.columns]
        
        def style_score(val):
            if val >= 70: return 'background-color: #9b59b6; color: white'
            elif val >= 60: return 'background-color: #2ecc71; color: white'
            elif val >= 50: return 'background-color: #f1c40f'
            else: return 'background-color: #e74c3c; color: white'
        
        if 'Final_Score' in available_cols:
            styled_df = df[available_cols].style.map(style_score, subset=['Final_Score'])
        else:
            styled_df = df[available_cols].style
        
        st.dataframe(styled_df, use_container_width=True, height=400)
        
        # İndirme
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📊 CSV İndir", 
                             df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'),
                             "sinyal_olaylari_v25.csv", "text/csv")
        with c2:
            export_df = df.head(5000) if len(df) > 5000 else df
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w:
                export_df.to_excel(w, index=False)
            st.download_button("📑 Excel İndir", buf.getvalue(),
                             "sinyal_olaylari_v25.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    elif not btn:
        st.markdown("### ⚡ V2.5 - Optimize Mimari")
        st.markdown("""
        **V2.5 Düzeltmeler:**
        
        | Özellik | Değişiklik |
        |---------|-----------|
        | Cooldown | **Sıralı çalışır** (tarihe göre sıralanır) |
        | İsimlendirme | **+30B** (bar, gün değil) |
        | RS Score | **İndikatör aşamasında** hesaplanır |
        | Hata Yönetimi | **Loglama aktif**, sessiz hata yok |
        | Gereksiz Import | Temizlendi |
        | TEST_MODE | Kullanıcı: ADMIN, Şifre: Elma* |
        """)

if __name__ == "__main__":
    main()
