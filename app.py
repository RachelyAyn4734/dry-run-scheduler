"""
Dry Run Scheduling App — thin UI layer.
All business logic lives in services/, repositories/, utils/.
"""
import logging
import sys
import os

import streamlit as st
from supabase import create_client, Client
from datetime import date, datetime, timedelta
import pytz
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="תיאום Dry Run",
    page_icon="📅",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Timezone ──────────────────────────────────────────────────────────────────
IL_TZ = pytz.timezone("Asia/Jerusalem")

def now_il() -> datetime:
    return datetime.now(IL_TZ)

# ── Supabase ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = get_supabase()

# ── Local layer imports ───────────────────────────────────────────────────────
from utils.dates import to_heb, to_heb_short, slot_range_label
from utils.validation import valid_email, normalize_email, safe
from repositories.slots_repository import (
    fetch_slots, fetch_booked_slots, fetch_user_slot,
    add_slot, delete_slot_record,
)
from repositories.users_repository import (
    get_user, create_user, get_all_users, delete_user_record,
)
from services import booking_service

# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_mode() -> str:
    return st.query_params.get("mode", "user")

def _do_cancel(slot_id: int, gcal_event_id: str = "") -> None:
    booking_service.cancel(supabase, st.secrets, slot_id, gcal_event_id or "")


# ── CSS ───────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"], .stMarkdown, p, div, span, label {
        font-family: 'Inter', 'Segoe UI', sans-serif !important; font-size: 17px;
    }
    h1 { font-size: 30px !important; font-weight: 800 !important; }
    h2 { font-size: 24px !important; font-weight: 700 !important; }
    h3 { font-size: 21px !important; font-weight: 700 !important; }
    .stApp { background: #f0f2f6; }
    .hero {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 60%, #a21caf 100%);
        color: white; border-radius: 22px; padding: 30px 34px; margin-bottom: 26px;
        box-shadow: 0 10px 40px rgba(79,70,229,0.35);
    }
    .hero h1 { font-size:30px!important; font-weight:800!important; margin:0 0 6px; color:white!important; }
    .hero p   { font-size:17px!important; margin:0; opacity:.88; color:white!important; }
    .date-card {
        background: white; border-radius: 18px; padding: 22px 26px 10px;
        margin-bottom: 18px; box-shadow: 0 3px 14px rgba(0,0,0,0.08);
        border: 1.5px solid #e5e7eb;
    }
    .date-card .gc { font-size:20px; font-weight:700; color:#111827; }
    .date-card .hc { font-size:18px; color:#6b21a8; font-weight:600; direction:rtl; text-align:right; margin-top:2px; }
    .my-slot {
        background: linear-gradient(135deg,#059669,#10b981); color:white;
        border-radius:20px; padding:22px 28px; margin-bottom:22px;
        box-shadow:0 6px 24px rgba(5,150,105,0.30);
    }
    .my-slot h2 { font-size:22px!important; font-weight:800!important; margin:0 0 8px; color:white!important; }
    .my-slot .row { font-size:17px; margin:4px 0; color:white; }
    .my-slot .heb { font-size:18px; direction:rtl; color:#d1fae5; }
    .stButton > button {
        border-radius:16px!important; font-weight:700!important; font-size:17px!important;
        min-height:3.4rem!important; width:100%!important;
        border:2px solid #d1d5db!important; background:white!important; color:#1f2937!important;
        transition:all .15s ease!important; box-shadow:0 2px 6px rgba(0,0,0,0.06)!important;
    }
    .stButton > button:hover {
        border-color:#7c3aed!important; color:#7c3aed!important;
        box-shadow:0 6px 18px rgba(124,58,237,0.18)!important; transform:translateY(-1px)!important;
    }
    [data-testid="baseButton-primary"] {
        background:linear-gradient(135deg,#4f46e5,#7c3aed)!important;
        color:white!important; border:none!important;
        box-shadow:0 6px 18px rgba(79,70,229,0.40)!important;
    }
    [data-testid="baseButton-primary"]:hover {
        transform:translateY(-1px)!important; box-shadow:0 8px 24px rgba(79,70,229,0.50)!important;
    }
    .badge { display:inline-block; border-radius:20px; padding:5px 16px; font-size:14px; font-weight:700; }
    .b-avail  { background:#ede9fe; color:#4f46e5; }
    .b-booked { background:#d1fae5; color:#065f46; }
    .b-none   { background:#f3f4f6; color:#6b7280; }
    .sec-title { font-size:20px!important; font-weight:800!important; color:#111827!important; margin:0 0 14px!important; }
    .avatar {
        width:42px; height:42px; border-radius:50%;
        background:linear-gradient(135deg,#4f46e5,#7c3aed);
        color:white; font-size:17px; font-weight:800;
        display:inline-flex; align-items:center; justify-content:center;
    }
    .bov-card {
        background:white; border-radius:16px; padding:16px 20px; margin-bottom:10px;
        border-left:5px solid #7c3aed; box-shadow:0 2px 8px rgba(0,0,0,0.06);
    }
    .bov-card .slot-info { font-size:18px; font-weight:700; color:#111827; }
    .bov-card .user-info { font-size:15px; color:#6b7280; margin-top:4px; }
    .bov-card .heb-info  { font-size:16px; color:#6b21a8; direction:rtl; margin-top:2px; }
    .stTabs [data-baseweb="tab"] { font-size:16px!important; font-weight:700!important; padding:12px 22px!important; }
    .footer { text-align:center; color:#9ca3af; font-size:14px; margin-top:36px; }
    #MainMenu, footer, header { visibility:hidden; }
    </style>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# USER VIEW
# ═══════════════════════════════════════════════════════════════
def user_view():
    st.markdown("""
    <div class="hero">
        <h1>📅 תיאום Dry Run</h1>
        <p>בחרי מועד שנוח לך 👇</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Login ──────────────────────────────────────────────────
    if not st.session_state.get("user_profile"):
        with st.container(border=True):
            st.markdown('<p class="sec-title">🔑 הכניסי את האימייל שלך</p>', unsafe_allow_html=True)
            email_input = st.text_input("אימייל", placeholder="your@email.com",
                                        label_visibility="collapsed")
            if st.button("המשך ←", type="primary", use_container_width=True):
                if not valid_email(email_input):
                    st.error("נא להכניס כתובת אימייל תקינה.")
                else:
                    user = get_user(supabase, normalize_email(email_input))
                    if not user:
                        st.error("❌ האימייל הזה אינו רשום. פני למנהל/ת.")
                    else:
                        st.session_state.user_profile = user
                        st.rerun()
        return

    user = st.session_state.user_profile
    st.markdown(f"👋 **שלום, {safe(user['name'])}!**")

    # ── Post-booking success banner ────────────────────────────
    if st.session_state.pop("show_booking_success", False):
        st.balloons()
        if st.session_state.pop("gcal_booked", False):
            st.toast("📅 האירוע נוסף ליומן Google!")
        if st.session_state.pop("mail_sent", False):
            st.toast("✉️ מייל אישור נשלח אליך!")
        st.success("✅ הפגישה נקבעה בהצלחה!")
        st.divider()

    my_slot = fetch_user_slot(supabase, user["email"])

    # ── Existing booking ───────────────────────────────────────
    if my_slot:
        gd = date.fromisoformat(my_slot["date"])
        sr = slot_range_label(my_slot["time_slot"])
        st.markdown(f"""
        <div class="my-slot">
            <h2>✅ הפגישה שלך</h2>
            <div class="row">📅 {safe(gd.strftime('%A, %d %B %Y'))}</div>
            <div class="heb">{safe(to_heb(gd))}</div>
            <div class="row">🕐 {safe(sr)}</div>
        </div>
        """, unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("רוצה לשנות? ניתן לבטל ולבחור מועד אחר.")
            if st.button("🗑️ ביטול הפגישה", use_container_width=True):
                st.session_state.confirm_cancel = True
        if st.session_state.get("confirm_cancel"):
            with st.container(border=True):
                st.warning(f"לבטל את **{safe(gd.strftime('%d/%m/%Y'))} @ {safe(sr)}**?")
                c1, c2 = st.columns(2)
                if c1.button("כן, בטלי", type="primary", use_container_width=True):
                    _do_cancel(my_slot["id"], my_slot.get("gcal_event_id") or "")
                    st.session_state.confirm_cancel = False
                    st.rerun()
                if c2.button("השאירי", use_container_width=True):
                    st.session_state.confirm_cancel = False
                    st.rerun()

    # ── Slot selection / confirmation ──────────────────────────
    else:
        # Confirmation panel shown FIRST (hides slot list)
        if st.session_state.get("pending_slot"):
            ps = st.session_state.pending_slot
            gd_p = date.fromisoformat(ps["date"])
            with st.container(border=True):
                st.subheader("✅ אישור הזמנה")
                st.markdown(f"""
                - 📅 **{safe(gd_p.strftime('%A, %d %B %Y'))}**
                - <span dir="rtl">{safe(ps['heb'])}</span>
                - 🕐 **{safe(ps['time_range'])}**
                - ⏳ **שעת התחלה:** {safe(ps['time'][:5])} | **שעת סיום:** {safe(ps['time_range'].split(' - ')[1])}
                - 👤 **{safe(user['name'])}**
                """, unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                if c1.button("✅ אישור", type="primary", use_container_width=True):
                    result = booking_service.book(
                        supabase, st.secrets,
                        slot_id=ps["id"],
                        user_email=user["email"],
                        user_name=user["name"],
                        slot_date=date.fromisoformat(ps["date"]),
                        start_time=ps["time"],
                    )
                    if not result["success"]:
                        st.warning("⚠️ מצטערים, המועד הזה כבר נתפס. אנא בחרי מועד אחר.")
                        st.session_state.pending_slot = None
                        st.rerun()
                    else:
                        st.session_state.show_booking_success = True
                        st.session_state.gcal_booked = result["gcal_ok"]
                        st.session_state.mail_sent   = result["mail_ok"]
                        st.session_state.pending_slot = None
                        st.rerun()
                if c2.button("❌ חזור לבחירת שעה", use_container_width=True):
                    st.session_state.pending_slot = None
                    st.rerun()

        # Available slots (hidden while confirmation is open)
        else:
            slots = fetch_slots(supabase, only_available=True)
            if not slots:
                st.info("🕐 אין מועדים פנויים כרגע.")
            else:
                st.markdown('<p class="sec-title">🗓️ מועדים פנויים</p>', unsafe_allow_html=True)
                df = pd.DataFrame(slots)
                for slot_date_str, group in df.groupby("date"):
                    gd = date.fromisoformat(slot_date_str)
                    st.markdown(f"""
                    <div class="date-card">
                        <div class="gc">📅 {safe(gd.strftime('%A, %d %B %Y'))}</div>
                        <div class="hc">{safe(to_heb(gd))}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    rows = list(group.iterrows())
                    cols = st.columns(min(len(rows), 4))
                    for idx, (_, row) in enumerate(rows):
                        sr = slot_range_label(row["time_slot"])
                        if cols[idx % 4].button(f"🕐 {sr}", key=f"s_{row['id']}"):
                            st.session_state.pending_slot = {
                                "id": row["id"], "date": slot_date_str,
                                "time": row["time_slot"], "time_range": sr, "heb": to_heb(gd),
                            }
                            st.rerun()

    if st.button("🚪 יציאה", use_container_width=True):
        st.session_state.user_profile = None
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# ADMIN VIEW
# ═══════════════════════════════════════════════════════════════
def admin_view():
    st.markdown("""
    <div class="hero">
        <h1>🔧 Admin Dashboard</h1>
        <p>ניהול מועדים ומשתמשים</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Auth (no hardcoded fallback) ───────────────────────────
    if not st.session_state.get("admin_auth"):
        admin_pwd = st.secrets.get("ADMIN_PASSWORD", "")
        if not admin_pwd:
            st.error("🔴 ADMIN_PASSWORD לא מוגדר ב-Secrets. לא ניתן להתחבר.")
            return
        with st.container(border=True):
            st.markdown('<p class="sec-title">🔐 כניסת מנהל</p>', unsafe_allow_html=True)
            pwd = st.text_input("סיסמה", type="password", label_visibility="collapsed",
                                placeholder="הכנס סיסמה")
            if st.button("כניסה", type="primary", use_container_width=True):
                if pwd == admin_pwd:
                    st.session_state.admin_auth = True
                    st.rerun()
                else:
                    st.error("סיסמה שגויה.")
        return

    tab1, tab2, tab3 = st.tabs(["📅 מועדים", "👁️ סקירת הזמנות", "👥 משתמשים"])

    # ── TAB 1: Slots ───────────────────────────────────────────
    with tab1:
        with st.container(border=True):
            st.markdown('<p class="sec-title">➕ הוספת מועד</p>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            today_il    = now_il().date()
            tomorrow_il = today_il + timedelta(days=1)
            sel_date = c1.date_input("תאריך", value=tomorrow_il, min_value=tomorrow_il,
                                     format="DD/MM/YYYY")
            all_hour_opts = [f"{h:02d}:00" for h in range(7, 22)]
            taken = {s["time_slot"][:5] for s in fetch_slots(supabase, filter_date=sel_date)} if sel_date else set()
            available_opts = [t for t in all_hour_opts if t not in taken]
            time_slot = None
            if not available_opts:
                c2.warning("כל השעות לתאריך זה כבר תפוסות.")
            else:
                time_slot = c2.selectbox("שעה (משך: שעה)", available_opts,
                                         format_func=slot_range_label)
            if sel_date and time_slot:
                st.markdown(
                    f'<p style="color:#6b21a8;font-size:17px;direction:rtl;">'
                    f'📜 {safe(to_heb(sel_date))}</p>',
                    unsafe_allow_html=True)
                st.caption(f"משך המועד: {slot_range_label(time_slot)}")
            if st.button("💾 שמור מועד", type="primary", use_container_width=True):
                if not time_slot:
                    st.warning("אין שעות פנויות לתאריך זה.")
                elif add_slot(supabase, sel_date, time_slot):
                    st.success("✅ מועד נוסף!")
                    st.rerun()
                else:
                    st.warning("המועד הזה כבר קיים.")

        with st.container(border=True):
            st.markdown('<p class="sec-title">📋 כל המועדים</p>', unsafe_allow_html=True)
            filter_d = st.date_input("סנן לפי תאריך", value=None,
                                     format="DD/MM/YYYY", key="admin_fd")
            slots = fetch_slots(supabase, filter_date=filter_d)
            if not slots:
                st.info("אין מועדים.")
            else:
                df = pd.DataFrame(slots)
                for slot_date_str, group in df.groupby("date"):
                    gd = date.fromisoformat(slot_date_str)
                    st.markdown(
                        f"**📅 {safe(gd.strftime('%A, %d/%m/%Y'))}**"
                        f"<span style='color:#6b21a8;margin-right:10px;'>"
                        f" — {safe(to_heb_short(gd))}</span>",
                        unsafe_allow_html=True)
                    for _, row in group.iterrows():
                        c1, c2, c3, c4 = st.columns([1.5, 3, 1.5, 0.7])
                        c1.markdown(f"**🕐 {slot_range_label(row['time_slot'])}**")
                        if row["is_booked"]:
                            c2.markdown(
                                f'<span class="badge b-booked">✅ {safe(row.get("booked_by","?"))}'
                                f' ({safe(row.get("user_email","?"))})</span>',
                                unsafe_allow_html=True)
                            if c3.button("↩️ בטל הזמנה", key=f"unb_{row['id']}"):
                                _do_cancel(row["id"], row.get("gcal_event_id") or "")
                                st.rerun()
                        else:
                            c2.markdown('<span class="badge b-avail">🟢 פנוי</span>',
                                        unsafe_allow_html=True)
                            c3.empty()
                        if c4.button("🗑️", key=f"del_{row['id']}"):
                            if row.get("is_booked"):
                                _do_cancel(row["id"], row.get("gcal_event_id") or "")
                            delete_slot_record(supabase, row["id"])
                            st.rerun()
                    st.divider()

    # ── TAB 2: Booked overview ─────────────────────────────────
    with tab2:
        st.markdown('<p class="sec-title">👁️ סקירת הזמנות</p>', unsafe_allow_html=True)
        booked = fetch_booked_slots(supabase)
        if not booked:
            st.info("אין הזמנות פעילות כרגע.")
        else:
            user_map = {u["email"]: u for u in get_all_users(supabase)}
            for s in booked:
                gd = date.fromisoformat(s["date"])
                u  = user_map.get(s.get("user_email", ""), {})
                st.markdown(f"""
                <div class="bov-card">
                    <div class="slot-info">🕐 {safe(slot_range_label(s['time_slot']))} &nbsp;|&nbsp; 📅 {safe(gd.strftime('%d/%m/%Y'))}</div>
                    <div class="heb-info">{safe(to_heb_short(gd))}</div>
                    <div class="user-info">👤 {safe(u.get('name', s.get('booked_by','—')))} &nbsp;·&nbsp; ✉️ {safe(s.get('user_email','—'))} &nbsp;·&nbsp; 📞 {safe(u.get('phone','—'))}</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown(f"**סה״כ: {len(booked)} הזמנות**")

    # ── TAB 3: Users ───────────────────────────────────────────
    with tab3:
        with st.container(border=True):
            st.markdown('<p class="sec-title">➕ הוספת משתמש</p>', unsafe_allow_html=True)
            nc1, nc2, nc3 = st.columns(3)
            new_name  = nc1.text_input("שם מלא", placeholder="רחל כהן")
            new_email = nc2.text_input("אימייל", placeholder="rachel@example.com")
            new_phone = nc3.text_input("טלפון", placeholder="+972-50-...")
            if st.button("➕ הוסף משתמש", type="primary", use_container_width=True):
                norm = normalize_email(new_email)
                if not new_name or not valid_email(norm):
                    st.error("נא למלא שם ואימייל תקין.")
                elif get_user(supabase, norm):
                    st.warning("משתמש עם האימייל הזה כבר קיים.")
                else:
                    create_user(supabase, new_name, norm, new_phone)
                    st.success(f"✅ {safe(new_name)} נוסף/ה!")
                    st.rerun()

        with st.container(border=True):
            st.markdown('<p class="sec-title">👥 משתמשים רשומים</p>', unsafe_allow_html=True)
            users = get_all_users(supabase)
            if not users:
                st.info("אין משתמשים רשומים.")
            else:
                booked_map = {
                    s["user_email"]: f"{s['date']} @ {slot_range_label(s['time_slot'])}"
                    for s in fetch_slots(supabase) if s.get("is_booked") and s.get("user_email")
                }
                for u in users:
                    uc1, uc2, uc3, uc4, uc5 = st.columns([0.55, 2, 2.5, 2.5, 0.7])
                    initials = "".join(w[0].upper() for w in u["name"].split()[:2])
                    uc1.markdown(f'<div class="avatar">{safe(initials)}</div>', unsafe_allow_html=True)
                    uc2.markdown(f"**{safe(u['name'])}**")
                    uc3.caption(u["email"])
                    slot_label = booked_map.get(u["email"])
                    if slot_label:
                        uc4.markdown(f'<span class="badge b-booked">📅 {safe(slot_label)}</span>',
                                     unsafe_allow_html=True)
                    else:
                        uc4.markdown('<span class="badge b-none">אין הזמנה</span>',
                                     unsafe_allow_html=True)
                    if uc5.button("🗑️", key=f"delu_{u['email']}"):
                        booking_service.cancel_user_booking(supabase, st.secrets, u["email"])
                        delete_user_record(supabase, u["email"])
                        st.rerun()

    st.divider()
    if st.button("🚪 יציאה", use_container_width=True):
        st.session_state.admin_auth = False
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    inject_css()
    if _get_mode() == "admin":
        admin_view()
    else:
        user_view()

    now = now_il()
    st.markdown(
        f'<div class="footer">🕐 {now.strftime("%H:%M")} שעון ישראל'
        f' &nbsp;|&nbsp; <span dir="rtl">{safe(to_heb_short(now.date()))}</span></div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
