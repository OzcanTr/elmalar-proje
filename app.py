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

st.set_page_config(page_title="BIST Sinyal Tarama Pro - Gelişmiş", page_icon="📈", layout="wide")

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
    .score-high { background-color: #2ecc71; color: white; font-weight: bold; padding: 2px 8px; border-radius: 12px; }
    .score-mid { background-color: #f1c40f; padding: 2px 8px; border-radius: 12px; }
    .score-low { background-color: #e67e22; color: white; padding: 2px 8px; border-radius: 12px; }
    .score-bad { background-color: #e74c3c; color: white; padding: 2px 8px; border-radius: 12px; }
</style>""", unsafe_allow_html=True)

# ===================== SABİTLER =====================
LOOKBACK, STEPS, WORKERS = 200, [5,10,15,30,60,90], 10

STRATEGY_PRESETS = {
    "🎯 Üç Aşamalı Kademeli": {
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
        'tight_filters': {
            'Min_Perf_Score': 70,
            'Max_RSI': 52, 'Min_RSI': 38,
            'Max_ADX': 38, 'Min_ADX': 15,
            'Min_Volume_MA': 0.6, 'Max_Volume_MA': 1.4,
            'Max_MFI': 61, 'Min_MFI': 45,
            'Max_Stochastic': 58, 'Min_Stochastic': 5,
            'Max_BB_Position': 0.55, 'Min_BB_Position': 0.07,
        },
        'desc': '🎯 1.Aşama: Geniş | 2A:Temel süzgeç | 2B:Destek süzgeç | 3:5 aylık kazanan'
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
    """Veri çekme - HER ZAMAN ileri veriyi de dener, yoksa boş döner"""
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

# ===================== GELİŞMİŞ GÖSTERGE HESAPLAMALARI =====================
def calculate_slope(series, period=3):
    """Belirli periyottaki eğimi hesaplar"""
    if len(series) < period:
        return 0
    try:
        x = np.arange(period)
        y = series[-period:].values
        slope = np.polyfit(x, y, 1)[0]
        return slope
    except:
        return 0

def add_slope_indicators(df):
    """Tüm göstergelere slope değerleri ekler"""
    indicators = ['RSI', 'ADX', 'MFI', 'Stochastic', 'VolRatio', 'BB_Position']
    
    for ind in indicators:
        if ind in df.columns:
            try:
                df[f'{ind}_Slope3'] = df[ind].rolling(5).apply(
                    lambda x: calculate_slope(x, 3) if len(x) >= 3 else 0, raw=True
                )
                df[f'{ind}_Slope5'] = df[ind].rolling(7).apply(
                    lambda x: calculate_slope(x, 5) if len(x) >= 5 else 0, raw=True
                )
            except:
                df[f'{ind}_Slope3'] = 0
                df[f'{ind}_Slope5'] = 0
    
    return df

def calculate_obv(df):
    """On Balance Volume hesaplar"""
    try:
        obv = [0]
        for i in range(1, len(df)):
            if df['Close'].iloc[i] > df['Close'].iloc[i-1]:
                obv.append(obv[-1] + df['Volume'].iloc[i])
            elif df['Close'].iloc[i] < df['Close'].iloc[i-1]:
                obv.append(obv[-1] - df['Volume'].iloc[i])
            else:
                obv.append(obv[-1])
        df['OBV'] = obv
    except:
        df['OBV'] = 0
    return df

def calculate_cmf(df, period=20):
    """Chaikin Money Flow hesaplar"""
    try:
        high_low = df['High'] - df['Low']
        high_low = high_low.replace(0, np.nan)
        mf_multiplier = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / high_low
        mf_volume = mf_multiplier * df['Volume']
        df['CMF'] = mf_volume.rolling(period).sum() / df['Volume'].rolling(period).sum()
        df['CMF'] = df['CMF'].fillna(0)
    except:
        df['CMF'] = 0
    return df

def calculate_atr(df, period=14):
    """ATR hesaplar"""
    try:
        high_low = df['High'] - df['Low']
        high_close = abs(df['High'] - df['Close'].shift())
        low_close = abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(period).mean()
        df['ATR'] = df['ATR'].fillna(0)
    except:
        df['ATR'] = 0
    return df

def slope_score(row, indicator='RSI'):
    """Slope değerine göre puan verir"""
    slope_col = f'{indicator}_Slope3'
    if slope_col not in row.index or pd.isna(row[slope_col]):
        return 0
    
    slope = row[slope_col]
    if slope > 1.2:
        return 8
    elif slope > 0.5:
        return 5
    elif slope > 0:
        return 2
    elif slope > -0.5:
        return -2
    else:
        return -8

def calc_indicators(df):
    """Temel göstergeleri hesaplar - GELİŞMİŞ VERSİYON"""
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
    
    # Hareketli ortalamalar
    for p in [5,10,20,50,100,200]:
        clean_df[f'MA{p}'] = clean_df['Close'].rolling(p).mean()
        clean_df[f'VMA{p}'] = clean_df['Volume'].rolling(p).mean()
    
    # RSI
    d = clean_df['Close'].diff()
    g = d.where(d>0,0).rolling(14).mean()
    l = (-d.where(d<0,0)).rolling(14).mean()
    clean_df['RSI'] = 100-(100/(1+g/l))
    clean_df['RSI'] = clean_df['RSI'].fillna(50)
    
    # Stochastic
    high_14 = clean_df['High'].rolling(14).max()
    low_14 = clean_df['Low'].rolling(14).min()
    clean_df['Stochastic'] = 100*(clean_df['Close']-low_14)/(high_14-low_14)
    clean_df['Stochastic'] = clean_df['Stochastic'].fillna(50)
    
    # ADX
    tr = np.maximum(clean_df['High']-clean_df['Low'], 
                    np.maximum(abs(clean_df['High']-clean_df['Close'].shift()), 
                              abs(clean_df['Low']-clean_df['Close'].shift())))
    atr = pd.Series(tr).rolling(14).mean()
    dp = np.where((clean_df['High']-clean_df['High'].shift())>(clean_df['Low'].shift()-clean_df['Low']), 
                  np.maximum(clean_df['High']-clean_df['High'].shift(),0),0)
    dm = np.where((clean_df['Low'].shift()-clean_df['Low'])>(clean_df['High']-clean_df['High'].shift()), 
                  np.maximum(clean_df['Low'].shift()-clean_df['Low'],0),0)
    
    di_plus = 100*(pd.Series(dp).rolling(14).mean()/atr)
    di_minus = 100*(pd.Series(dm).rolling(14).mean()/atr)
    clean_df['ADX'] = (100*(abs(di_plus-di_minus)/(di_plus+di_minus))).rolling(14).mean()
    clean_df['ADX'] = clean_df['ADX'].fillna(20)
    
    # VolRatio
    clean_df['VolRatio'] = clean_df['Volume']/clean_df['VMA20']
    clean_df['VolRatio'] = clean_df['VolRatio'].fillna(1)
    
    # MFI
    tp = (clean_df['High']+clean_df['Low']+clean_df['Close'])/3
    mf = tp*clean_df['Volume']
    pf = mf.where(tp>tp.shift(),0).rolling(14).sum()
    nf = mf.where(tp<tp.shift(),0).rolling(14).sum()
    clean_df['MFI'] = 100-(100/(1+pf/nf))
    clean_df['MFI'] = clean_df['MFI'].fillna(50)
    
    # Bollinger Bands
    clean_df['BB_Mid'] = clean_df['Close'].rolling(20).mean()
    clean_df['BB_Std'] = clean_df['Close'].rolling(20).std()
    clean_df['BB_Upper'] = clean_df['BB_Mid'] + 2 * clean_df['BB_Std']
    clean_df['BB_Lower'] = clean_df['BB_Mid'] - 2 * clean_df['BB_Std']
    clean_df['BB_Position'] = (clean_df['Close'] - clean_df['BB_Lower']) / (clean_df['BB_Upper'] - clean_df['BB_Lower'])
    clean_df['BB_Position'] = clean_df['BB_Position'].fillna(0.5)
    
    # GELİŞMİŞ GÖSTERGELER
    clean_df = add_slope_indicators(clean_df)
    clean_df = calculate_obv(clean_df)
    clean_df = calculate_cmf(clean_df)
    clean_df = calculate_atr(clean_df)
    
    return clean_df

# ===================== SKORLAMA FONKSİYONLARI =====================
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

def money_flow_score(row):
    """OBV ve CMF trendlerine göre puan verir"""
    score = 0
    
    # OBV Trend
    if 'OBV' in row.index and not pd.isna(row.get('OBV', 0)):
        try:
            if 'OBV_Slope3' in row.index:
                obv_slope = row.get('OBV_Slope3', 0)
                if obv_slope > 100000:
                    score += 10
                elif obv_slope > 50000:
                    score += 5
                elif obv_slope > 10000:
                    score += 2
        except:
            pass
    
    # CMF Değeri
    if 'CMF' in row.index and not pd.isna(row.get('CMF', 0)):
        cmf = row.get('CMF', 0)
        if cmf > 0.1:
            score += 8
        elif cmf > 0:
            score += 4
        elif cmf < -0.1:
            score -= 5
    
    return max(0, min(score, 15))

def consolidation_breakout_score(df, idx):
    """Sıkışma ve hacim artışına göre puan verir"""
    if idx < 20:
        return 0
    
    score = 0
    
    try:
        # ATR daralması
        atr_recent = df['ATR'].iloc[max(0, idx-9):idx+1].mean()
        atr_previous = df['ATR'].iloc[max(0, idx-19):max(0, idx-9)].mean()
        
        if atr_previous > 0 and atr_recent < atr_previous * 0.7:
            score += 10
        elif atr_previous > 0 and atr_recent < atr_previous * 0.85:
            score += 5
    except:
        pass
    
    try:
        # Hacim artışı
        vol_recent = df['Volume'].iloc[max(0, idx-4):idx+1].mean()
        vol_previous = df['Volume'].iloc[max(0, idx-9):max(0, idx-4)].mean()
        
        if vol_previous > 0 and vol_recent > vol_previous * 1.5:
            score += 8
        elif vol_previous > 0 and vol_recent > vol_previous * 1.2:
            score += 4
    except:
        pass
    
    try:
        # Fiyat sıkışması
        high_20 = df['High'].iloc[max(0, idx-19):idx+1].max()
        low_20 = df['Low'].iloc[max(0, idx-19):idx+1].min()
        
        if low_20 > 0:
            range_pct = (high_20 - low_20) / low_20 * 100
            if range_pct < 8:
                score += 5
    except:
        pass
    
    return min(score, 20)

def calculate_enhanced_scores(df, idx, symbol=None, index_df=None):
    """Tüm puanları hesaplar ve final skoru üretir"""
    row = df.iloc[idx]
    
    # 1. PerfScore (mevcut sistem)
    base_score = score_stock({
        'RSI': row.get('RSI', 50),
        'ADX': row.get('ADX', 20),
        'VolRatio': row.get('VolRatio', 1),
        'MFI': row.get('MFI', 50),
        'Stochastic': row.get('Stochastic', 50),
        'BB_Position': row.get('BB_Position', 0.5)
    })
    
    # 2. Momentum Score (slope'lar)
    momentum_score = 0
    for ind in ['RSI', 'ADX', 'MFI', 'Stochastic', 'VolRatio', 'BB_Position']:
        m_score = slope_score(row, ind)
        momentum_score += max(0, m_score)  # Negatif puanları sıfırla
    
    momentum_score = min(momentum_score, 30)
    
    # 3. Money Flow Score
    money_score = money_flow_score(row)
    
    # 4. Trend Score
    trend_score = consolidation_breakout_score(df, idx)
    
    # 5. Relative Strength Score (opsiyonel)
    rs_score = 0
    if index_df is not None and idx >= 20:
        try:
            current_price = df['Close'].iloc[idx]
            index_current = index_df['Close'].iloc[idx]
            
            for period in [5, 10, 20]:
                if idx >= period:
                    stock_prev = df['Close'].iloc[idx - period]
                    index_prev = index_df['Close'].iloc[idx - period]
                    
                    if stock_prev > 0 and index_prev > 0:
                        stock_return = ((current_price - stock_prev) / stock_prev) * 100
                        index_return = ((index_current - index_prev) / index_prev) * 100
                        rs = stock_return - index_return
                        
                        if rs > 3:
                            rs_score += 8
                        elif rs > 1:
                            rs_score += 4
                        elif rs > 0:
                            rs_score += 1
        except:
            pass
    
    rs_score = min(rs_score, 20)
    
    # Final Score
    final_score = (
        0.30 * base_score +
        0.25 * momentum_score +
        0.20 * rs_score +
        0.15 * trend_score +
        0.10 * money_score
    )
    
    return {
        'Base_Score': round(base_score, 1),
        'Momentum_Score': round(momentum_score, 1),
        'RS_Score': round(rs_score, 1),
        'Trend_Score': round(trend_score, 1),
        'Money_Score': round(money_score, 1),
        'Final_Score': round(min(final_score, 100), 1)
    }

def check_signal(df, i, strategy, filters):
    """Mevcut sinyal kontrolü"""
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
    if filters is None:
        return True
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

# ===================== GELİŞMİŞ TARAMA FONKSİYONU =====================
def scan_stock_enhanced(sym, date_str, strategy, filters, mid_filters=None, 
                         support_filters=None, tight_filters=None, index_df=None):
    """Gelişmiş tarama fonksiyonu - 5 katmanlı skorlama ile"""
    try:
        df = get_data(sym, date_str)
        if df is None: return None
        
        df = calc_indicators(df)
        if df is None: return None
        
        ref = pd.to_datetime(date_str).normalize()
        dates = df['Date'].dt.normalize()
        idx = next((i for i,d in enumerate(dates) if d>=ref), None)
        if idx is None: return None
        
        # Mevcut filtreleri uygula
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
        
        # Filtreleri uygula
        if mid_filters and not apply_filter(r, mid_filters): return None
        if support_filters and not apply_filter(r, support_filters): return None
        if tight_filters and not apply_filter(r, tight_filters): return None
        if not apply_filter(r, filters): return None
        
        # GELİŞMİŞ SKORLAMA
        enhanced = calculate_enhanced_scores(df, idx, sym, index_df)
        
        r.update({
            'Base_Score': enhanced['Base_Score'],
            'Momentum_Score': enhanced['Momentum_Score'],
            'RS_Score': enhanced['RS_Score'],
            'Trend_Score': enhanced['Trend_Score'],
            'Money_Score': enhanced['Money_Score'],
            'Final_Score': enhanced['Final_Score']
        })
        
        # Final Score filtresi
        if enhanced['Final_Score'] < 45:
            return None
        
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
    except Exception as e:
        return None

def run_scan_enhanced(symbols, date, strategy, filters, mid_filters=None, 
                       support_filters=None, tight_filters=None, index_df=None):
    """Gelişmiş tarama çalıştırıcı"""
    results = []
    ds = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scan_stock_enhanced, s, ds, strategy, filters, 
                            mid_filters, support_filters, tight_filters, index_df):s for s in symbols}
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
        "strategy_preset": "🎯 Üç Aşamalı Kademeli",
        "df": None, "ok": False, "t": 0, "days": 0
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    
    c1, c2, c3 = st.columns([7,1,1])
    with c1: st.markdown('<div class="header">📈 BIST SİNYAL TARAMA PRO - GELİŞMİŞ 5 KATMAN</div>', unsafe_allow_html=True)
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
        filters = STRATEGY_PRESETS[preset].get('filters', {})
        mid_filters = STRATEGY_PRESETS[preset].get('mid_filters', None)
        support_filters = STRATEGY_PRESETS[preset].get('support_filters', None)
        tight_filters = STRATEGY_PRESETS[preset].get('tight_filters', None)
        
        st.caption(STRATEGY_PRESETS[preset]['desc'])
        
        st.markdown("---")
        st.markdown("### 🎯 GELİŞMİŞ PUANLAMA AĞIRLIKLARI")
        st.caption("Final skor için ağırlıklar")
        
        col1, col2 = st.columns(2)
        with col1:
            w_base = st.slider("Temel", 0.0, 1.0, 0.30, 0.05, key="w_base")
            w_momentum = st.slider("Momentum", 0.0, 1.0, 0.25, 0.05, key="w_mom")
            w_rs = st.slider("RS", 0.0, 1.0, 0.20, 0.05, key="w_rs")
        with col2:
            w_trend = st.slider("Trend", 0.0, 1.0, 0.15, 0.05, key="w_trend")
            w_money = st.slider("Para Girişi", 0.0, 1.0, 0.10, 0.05, key="w_money")
        
        # Ağırlıkları normalize et
        total_w = w_base + w_momentum + w_rs + w_trend + w_money
        if total_w > 0:
            weights = {
                'base': w_base/total_w,
                'momentum': w_momentum/total_w,
                'rs': w_rs/total_w,
                'trend': w_trend/total_w,
                'money': w_money/total_w
            }
        
        min_final_score = st.slider(
            "Minimum Final Skor",
            min_value=0, max_value=100, value=50, step=5,
            help="Bu skorun altındaki hisseler elenir"
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
        st.markdown(f"⏱️ ~**{days*len(symbols)*0.1/WORKERS:.0f}s**")
        
        btn = st.button("🔍 TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        
        # BIST100 verisini çek
        with st.spinner('📊 BIST100 verisi hazırlanıyor...'):
            index_df = None
            try:
                index_data = get_data('XU100', start.strftime('%Y-%m-%d'))
                if index_data is not None:
                    index_df = calc_indicators(index_data)
            except:
                pass
        
        with st.spinner(f'🔍 {days} gün taranıyor... (Gelişmiş 5 Katman)'):
            all_signals = []
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | {i+1}/{days}")
                res = run_scan_enhanced(symbols, day, strategy, filters, mid_filters, 
                                       support_filters, tight_filters, index_df)
                if res:
                    all_signals.extend(res)
                bar.progress((i+1)/days)
            
            bar.empty()
            txt.empty()
        
        if all_signals:
            df = pd.DataFrame(all_signals)
            df = df.sort_values('Final_Score', ascending=False)
            
            # Final Score filtreleme
            df = df[df['Final_Score'] >= min_final_score]
            
            st.session_state.df = df
            st.session_state.ok = True
            st.session_state.t = time.time() - t0
            st.session_state.days = days
        else:
            st.warning("⚠️ Sinyal bulunamadı!")
            st.session_state.ok = False
    
    if st.session_state.get('ok') and st.session_state.df is not None:
        df = st.session_state.df
        
        st.markdown(f"### 📊 {len(df)} Sinyal | ⚡ {st.session_state.t:.1f}s | 📅 {st.session_state.days} gün")
        
        # Metrikler
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("Toplam Sinyal", len(df))
        with c2: st.metric("Ort. Final Skor", f"{df['Final_Score'].mean():.0f}")
        
        # 30 günlük getiri varsa
        r30 = df.get('+30G_Getiri%', pd.Series(dtype=float)).dropna()
        with c3:
            if len(r30) > 0:
                st.metric("30G Ort. Getiri", f"%{r30.mean():.1f}")
            else:
                st.metric("30G Ort. Getiri", "Veri Yok")
        with c4:
            if len(r30) > 0:
                st.metric("30G Kazanma", f"%{(r30>0).sum()/len(r30)*100:.0f}")
            else:
                st.metric("30G Kazanma", "Veri Yok")
        with c5:
            high_score = len(df[df['Final_Score'] >= 70])
            st.metric("⭐ Yüksek Skor (≥70)", f"{high_score}")
        
        # Skor dağılımı
        st.markdown("### 📊 Skor Dağılımı")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Final Score histogram
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=df['Final_Score'], 
                nbinsx=20, 
                marker_color='#667eea',
                name='Final Score'
            ))
            fig.add_vline(x=df['Final_Score'].mean(), line_dash="dash", line_color="green", 
                         annotation_text=f"Ort: {df['Final_Score'].mean():.1f}")
            fig.add_vline(x=60, line_dash="dash", line_color="orange", 
                         annotation_text="Eşik: 60")
            fig.update_layout(
                title="Final Score Dağılımı",
                xaxis_title="Skor",
                yaxis_title="Sinyal Sayısı",
                height=300,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Skor kategorileri
            categories = {
                'Güçlü (≥75)': len(df[df['Final_Score'] >= 75]),
                'İyi (60-74)': len(df[(df['Final_Score'] >= 60) & (df['Final_Score'] < 75)]),
                'Orta (45-59)': len(df[(df['Final_Score'] >= 45) & (df['Final_Score'] < 60)]),
            }
            fig2 = go.Figure(data=[go.Pie(labels=list(categories.keys()), values=list(categories.values()))])
            fig2.update_layout(height=300, title="Skor Kategorileri")
            st.plotly_chart(fig2, use_container_width=True)
        
        # Tablo gösterimi
        st.markdown("### 📋 Sinyal Listesi")
        
        # Görselleştirme için sütunları seç
        display_cols = ['Hisse', 'Kapanis', 'Final_Score', 'Base_Score', 'Momentum_Score', 
                       'RS_Score', 'Trend_Score', 'Money_Score', 'RSI', 'ADX', 'VolRatio']
        
        # Var olan kolonları kontrol et
        available_cols = [col for col in display_cols if col in df.columns]
        
        # Renklendirme fonksiyonu
        def style_final_score(val):
            if val >= 75:
                return 'background-color: #2ecc71; color: white; font-weight: bold'
            elif val >= 60:
                return 'background-color: #f1c40f'
            elif val >= 45:
                return 'background-color: #e67e22; color: white'
            else:
                return 'background-color: #e74c3c; color: white'
        
        # Styler uygula
        styled_df = df[available_cols].style.applymap(style_final_score, subset=['Final_Score'])
        st.dataframe(styled_df, use_container_width=True, height=400)
        
        # En iyi 5 hisse
        st.markdown("### 🏆 En Güçlü 5 Sinyal")
        top5 = df.head(5)
        
        cols = st.columns(min(5, len(top5)))
        for i, (idx, row) in enumerate(top5.iterrows()):
            with cols[i]:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #667eea, #764ba2); 
                            padding: 15px; border-radius: 10px; color: white; text-align: center;">
                    <h3>{row['Hisse']}</h3>
                    <p style="font-size: 24px; font-weight: bold;">{row['Final_Score']:.0f}</p>
                    <p style="font-size: 12px;">Puan</p>
                    <hr style="margin: 5px 0;">
                    <p style="font-size: 12px;">📊 {row.get('RSI', 'N/A')} | 📈 {row.get('ADX', 'N/A')}</p>
                    <p style="font-size: 12px;">💰 {row.get('Kapanis', 'N/A')} TL</p>
                </div>
                """, unsafe_allow_html=True)
        
        # Detaylı skor dağılımı
        st.markdown("### 📈 Skor Bileşenleri")
        score_cols = ['Base_Score', 'Momentum_Score', 'RS_Score', 'Trend_Score', 'Money_Score']
        available_score_cols = [col for col in score_cols if col in df.columns]
        
        if available_score_cols:
            score_data = df[available_score_cols].mean().reset_index()
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
        
        # İndirme butonları
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "📊 CSV İndir",
                df.to_csv(index=False).encode('utf-8'),
                "sinyaller_gelismis.csv",
                "text/csv"
            )
        with c2:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w:
                df.to_excel(w, index=False)
            st.download_button(
                "📑 Excel İndir",
                buf.getvalue(),
                "sinyaller_gelismis.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    elif not btn:
        st.markdown("### 🚀 Hoş Geldiniz!")
        st.markdown("""
        **Bu sistem 5 katmanlı gelişmiş skorlama kullanır:**

        1. **Temel Skor** - Mevcut gösterge değerleri
        2. **Momentum Skoru** - Gösterge eğimleri (ivme)
        3. **Relative Strength** - BIST100'e göre performans
        4. **Trend Skoru** - ATR daralması + hacim artışı
        5. **Para Girişi Skoru** - OBV + CMF

        **Final Score** ile hisseler sıralanır ve pozitif ayrışma potansiyeli yüksek olanlar belirlenir.
        """)

if __name__ == "__main__":
    main()
