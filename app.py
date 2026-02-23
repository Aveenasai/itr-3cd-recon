import streamlit as st
import json
import pandas as pd
import xml.etree.ElementTree as ET
import io

# --- Page Config ---
st.set_page_config(page_title="Universal ITR vs 3CD Recon", layout="wide", page_icon="⚖️")

class DataEngine:
    @staticmethod
    def to_f(val):
        if val is None: return 0.0
        try:
            if isinstance(val, (int, float)): return float(val)
            val = str(val).replace(',', '').strip()
            return round(float(val), 2)
        except (ValueError, TypeError): return 0.0

    @staticmethod
    def get_xml_text(element, tag_name):
        """Finds XML tag text ignoring namespaces."""
        for el in element.iter():
            if el.tag.split('}')[-1] == tag_name:
                return el.text
        return None

    @staticmethod
    def parse_3cd(content, is_xml):
        """Extracts all relevant disallowances from 3CD (Audit)."""
        res = {"c20b": 0.0, "c21a": 0.0, "c21d": 0.0, "c21i": 0.0, "c22": 0.0, "c32": 0.0, "c43bh": 0.0}
        
        try:
            if is_xml:
                root = ET.fromstring(content)
                pf_entries = root.findall(".//{*}Form3cdEmpPfSuperann") + root.findall(".//{*}Form3cdSect20b")
                for item in pf_entries:
                    due = DataEngine.get_xml_text(item, "DueDate")
                    act = DataEngine.get_xml_text(item, "ActualDate")
                    amt = DataEngine.to_f(DataEngine.get_xml_text(item, "Amount"))
                    if act and due and act > due: res["c20b"] += amt

                res["c21a"] = sum(DataEngine.to_f(DataEngine.get_xml_text(i, "Amount")) for i in root.findall(".//{*}Form3cdDebPLExpnditure") 
                                 if "PERSONAL" in str(DataEngine.get_xml_text(i, "ParticularType")).upper())
                
                for item in root.findall(".//{*}Form3cdUnpaidStrySec43b"):
                    if DataEngine.get_xml_text(item, "Section") == "43Bh":
                        res["c43bh"] += DataEngine.to_f(DataEngine.get_xml_text(item, "Amount"))

                res["c21d"] = DataEngine.to_f(DataEngine.get_xml_text(root, "AmountDisallowance40A3"))
                res["c21i"] = DataEngine.to_f(DataEngine.get_xml_text(root, "AmountDisallowance40ai"))
                res["c22"] = DataEngine.to_f(DataEngine.get_xml_text(root, "SubClauseeofClause22"))
                res["c32"] = sum(DataEngine.to_f(DataEngine.get_xml_text(i, "DepAllowable")) for i in root.findall(".//{*}Form3cdDeprAllw"))
            else:
                js = json.loads(content)
                f = js.get("FORM3CA", {}).get("F3CA", {}) or js.get("FORM3CB", {}).get("F3CB", {})
                if f:
                    pf = f.get("Form3cdEmpPfSuperannInfo", {}).get("Form3cdSect20b", []) or f.get("Form3cdSect20b", [])
                    for i in pf:
                        if i.get("ActualDate", "") > i.get("DueDate", ""):
                            res["c20b"] += DataEngine.to_f(i.get("Amount"))
                    res["c21a"] = sum(DataEngine.to_f(i.get("Amount")) for i in f.get("Form3cdDebPLExpnditure", []) if "PERSONAL" in str(i.get("ParticularType")).upper())
                    res["c43bh"] = sum(DataEngine.to_f(i.get("Amount")) for i in f.get("Form3cdUnpaidStrySec43b", []) if i.get("Section") == "43Bh")
                    res["c21d"] = DataEngine.to_f(f.get("AmountDisallowance40A3"))
                    res["c21i"] = DataEngine.to_f(f.get("AmountDisallowance40ai"))
                    res["c22"] = sum(DataEngine.to_f(i.get("Amount4")) for i in f.get("Form3cdInadm", []) if i.get("ParticularType") == "SEC23")
                    res["c32"] = sum(DataEngine.to_f(b.get("DepAllowable")) for b in f.get("Form3cdDeprAllw", []))
        except Exception as e:
            st.sidebar.error(f"Error parsing 3CD: {e}")
            
        return res

    @staticmethod
    def parse_itr(content, is_xml):
        """Universal Extraction for ITR-3, 5, 6 (Return)."""
        res = {"name": "Assessee", "c20b": 0.0, "c21a": 0.0, "c21d": 0.0, "c21i": 0.0, "c22": 0.0, "c32": 0.0, "c43bh": 0.0}
        
        try:
            if is_xml:
                root = ET.fromstring(content)
                res["name"] = DataEngine.get_xml_text(root, "SurNameOrOrgName") or "Unknown"
                res["c20b"] = DataEngine.to_f(DataEngine.get_xml_text(root, "EmplyeeContrStatutoryFund"))
                res["c21a"] = DataEngine.to_f(DataEngine.get_xml_text(root, "PersonalExp")) or DataEngine.to_f(DataEngine.get_xml_text(root, "PersonalExpndtr"))
                res["c21d"] = DataEngine.to_f(DataEngine.get_xml_text(root, "AmtDisallowance40A3"))
                res["c21i"] = DataEngine.to_f(DataEngine.get_xml_text(root, "AmtDisallowance40ai"))
                res["c22"] = DataEngine.to_f(DataEngine.get_xml_text(root, "MSMEDisallowance"))
                res["c32"] = DataEngine.to_f(DataEngine.get_xml_text(root, "TotDeprAllowITAct"))
                res["c43bh"] = DataEngine.to_f(DataEngine.get_xml_text(root, "MSEPayable"))
            else:
                js = json.loads(content)
                itr = js.get("ITR", {}).get("ITR3") or js.get("ITR", {}).get("ITR5") or js.get("ITR", {}).get("ITR6")
                if itr:
                    gen1 = itr.get("PartA_GEN1", {})
                    res["name"] = gen1.get("PersonalInfo", {}).get("AssesseeName", {}).get("SurNameOrOrgName") or \
                                 gen1.get("OrgFirmInfo", {}).get("AssesseeName", {}).get("SurNameOrOrgName", "Assessee")
                    
                    oi = itr.get("PARTA_OI", {})
                    bp = (itr.get("ITR3ScheduleBP") or itr.get("CorpScheduleBP") or itr.get("ScheduleBP", {})).get("BusinessIncOthThanSpec", {})
                    
                    res["c20b"] = DataEngine.to_f(oi.get("AmtDisallUs36", {}).get("EmplyeeContrStatutoryFund"))
                    res["c21a"] = DataEngine.to_f(oi.get("AmtDisallUs37", {}).get("PersonalExpndtr")) or DataEngine.to_f(bp.get("AmtDebPLDisallowUs37"))
                    res["c21d"] = DataEngine.to_f(oi.get("AmtDisallUs40A", {}).get("AmtDisallUs40A3"))
                    res["c21i"] = DataEngine.to_f(oi.get("AmtDisallUs40", {}).get("AmtDisallUs40ai"))
                    res["c22"] = DataEngine.to_f(oi.get("AmtDisall43B", {}).get("AmtUs43B", {}).get("MSEPayable"))
                    res["c32"] = DataEngine.to_f(bp.get("DepreciationAllowITAct32", {}).get("TotDeprAllowITAct"))
                    res["c43bh"] = DataEngine.to_f(oi.get("AmtDisallUs43BPyNowAll", {}).get("AmtUs43B", {}).get("MSEPayable")) or \
                                   DataEngine.to_f(oi.get("AmtDisallUs43B", {}).get("AmtUs43B", {}).get("MSEPayable"))
        except Exception as e:
            st.sidebar.error(f"Error parsing ITR: {e}")
            
        return res

# --- UI Logic ---
st.title("⚖️ Comprehensive Tax Recon: 3CD vs ITR")
st.markdown("Handles **XML & JSON** for Corporate, Firms, and Individuals.")

with st.sidebar:
    st.header("1. Settings")
    fmt_3cd = st.selectbox("3CD Format", ["JSON", "XML"])
    fmt_itr = st.selectbox("ITR Format", ["JSON", "XML"])

# File Uploaders
c1, c2 = st.columns(2)
with c1: u_3cd = st.file_uploader(f"Upload 3CD ({fmt_3cd})", type=[fmt_3cd.lower()])
with c2: u_itr = st.file_uploader(f"Upload ITR ({fmt_itr})", type=[fmt_itr.lower()])

# Processing
if u_3cd and u_itr:
    aud = DataEngine.parse_3cd(u_3cd.read(), is_xml=(fmt_3cd == "XML"))
    ret = DataEngine.parse_itr(u_itr.read(), is_xml=(fmt_itr == "XML"))
    
    st.subheader(f"🏢 Assessee: {ret['name']}")
    
    recon_data = [
        ["20(b)", "ESI/PF (Late Payments)", aud["c20b"], ret["c20b"]],
        ["21(a)", "Personal Expenses", aud["c21a"], ret["c21a"]],
        ["21(d)", "Cash Payments (40A3)", aud["c21d"], ret["c21d"]],
        ["21(i)", "TDS Defaults (40ai)", aud["c21i"], ret["c21i"]],
        ["22", "MSME Interest (Sec 23)", aud["c22"], ret["c22"]],
        ["43B(h)", "MSME Unpaid (Sec 43Bh)", aud["c43bh"], ret["c43bh"]],
        ["32", "Depreciation (IT Act)", aud["c32"], ret["c32"]]
    ]
    
    df = pd.DataFrame(recon_data, columns=["Clause", "Parameter", "Audit (3CD)", "Return (ITR)"])
    df["Diff"] = df["Audit (3CD)"] - df["Return (ITR)"]
    df["Status"] = df["Diff"].apply(lambda x: "✅ Match" if abs(x) < 5 else "❌ Mismatch")
    
    st.table(df.style.format({"Audit (3CD)": "{:,.2f}", "Return (ITR)": "{:,.2f}", "Diff": "{:,.2f}"}))
else:
    st.info("Please upload both files to generate the reconciliation table.")
