import borsapy as bp
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Elmalar 3.0", layout="wide")

st.title("📊 BIST 100 Finansal Analiz Dashboard")
st.write("ROE - PD/DD - F/K - Skor Sistemi")

def güvenli_float(x):
    try:
        return float(x)
    except:
        return None


def satir_bul_kesin(balance, adaylar):
    for aday in adaylar:
        for idx in balance.index:
            if str(idx).strip().lower() == aday.strip().lower():
                return idx
    return None


def yillik_kolon_bul(balance):
    for col in balance.columns:
        if "12" in str(col) or "2024" in str(col):
            return col
    return balance.columns[0]


xu100 = bp.Index("XU100")
hisseler = xu100.component_symbols

sonuclar = []

progress = st.progress(0)

for i, kod in enumerate(hisseler):

    try:
        ticker = bp.Ticker(kod)
        info = ticker.info

        fiyat = güvenli_float(info.get("currentPrice"))
        pd_dd = güvenli_float(info.get("priceToBook"))
        fk = güvenli_float(info.get("trailingPE"))

        roe = None

        try:
            balance = ticker.balance_sheet
            if balance is None:
                continue

            col = yillik_kolon_bul(balance)

            net_kar_satir = satir_bul_kesin(balance, [
                "Dönem Net Kar/Zararı",
                "Net Dönem Karı/Zararı"
            ])

            ozkaynak_satir = satir_bul_kesin(balance, [
                "Özkaynaklar"
            ])

            if net_kar_satir and ozkaynak_satir:
                net_kar = güvenli_float(balance.loc[net_kar_satir, col])
                ozkaynak = güvenli_float(balance.loc[ozkaynak_satir, col])

                if ozkaynak and ozkaynak != 0:
                    roe = net_kar / ozkaynak

        except:
            pass

        puan = 0

        if pd_dd and pd_dd < 1:
            puan += 50
        elif pd_dd and pd_dd < 1.5:
            puan += 30

        if fk and fk < 10:
            puan += 30

        if roe and roe > 0.15:
            puan += 20

        sonuclar.append({
            "Hisse": kod,
            "Fiyat": fiyat,
            "PD/DD": pd_dd,
            "F/K": fk,
            "ROE (%)": round(roe * 100, 2) if roe else None,
            "Puan": puan
        })

    except:
        pass

    progress.progress((i + 1) / len(hisseler))


df = pd.DataFrame(sonuclar)
df = df.sort_values("Puan", ascending=False)

st.subheader("🏆 En Güçlü Hisseler")
st.dataframe(df.head(20))

st.download_button(
    "📥 CSV indir",
    df.to_csv(index=False).encode("utf-8"),
    "bist_sonuclar.csv",
    "text/csv"
)
