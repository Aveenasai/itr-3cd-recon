import streamlit as st
import json
import pandas as pd
import xml.etree.ElementTree as ET

# --- Page Config ---
st.set_page_config(page_title="ITR vS 3CD", layout="wide", page_icon="⚖️")

# --- Professional Styling ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .main-header { font-size: 32px; font-weight: bold; color: #1E3A8A; margin-bottom: 5px; }
    .sub-text { color: #666; margin-bottom: 20px; }
    .stTable { background-color: white; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

class DataEngine:
    @staticmethod
    def to_f(val):
        if val is None: return 0.0
        try:
            if isinstance(val, str): val = val.replace(',', '')
            return float(val)
        except (ValueError, TypeError): return 0.0

    @staticmethod
    def get_audit_vals(js, category):
        """Extracts values from 3CD (Works for both FORM3CA and FORM3CB)."""
        res = {"c20b": 0.0, "c21a": 0.0, "c22": 0.0, "c26": 0.0, "dep": 0.0}
        # Auto-detect Audit Form
        f = js.get("FORM3CA", {}).get("F3CA", {}) or js.get("FORM3CB", {}).get("F3CB", {})
        
        if not f: return res

        # Clause 20(b) - ESI/PF
        pf = f.get("Form3cdEmpPfSuperannInfo", {}).get("Form3cdSect20b", []) or f.get("Form3cdSect20b", [])
        res["c20b"] = sum(DataEngine.to_f(i.get("Amount")) for i in pf)

        # Clause 21(a) - Personal Expenses
        res["c21a"] = sum(DataEngine.to_f(i.get("Amount")) for i in f.get("Form3cdDebPLExpnditure", []) 
                         if "PERSONAL" in str(i.get("ParticularType")).upper())

        # Clause 22 - MSME Interest (Sec 23)
        res["c22"] = sum(DataEngine.to_f(i.get("Amount4")) for i in f.get("Form3cdInadm", []) 
                        if i.get("ParticularType") == "SEC23")

        # Clause 26 - MSME 43B(h)
        res["c26"] = sum(DataEngine.to_f(i.get("Amount")) for i in f.get("Form3cdUnpaidStrySec43b", []) 
                        if i.get("Section") == "43Bh")

        # Clause 32 - Depreciation
        res["dep"] = sum(DataEngine.to_f(b.get("DepAllowable")) for b in f.get("Form3cdDeprAllw", []))
        return res

    @staticmethod
    def get_itr_vals(js, category, is_xml=False):
        """Universal Extraction Logic for ITR-3, ITR-5, and ITR-6."""
        if is_xml:
            # Placeholder for XML logic if needed later
            return {"name": "XML Processing...", "c20b":0, "c21a":0, "c22":0, "c26":0, "dep":0}

        itr_root = js.get("ITR", {})
        # Detect Form Type
        itr = itr_root.get("ITR3") or itr_root.get("ITR5") or itr_root.get("ITR6")
        
        if not itr: 
            return {"name": "Unknown Format", "c20b":0, "c21a":0, "c22":0, "c26":0, "dep":0}

        # 1. Name Extraction (Handles Individual/HUF vs Corporate)
        gen1 = itr.get("PartA_GEN1", {})
        name = gen1.get("PersonalInfo", {}).get("AssesseeName", {}).get("SurNameOrOrgName") or \
               gen1.get("OrgFirmInfo", {}).get("AssesseeName", {}).get("SurNameOrOrgName", "Unknown")

        # 2. Schedule BP (Business Profession) - Different keys for ITR3 vs ITR5/6
        bp_root = itr.get("ITR3ScheduleBP") or itr.get("CorpScheduleBP") or itr.get("ScheduleBP", {})
        bp = bp_root.get("BusinessIncOthThanSpec", {})
        oi = itr.get("PARTA_OI", {})

        # 3. Personal Exp (Found in OI or BP disallowance section)
        p_exp = DataEngine.to_f(oi.get("AmtDisallUs37", {}).get("PersonalExp")) or \
                DataEngine.to_f(oi.get("AmtDisallUs37", {}).get("PersonalExpndtr")) or \
                DataEngine.to_f(bp.get("AmtDebPLDisallowUs37"))

        # 4. Depreciation Search (BP Summary vs Asset Schedules)
        itr_dep = DataEngine.to_f(bp.get("DepreciationAllowITAct32", {}).get("TotDeprAllowITAct"))
        if itr_dep == 0:
            dpm = itr.get("ScheduleDPM", {}).get("PlantMachinerySummary", {}) or itr.get("ScheduleDPM", {}).get("PlantMachSummary", {})
            doa = itr.get("ScheduleDOA", {}).get("OtherAssetsSummary", {}) or itr.get("ScheduleDOA", {}).get("OtherAssetsSumm", {})
            itr_dep = DataEngine.to_f(dpm.get("TotDepAllowitProp")) + DataEngine.to_f(doa.get("TotDepAllowitProp"))

        return {
            "name": name,
            "c20b": DataEngine.to_f(oi.get("AmtDisallUs36", {}).get("EmplyeeContrStatutoryFund")),
            "c21a": p_exp,
            "c22": DataEngine.to_f(oi.get("AmtDisall43B", {}).get("AmtUs43B", {}).get("MSEPayable")),
            "c26": DataEngine.to_f(oi.get("AmtDisallUs43BPyNowAll", {}).get("AmtUs43B", {}).get("MSEPayable")),
            "dep": itr_dep
        }

# --- UI Header ---
st.markdown('<div class="main-header">⚖️ ITR vS 3CD</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">Universal Tax Audit & Return Reconciliation Dashboard</div>', unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.markdown("### TYPE")
    category = st.radio("Entity Category", ["Corporate", "Non-Corporate"])
    itr_format = st.selectbox("File Format", ["JSON", "XML"])
    st.divider()
    st.caption("Version 2.2 | Multi-Form Support")

# --- Upload Section ---
c1, c2 = st.columns(2)
with c1:
    u_3cd = st.file_uploader("Upload 3CD (Audit JSON)", type=['json'])
with c2:
    u_itr = st.file_uploader(f"Upload ITR ({itr_format})", type=[itr_format.lower()])

if u_3cd and u_itr:
    try:
        # Load Files
        aud_js = json.load(u_3cd)
        itr_input = json.load(u_itr) if itr_format == "JSON" else u_itr.read()
        
        # Extract Data
        aud = DataEngine.get_audit_vals(aud_js, category)
        ret = DataEngine.get_itr_vals(itr_input, category, is_xml=(itr_format == "XML"))
        
        # Display Entity Header
        st.markdown(f"### 🏢 Assessee: **{ret['name']}**")
        
        # Reconciliation Logic
        comparison = [
            {"Clause": "20(b) ESI/PF (36(1)(va))", "Audit": aud["c20b"], "ITR": ret["c20b"]},
            {"Clause": "21(a) Personal Exp", "Audit": aud["c21a"], "ITR": ret["c21a"]},
            {"Clause": "22 MSME Interest (Sec 23)", "Audit": aud["c22"], "ITR": ret["c22"]},
            {"Clause": "26 MSME 43B(h)", "Audit": aud["c26"], "ITR": ret["c26"]},
            {"Clause": "32 Depr (IT Act)", "Audit": aud["dep"], "ITR": ret["dep"]}
        ]
        
        df = pd.DataFrame(comparison)
        df["Difference"] = df["Audit"] - df["ITR"]
        df["Status"] = df["Difference"].apply(lambda x: "✅ Match" if abs(x) < 5 else "❌ Mismatch")

        # Table Output
        st.table(df.style.format({
            "Audit": "{:,.2f}", 
            "ITR": "{:,.2f}", 
            "Difference": "{:,.2f}"
        }))
        
        # Download Button
        st.download_button("📥 Export CSV Report", df.to_csv(index=False), "ITR_3CD_Recon.csv", "text/csv")

    except Exception as e:
        st.error(f"Mapping Error: {e}")
        st.info("Ensure you have selected the correct format in the sidebar.")

