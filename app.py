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

st.set_page_config(page_title="BIST Sinyal Tarama V3", page_icon="📈", layout="wide")

# ===================== TÜRKÇE TARİH SEÇİCİ =====================
TURKISH_MONTHS = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran","Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]

def hybrid_date_selector(label, default_date=None, key_prefix=""):
    if default_date is None:
        default_date = datetime.now()
    
    st.markdown(f"**{label}**")
    
    manuel_str = st.text_input("📝 gg.aa.yyyy", value=default_date.strftime('%d.%m.%Y'), key=f"{key_prefix}_manuel", placeholder="15.07.2025")
    
    try:
        parts = manuel_str.replace('/', '.').split('.')
        manuel_date = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
    except:
        manuel_date = None
    
    with st.expander("📅 Takvim", expanded=(manuel_date is None)):
        c1, c2, c3 = st.columns(3)
        with c1:
            gun = st.selectbox("Gün", range(1,32), index=default_date.day-1, key=f"{key_prefix}_g")
        with c2:
            ay = st.selectbox("Ay", range(1,13), format_func=lambda x: TURKISH_MONTHS[x-1], index=default_date.month-1, key=f"{key_prefix}_a")
        with c3:
            yil = st.selectbox("Yıl", range(2020,2031), index=default_date.year-2020, key=f"{key_prefix}_y")
    
    secilen = manuel_date if manuel_date else datetime(yil, ay, min(gun, calendar.monthrange(yil, ay)[1])).date()
    st.caption(f"✅ **{secilen.strftime('%d %B %Y')}**")
    return secilen

# ===================== GİRİŞ =====================
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "login_counter" not in st.session_state:
        st.session_state.login_counter = 0
    
    if st.session_state.authenticated:
        return True
    
    st.markdown("""<style>
        .login-box { max-width:400px; margin:80px auto; padding:2rem; background:white; border-radius:20px; box-shadow:0 20px 60px rgba(0,0,0,0.15); text-align:center; }
        .login-box h2 { color:#1a1a2e; }
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
    return False

# ===================== SABİTLER =====================
LOOKBACK, STEPS, WORKERS = 150, [5,10,15,30,60,90], 10
STRATEGY = {'RSI_max':65, 'MA200_diff_min':-30, 'Stochastic_max':80, 'ADX_min':3, 'Volume_MA_ratio':0.3, 'Volume_trend_days':2, 'Price_volume_correlation':0.05, 'MFI_max':70}
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

@st.cache_data(ttl=1800)
def get_data(symbol, date_str):
    try:
        ref = pd.to_datetime(date_str)
        sym = symbol.upper().strip()
        if not sym.endswith(".IS"): sym += ".IS"
        df = bp.Ticker(sym).history(start=(ref-timedelta(days=LOOKBACK*2)).strftime('%Y-%m-%d'), end=(ref+timedelta(days=LOOKBACK)).strftime('%Y-%m-%d'))
        if df is None or len(df)==0: return None
        df = df.reset_index().rename(columns={'index':'Date'}) if 'Date' not in df.columns else df
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        return df[['Date','Open','High','Low','Close','Volume']].sort_values('Date')
    except:
        return None

def calc_indicators(df):
    for p in [5,10,20,50,100,200]:
        df[f'MA{p}'] = df['Close'].rolling(p).mean()
        df[f'VMA{p}'] = df['Volume'].rolling(p).mean()
    d = df['Close'].diff()
    g = d.where(d>0,0).rolling(14).mean()
    l = (-d.where(d<0,0)).rolling(14).mean()
    df['RSI'] = 100-(100/(1+g/l))
    e1 = df['Close'].ewm(span=12,adjust=False).mean()
    e2 = df['Close'].ewm(span=26,adjust=False).mean()
    df['MACD'] = e1-e2
    df['Stochastic'] = 100*(df['Close']-df['Low'].rolling(14).min())/(df['High'].rolling(14).max()-df['Low'].rolling(14).min())
    tr = np.maximum(df['High']-df['Low'], np.maximum(abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())))
    atr = tr.rolling(14).mean()
    dp = np.where((df['High']-df['High'].shift())>(df['Low'].shift()-df['Low']), np.maximum(df['High']-df['High'].shift(),0),0)
    dm = np.where((df['Low'].shift()-df['Low'])>(df['High']-df['High'].shift()), np.maximum(df['Low'].shift()-df['Low'],0),0)
    df['ADX'] = (100*(abs(dp.rolling(14).mean()-dm.rolling(14).mean())/(dp.rolling(14).mean()+dm.rolling(14).mean()))).rolling(14).mean()
    df['VolRatio'] = df['Volume']/df['VMA20']
    tp = (df['High']+df['Low']+df['Close'])/3
    mf = tp*df['Volume']
    pf = mf.where(tp>tp.shift(),0).rolling(14).sum()
    nf = mf.where(tp<tp.shift(),0).rolling(14).sum()
    df['MFI'] = 100-(100/(1+pf/nf))
    return df

def score_stock(r):
    s, rs, ad, vl, mf = 0, r['RSI'], r['ADX'], r['VolRatio'], r['MFI']
    if 30<=rs<=40: s+=30
    elif 40<rs<=50: s+=25
    elif 50<rs<=55: s+=20
    else: s+=10
    if ad<15: s+=30
    elif 15<=ad<20: s+=25
    elif 20<=ad<25: s+=20
    else: s+=10
    if vl>2.5: s+=25
    elif vl>1.8: s+=22
    elif vl>1.2: s+=18
    elif vl>1.0: s+=12
    else: s+=8
    if 40<=mf<=55: s+=15
    elif 35<=mf<=60: s+=12
    else: s+=8
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
    try:
        df = get_data(sym, date_str)
        if df is None: return None
        df = calc_indicators(df)
        ref = pd.to_datetime(date_str).normalize()
        dates = df['Date'].dt.normalize()
        idx = next((i for i,d in enumerate(dates) if d>=ref), None)
        if idx is None: return None
        if not check_signal(df, idx): return None
        
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
    results = []
    ds = date.strftime('%Y-%m-%d')
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(scan_stock, s, ds):s for s in symbols}
        for f in as_completed(futures):
            r = f.result()
            if r: results.append(r)
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
    
    st.markdown("""<style>
        .header { font-size:2rem; font-weight:700; text-align:center; padding:1rem;
                  background:linear-gradient(135deg,#667eea,#764ba2); color:white;
                  border-radius:15px; margin-bottom:1.5rem; }
    </style>""", unsafe_allow_html=True)
    
    c1, c2 = st.columns([8,1])
    with c1: st.markdown('<div class="header">📈 BIST SİNYAL TARAMA V3</div>', unsafe_allow_html=True)
    with c2:
        if st.button("🚪 ÇIKIŞ", use_container_width=True):
            st.session_state.clear()
            st.session_state.authenticated = False
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
            d = hybrid_date_selector("Tarih", datetime(2025,7,7), "t")
            start = end = d
        elif tip == "Aralık":
            start = hybrid_date_selector("Başlangıç", datetime(2025,7,7), "b")
            end = hybrid_date_selector("Bitiş", datetime(2025,7,10), "e")
        else:
            c1,c2 = st.columns(2)
            with c1: y = st.selectbox("Yıl", range(2020,2031), index=5, key="yy")
            with c2: m = st.selectbox("Ay", range(1,13), format_func=lambda x: TURKISH_MONTHS[x-1], index=6, key="mm")
            start = datetime(y,m,1).date()
            end = (datetime(y,m+1,1) if m<12 else datetime(y+1,1,1)).date() - timedelta(days=1)
        
        days = len(get_bdays(pd.to_datetime(start), pd.to_datetime(end)))
        st.caption(f"⏱️ ~{days*len(symbols)*0.1/WORKERS:.0f}s | {days} iş günü")
        btn = st.button("🔍 TARAMA BAŞLAT", use_container_width=True, type="primary")
    
    if btn:
        t0 = time.time()
        with st.spinner('🔍 Taranıyor...'):
            bdays = get_bdays(pd.to_datetime(start), pd.to_datetime(end))
            all_signals = []
            bar = st.progress(0)
            txt = st.empty()
            
            for i, day in enumerate(bdays):
                txt.text(f"📅 {day.strftime('%d.%m.%Y')} | ⚡ {time.time()-t0:.0f}s | {i+1}/{len(bdays)}")
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
            st.download_button("📑 EXCEL", buf.getvalue(), "sinyaller.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    elif not btn:
        st.markdown("### 🚀 Hoş Geldiniz!")
        st.info("💡 **Demo:** Kullanıcı: `ADMIN` | Şifre: `Elma*`")

if __name__ == "__main__":
    main()
