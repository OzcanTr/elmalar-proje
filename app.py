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
    """Türkçe tarih seçici - Streamlit native date_input ile"""
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

def get_data(symbol, date_str):
    """Veri çekme"""
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
        
        # Tarih kolonunu bul
        date_col = None
        for c in df.columns:
            col_name = str(c).lower()
            if 'date' in col_name or 'index' in col_name or 'tarih' in col_name:
                date_col = c
                break
        
        if date_col is None:
            date_col = df.columns[0]
        
        df = df.rename(columns={date_col: 'Date'})
        
        # Tarihi dönüştür
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
        
        # OHLCV kolonlarını eşleştir
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
    """İndikatör hesaplama"""
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

def scan_stock(sym, date_str):
    """Hisse tarama"""
    try:
        df = get_data(sym, date_str)
        if df is None: return None
        
        df = calc_indicators(df)
        if df is None: return None
        
        ref = pd.to_datetime(date_str).normalize()
        dates = df['Date'].dt.normalize()
        idx = next((i for i,d in enumerate(dates) if d>=ref), None)
        if idx is None or not check_signal(df, idx): return None
        
        cur = df['Close'].iloc[idx]
        r = {'Hisse':sym, 'Tarih':df.iloc[idx]['Date'].strftime('%Y-%m-%d'), 'Kapanis':round(cur,2),
             'RSI':round(df['RSI'].iloc[idx],1), 'ADX':round(df['ADX'].iloc[idx],1),
             'VolRatio':round(df['VolRatio'].iloc[idx],2), 'MFI':round(df['MFI'].iloc[idx],1)}
        r['Perf_Skor'] = score_stock(r)
        
        for s in STEPS:
            if idx+s < len(df):
                r[f'+{s}_RET'] = round(((df['Close'].iloc[idx+s]-cur)/cur)*100, 2)
        
        if r['RSI']>FILTERS['Max_RSI'] or r['ADX']>FILTERS['Max_ADX']: return None
        if r['VolRatio']<FILTERS['Min_Volume_MA'] or r['MFI']>FILTERS['Max_MFI']: return None
        if r['Perf_Skor']<FILTERS['Min_Perf_Score']: return None
        return r
    except:
        return None

def run_scan(symbols, date):
    """Paralel tarama"""
    results = []
    ds = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scan_stock, s, ds):s for s in symbols}
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
        if cur.weekday()<5: days.append(cur)
        cur += timedelta(days=1)
    return days

# ===================== ANA UYGULAMA =====================
def main():
    if not check_password():
        return
    
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = False
    
    c1, c2, c3 = st.columns([7,1,1])
    with c1: st.markdown('<div class="header">📈 BIST SİNYAL TARAMA V3</div>', unsafe_allow_html=True)
    with c2:
        if st.button("🐛 Debug", use_container_width=True, help="Detaylı tarama loglarını göster"):
            st.session_state.debug_mode = not st.session_state.debug_mode
    with c3:
        if st.button("🚪 ÇIKIŞ", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
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
        st.caption(f"⏱️ ~{days*len(symbols)*0.1/WORKERS:.0f}s | {days} işlem günü")
        btn = st.button("🔍 TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        debug_logs = [] if st.session_state.debug_mode else None
        
        with st.spinner('🔍 Taranıyor...'):
            bdays = get_bdays(pd.to_datetime(start), pd.to_datetime(end))
            all_signals = []
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | {i+1}/{len(bdays)}")
                
                if st.session_state.debug_mode:
                    # Debug modunda tek tek tara
                    from concurrent.futures import ThreadPoolExecutor
                    ds = day.strftime('%Y-%m-%d')
                    debug_logs.append(f"\n--- Gün {i+1}: {ds} ---")
                    
                    for sym in symbols:
                        r = scan_stock(sym, ds)
                        if r:
                            all_signals.append(r)
                            debug_logs.append(f"✅ {sym}: Sinyal! RSI={r['RSI']} ADX={r['ADX']} Vol={r['VolRatio']} MFI={r['MFI']} Skor={r['Perf_Skor']}")
                else:
                    # Normal modda paralel tara
                    res = run_scan(symbols, day)
                    if res: all_signals.extend(res)
                
                bar.progress((i+1)/len(bdays))
            
            bar.empty(); txt.empty()
        
        if all_signals:
            st.session_state.df = pd.DataFrame(all_signals)
            st.session_state.ok = True
            st.session_state.t = time.time()-t0
        else:
            st.warning("⚠️ Sinyal bulunamadı!")
            st.session_state.ok = False
        
        if st.session_state.debug_mode and debug_logs:
            with st.expander("🐛 Debug Logları", expanded=False):
                st.text_area("Log", "\n".join(debug_logs), height=300)
    
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
