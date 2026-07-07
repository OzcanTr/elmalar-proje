import streamlit as st
import pandas as pd
import numpy as np
import borsapy as bp
from datetime import datetime, timedelta
import warnings
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from io import BytesIO
import calendar

warnings.filterwarnings('ignore')

st.set_page_config(page_title="BIST Sinyal Tarama V3", page_icon="📈", layout="wide")

# ===================== TÜRKÇE TARİH SEÇİCİ =====================
TURKISH_MONTHS = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
TURKISH_DAYS = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"]

def turkish_date_picker(label, default_date=None, key="tcal", min_date=None, max_date=None):
    """Türkçe tarih seçici"""
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
    st.markdown("### 🔐 BIST Sinyal Tarama")
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
    .debug-box { background:#f0f0f0; padding:10px; border-radius:5px; font-family:monospace; 
                 font-size:12px; max-height:600px; overflow-y:auto; }
</style>""", unsafe_allow_html=True)

# ===================== SABİTLER =====================
LOOKBACK, STEPS, WORKERS = 150, [5,10,15,30,60,90], 10
STRATEGY = {'RSI_max':65, 'MA200_diff_min':-30, 'Stochastic_max':80, 'ADX_min':3, 'Volume_MA_ratio':0.3, 'MFI_max':70}
FILTERS = {'Min_Perf_Score':65, 'Max_RSI':60, 'Max_ADX':45, 'Min_Volume_MA':0.8, 'Max_MFI':65}

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

def get_data(symbol, date_str, debug_logs=None):
    """Veri çekme - ORİJİNAL MANTIK + numpy düzeltmesi"""
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
        
        # ORİJİNAL MANTIK: reset_index ve kolon eşleştirme
        df = df.reset_index()
        
        # Tarih kolonunu bul
        date_col = None
        for c in df.columns:
            col_name = str(c).lower()
            if 'date' in col_name or 'index' in col_name or 'tarih' in col_name:
                date_col = c
                break
        
        if date_col is None:
            # İlk kolonu tarih olarak dene
            date_col = df.columns[0]
        
        df = df.rename(columns={date_col: 'Date'})
        
        # Tarihi dönüştür - epoch time olabilir
        try:
            df['Date'] = pd.to_datetime(df['Date'])
        except:
            try:
                # Unix timestamp olabilir (saniye)
                df['Date'] = pd.to_datetime(df['Date'], unit='s')
            except:
                try:
                    # Unix timestamp (milisaniye)
                    df['Date'] = pd.to_datetime(df['Date'], unit='ms')
                except:
                    if debug_logs is not None:
                        debug_logs.append(f"⚠️ {sym}: Tarih dönüşümü başarısız, ilk değer: {df['Date'].iloc[0]}")
                    return None
        
        # Zaman dilimi varsa kaldır
        if hasattr(df['Date'].iloc[0], 'tz') and df['Date'].iloc[0].tz is not None:
            df['Date'] = df['Date'].dt.tz_localize(None)
        
        # OHLCV kolonlarını eşleştir
        col_map = {}
        for c in df.columns:
            cl = str(c).lower()
            if 'open' in cl: col_map[c] = 'Open'
            elif 'high' in cl: col_map[c] = 'High'
            elif 'low' in cl: col_map[c] = 'Low'
            elif 'close' in cl or 'kapanis' in cl: col_map[c] = 'Close'
            elif 'volume' in cl or 'hacim' in cl: col_map[c] = 'Volume'
        
        # Eğer isim eşleştirme çalışmadıysa, pozisyona göre eşleştir
        if 'Close' not in col_map.values():
            # Date'den sonraki kolonları sırayla OHLCV yap
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
            if debug_logs is not None:
                debug_logs.append(f"⚠️ {sym}: Eksik kolonlar - mevcut: {df.columns.tolist()}")
            return None
        
        if 'Volume' not in df.columns:
            df['Volume'] = 0
        
        # Sadece gerekli kolonları al
        result = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
        
        # Numpy hatasını önlemek için tüm sayısal kolonları float yap
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            result[col] = pd.to_numeric(result[col], errors='coerce').astype(float)
        
        result = result.sort_values('Date').reset_index(drop=True)
        
        # NaN içeren satırları temizle
        result = result.dropna(subset=['Open', 'High', 'Low', 'Close'])
        
        return result
    except Exception as e:
        if debug_logs is not None:
            debug_logs.append(f"💥 {symbol} get_data hata: {str(e)}")
        return None

def calc_indicators(df):
    """İndikatör hesaplama"""
    if df is None or len(df) < 200:
        return None
    
    # NaN'ları temizle
    df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
    
    # Yeni DataFrame - numpy hatası olmaması için
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
    
    return clean_df

def score_stock(r):
    s, rs, ad, vl, mf = 0, r['RSI'], r['ADX'], r['VolRatio'], r['MFI']
    if 30<=rs<=40: s+=30
    elif 40<rs<=50: s+=25
    elif 50<rs<=55: s+=20
    elif 55<rs<=60: s+=15
    elif 25<=rs<30: s+=15
    else: s+=5
    
    if ad<15: s+=30
    elif 15<=ad<20: s+=25
    elif 20<=ad<25: s+=20
    elif 25<=ad<30: s+=15
    else: s+=5
    
    if vl>2.5: s+=25
    elif vl>1.8: s+=22
    elif vl>1.2: s+=18
    elif vl>1.0: s+=12
    elif vl>0.8: s+=8
    else: s+=3
    
    if 40<=mf<=55: s+=15
    elif 35<=mf<=60: s+=12
    elif 30<=mf<=65: s+=8
    else: s+=3
    
    if vl>1.5 and ad>20: s+=5
    return min(s,100)

def check_signal(df, i):
    try:
        if pd.isna(df['RSI'].iloc[i]) or df['RSI'].iloc[i]>STRATEGY['RSI_max']: return False
        if pd.isna(df['MA200'].iloc[i]): return False
        if ((df['Close'].iloc[i]-df['MA200'].iloc[i])/df['MA200'].iloc[i])*100 < STRATEGY['MA200_diff_min']: return False
        if pd.isna(df['Stochastic'].iloc[i]) or df['Stochastic'].iloc[i]>STRATEGY['Stochastic_max']: return False
        if pd.isna(df['ADX'].iloc[i]) or df['ADX'].iloc[i]<STRATEGY['ADX_min']: return False
        if pd.isna(df['VolRatio'].iloc[i]) or df['VolRatio'].iloc[i]<STRATEGY['Volume_MA_ratio']: return False
        if pd.isna(df['MFI'].iloc[i]) or df['MFI'].iloc[i]>STRATEGY['MFI_max']: return False
        return True
    except:
        return False

def scan_stock_single(sym, date_str, debug_logs):
    """Tek hisse tarama"""
    try:
        df = get_data(sym, date_str, debug_logs)
        if df is None:
            return None
        
        df = calc_indicators(df)
        if df is None:
            debug_logs.append(f"❌ {sym}: İndikatör hesaplanamadı (yetersiz veri)")
            return None
        
        ref = pd.to_datetime(date_str).normalize()
        dates = df['Date'].dt.normalize()
        idx = next((i for i,d in enumerate(dates) if d>=ref), None)
        
        if idx is None:
            debug_logs.append(f"❌ {sym}: Tarih bulunamadı (istenen: {ref.date()}, veri aralığı: {dates.min().date()} - {dates.max().date()})")
            return None
        
        rsi_val = df['RSI'].iloc[idx]
        adx_val = df['ADX'].iloc[idx]
        vol_val = df['VolRatio'].iloc[idx]
        mfi_val = df['MFI'].iloc[idx]
        stoch_val = df['Stochastic'].iloc[idx]
        close_val = df['Close'].iloc[idx]
        
        if pd.isna(df['MA200'].iloc[idx]):
            debug_logs.append(f"❌ {sym}: MA200 NaN (yetersiz geçmiş veri)")
            return None
        
        ma200_val = df['MA200'].iloc[idx]
        ma200_diff = ((close_val - ma200_val) / ma200_val) * 100
        
        # Neden sinyal yok?
        reasons = []
        if pd.isna(rsi_val) or rsi_val > STRATEGY['RSI_max']:
            reasons.append(f"RSI={rsi_val:.1f} (max:{STRATEGY['RSI_max']})")
        if pd.isna(ma200_val):
            reasons.append("MA200 NaN")
        elif ma200_diff < STRATEGY['MA200_diff_min']:
            reasons.append(f"MA200diff={ma200_diff:.1f}% (min:{STRATEGY['MA200_diff_min']})")
        if pd.isna(stoch_val) or stoch_val > STRATEGY['Stochastic_max']:
            reasons.append(f"Stoch={stoch_val:.1f} (max:{STRATEGY['Stochastic_max']})")
        if pd.isna(adx_val) or adx_val < STRATEGY['ADX_min']:
            reasons.append(f"ADX={adx_val:.1f} (min:{STRATEGY['ADX_min']})")
        if pd.isna(vol_val) or vol_val < STRATEGY['Volume_MA_ratio']:
            reasons.append(f"Vol={vol_val:.2f} (min:{STRATEGY['Volume_MA_ratio']})")
        if pd.isna(mfi_val) or mfi_val > STRATEGY['MFI_max']:
            reasons.append(f"MFI={mfi_val:.1f} (max:{STRATEGY['MFI_max']})")
        
        if reasons:
            debug_logs.append(f"❌ {sym}: {' | '.join(reasons)}")
            return None
        
        # Sinyal var!
        cur = close_val
        r = {'Hisse':sym, 'Tarih':df.iloc[idx]['Date'].strftime('%Y-%m-%d'), 'Kapanis':round(cur,2),
             'RSI':round(rsi_val,1), 'ADX':round(adx_val,1),
             'VolRatio':round(vol_val,2), 'MFI':round(mfi_val,1)}
        r['Perf_Skor'] = score_stock(r)
        
        for s in STEPS:
            if idx+s < len(df):
                r[f'+{s}_RET'] = round(((df['Close'].iloc[idx+s]-cur)/cur)*100, 2)
        
        # Filtre kontrolü
        filter_reasons = []
        if r['RSI'] > FILTERS['Max_RSI']:
            filter_reasons.append(f"RSI filtresi ({r['RSI']:.1f}>{FILTERS['Max_RSI']})")
        if r['ADX'] > FILTERS['Max_ADX']:
            filter_reasons.append(f"ADX filtresi ({r['ADX']:.1f}>{FILTERS['Max_ADX']})")
        if r['VolRatio'] < FILTERS['Min_Volume_MA']:
            filter_reasons.append(f"Vol filtresi ({r['VolRatio']:.2f}<{FILTERS['Min_Volume_MA']})")
        if r['MFI'] > FILTERS['Max_MFI']:
            filter_reasons.append(f"MFI filtresi ({r['MFI']:.1f}>{FILTERS['Max_MFI']})")
        if r['Perf_Skor'] < FILTERS['Min_Perf_Score']:
            filter_reasons.append(f"Skor filtresi ({r['Perf_Skor']}<{FILTERS['Min_Perf_Score']})")
        
        if filter_reasons:
            debug_logs.append(f"⚠️ {sym}: FİLTRE - {' | '.join(filter_reasons)}")
            return None
        
        debug_logs.append(f"✅✅✅ {sym}: SİNYAL! Skor={r['Perf_Skor']} | RSI={rsi_val:.1f} ADX={adx_val:.1f} Vol={vol_val:.2f} MFI={mfi_val:.1f} MA200diff={ma200_diff:.1f}%")
        return r
    except Exception as e:
        debug_logs.append(f"💥 {sym} HATA: {str(e)}")
        return None

def run_scan_sequential(symbols, date, debug_logs):
    """Sıralı tarama"""
    results = []
    ds = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
    
    for sym in symbols:
        r = scan_stock_single(sym, ds, debug_logs)
        if r:
            results.append(r)
    
    return results

def get_bdays(start, end):
    days = []
    cur = start
    while cur <= end:
        if cur.weekday()<5: days.append(cur)
        cur += timedelta(days=1)
    return days

# ===================== ANA UYGULAMA =====================
def main():
    if not check_password():
        return
    
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = True
    if "debug_logs" not in st.session_state:
        st.session_state.debug_logs = []
    
    c1, c2 = st.columns([8,1])
    with c1: st.markdown('<div class="header">📈 BIST SİNYAL TARAMA V3</div>', unsafe_allow_html=True)
    with c2:
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🐛 Debug Aç/Kapat", use_container_width=True):
                st.session_state.debug_mode = not st.session_state.debug_mode
                if not st.session_state.debug_mode:
                    st.session_state.debug_logs = []
        with col_btn2:
            if st.button("🚪 ÇIKIŞ", use_container_width=True):
                st.session_state.clear()
                st.rerun()
    
    if st.session_state.debug_mode:
        st.warning("🐛 DEBUG MODU AKTİF")
    
    with st.sidebar:
        st.markdown("### ⚙️ AYARLAR")
        lists = get_lists()
        secim = st.selectbox("Liste", list(lists.keys()))
        symbols = lists[secim]
        st.caption(f"{len(symbols)} hisse")
        
        st.markdown("### 📅 Tarih")
        tip = st.radio("Tip", ["Tek Tarih","Aralık","Ay"], horizontal=True)
        
        if tip == "Tek Tarih":
            d = turkish_date_picker("Tarih Seçin", datetime(2025,7,7), "tek")
            start = end = d
        elif tip == "Aralık":
            start = turkish_date_picker("Başlangıç", datetime(2025,7,7), "bas")
            end = turkish_date_picker("Bitiş", datetime(2025,7,10), "bit")
        else:
            c1,c2 = st.columns(2)
            with c1: y = st.selectbox("Yıl", range(2020,2031), index=5, key="yy")
            with c2: m = st.selectbox("Ay", range(1,13), format_func=lambda x: TURKISH_MONTHS[x-1], index=6, key="mm")
            start = datetime(y,m,1).date()
            end = (datetime(y,m+1,1) if m<12 else datetime(y+1,1,1)).date() - timedelta(days=1)
        
        days = len(get_bdays(pd.to_datetime(start), pd.to_datetime(end)))
        st.caption(f"⏱️ ~{days*len(symbols)*0.2:.0f}s | {days} gün | {len(symbols)} hisse")
        btn = st.button("🔍 TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        st.session_state.debug_logs = []
        
        with st.spinner('🔍 Taranıyor...'):
            bdays = get_bdays(pd.to_datetime(start), pd.to_datetime(end))
            all_signals = []
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | {i+1}/{len(bdays)}")
                st.session_state.debug_logs.append(f"\n{'='*50}")
                st.session_state.debug_logs.append(f"📅 GÜN {i+1}: {day.strftime('%d.%m.%Y')}")
                st.session_state.debug_logs.append(f"{'='*50}")
                
                res = run_scan_sequential(symbols, day, st.session_state.debug_logs)
                if res: 
                    all_signals.extend(res)
                    st.session_state.debug_logs.append(f"✅ Bu gün {len(res)} sinyal bulundu!")
                else:
                    st.session_state.debug_logs.append(f"❌ Bu gün sinyal bulunamadı")
                
                bar.progress((i+1)/len(bdays))
            
            bar.empty(); txt.empty()
        
        if all_signals:
            st.session_state.df = pd.DataFrame(all_signals)
            st.session_state.ok = True
            st.session_state.t = time.time()-t0
        else:
            st.warning("⚠️ Sinyal bulunamadı!")
            st.session_state.ok = False
        
        if st.session_state.debug_mode and st.session_state.debug_logs:
            with st.expander("🐛 DETAYLI DEBUG LOGLARI", expanded=True):
                sinyal = sum(1 for log in st.session_state.debug_logs if "SİNYAL!" in log)
                veri_yok = sum(1 for log in st.session_state.debug_logs if "Veri çekilemedi" in log)
                sinyal_yok = sum(1 for log in st.session_state.debug_logs if "❌" in log and "Tarih" not in log)
                filtre = sum(1 for log in st.session_state.debug_logs if "FİLTRE" in log)
                hata = sum(1 for log in st.session_state.debug_logs if "HATA:" in log)
                
                st.markdown(f"""
                **📊 ÖZET:**
                - ✅ Sinyal: **{sinyal}**
                - ❌ Sinyal yok: {sinyal_yok}
                - ⚠️ Filtre: {filtre}
                - 💥 Hata: {hata}
                """)
                
                st.text_area("Detaylı Log", "\n".join(st.session_state.debug_logs), height=500)
    
    if st.session_state.get('ok'):
        df = st.session_state.df
        st.markdown(f"### 📊 {len(df)} Sinyal | ⚡ {st.session_state.t:.1f}s")
        
        r30 = df['+30_RET'].dropna()
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("Sinyal", len(df))
        with c2: st.metric("30G Ort.", f"%{r30.mean():.1f}" if len(r30)>0 else "N/A")
        with c3: st.metric("30G Kazanma", f"%{(r30>0).sum()/len(r30)*100:.0f}" if len(r30)>0 else "N/A")
        
        st.dataframe(df, use_container_width=True, height=400)
        
        c1,c2 = st.columns(2)
        with c1: st.download_button("📊 CSV", df.to_csv(index=False), "sinyaller.csv", "text/csv")
        with c2:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as w: df.to_excel(w, index=False)
            st.download_button("📑 EXCEL", buf.getvalue(), "sinyaller.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    elif not btn:
        st.markdown("### 🚀 Hoş Geldiniz!")
        st.info("💡 **Demo:** Kullanıcı: `ADMIN` | Şifre: `Elma*`")

if __name__ == "__main__":
    main()
