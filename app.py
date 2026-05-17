import streamlit as st
from supabase import create_client, Client
from pyluach import dates, hebrewcal, gematria
from datetime import date, datetime, timedelta
import pytz
import pandas as pd
import re

import traceback

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    _GCAL_AVAILABLE = True
except ImportError:
    _GCAL_AVAILABLE = False

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

# ── Hebrew date helpers ───────────────────────────────────────────────────────
_HEB_MONTHS = {
    1: "ניסן", 2: "אייר", 3: "סיון", 4: "תמוז", 5: "אב", 6: "אלול",
    7: "תשרי", 8: "חשון", 9: "כסלו", 10: "טבת", 11: "שבט", 12: "אדר",
    13: "אדר ב׳",
}

def to_heb(d: date) -> str:
    """Full Hebrew date string."""
    hd = dates.HebrewDate.from_pydate(d)
    day_s = gematria._num_to_str(hd.day)
    mon_s = _HEB_MONTHS.get(hd.month, str(hd.month))
    yr_s  = "ה׳" + gematria._num_to_str(hd.year % 1000)
    return f"{day_s} ב{mon_s} {yr_s}"

def to_heb_short(d: date) -> str:
    """Short Hebrew date string."""
    hd = dates.HebrewDate.from_pydate(d)
    return (f"{gematria._num_to_str(hd.day)} "
            f"{_HEB_MONTHS.get(hd.month, '')} "
            f"{gematria._num_to_str(hd.year % 1000)}")

# ── Google Calendar ──────────────────────────────────────────────────────────
@st.cache_resource
def get_calendar_service():
    """Build Google Calendar service from service account stored in secrets."""
    print("[GCAL] get_calendar_service() called")
    if not _GCAL_AVAILABLE:
        print("[GCAL] google libraries not available (_GCAL_AVAILABLE=False)")
        return None
    try:
        # Support both [gcp_service_account] table and GCP_SERVICE_ACCOUNT_JSON string
        if "gcp_service_account" in st.secrets:
            print("[GCAL] Loading credentials from [gcp_service_account] table")
            creds_info = dict(st.secrets["gcp_service_account"])
            pk = creds_info.get("private_key", "")
            print(f"[GCAL] private_key length: {len(pk)} chars, starts with: {pk[:30]!r}")
            # Fix escaped newlines that TOML multiline may mangle
            if "\\n" in pk:
                creds_info["private_key"] = pk.replace("\\n", "\n")
                print("[GCAL] Fixed escaped \\n in private_key")
        elif "GCP_SERVICE_ACCOUNT_JSON" in st.secrets:
            import json
            print("[GCAL] Loading credentials from GCP_SERVICE_ACCOUNT_JSON string")
            raw = st.secrets["GCP_SERVICE_ACCOUNT_JSON"]
            print(f"[GCAL] JSON string length: {len(raw)} chars")
            creds_info = json.loads(raw)
            pk = creds_info.get("private_key", "")
            print(f"[GCAL] private_key length after parse: {len(pk)} chars")
        else:
            print("[GCAL] No GCP credentials found in secrets!")
            return None
        print(f"[GCAL] service_account_email: {creds_info.get('client_email', 'N/A')}")
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        print("[GCAL] Credentials built successfully")
        svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
        print("[GCAL] Calendar service built successfully")
        return svc
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[GCAL] EXCEPTION in get_calendar_service:\n{tb}")
        st.warning(f"⚠️ Google Calendar לא זמין: {e}")
        st.error(f"🔴 פרטי שגיאה (get_calendar_service):\n```\n{tb}\n```")
        return None


def create_calendar_event(
    slot_date: date,
    start_time: str,
    user_name: str,
    user_email: str,
) -> bool:
    """Create a 1-hour Google Calendar event. Returns True on success."""
    print(f"[GCAL] create_calendar_event() called: date={slot_date}, time={start_time}, user={user_name}, email={user_email}")
    service = get_calendar_service()
    if service is None:
        print("[GCAL] service is None — aborting event creation")
        st.error("🔴 Google Calendar service לא אותחל. בדקי את ה-Secrets.")
        return False
    try:
        t = start_time[:5]
        start_dt = datetime.strptime(f"{slot_date.isoformat()} {t}", "%Y-%m-%d %H:%M")
        end_dt   = start_dt + timedelta(hours=1)
        tz_name  = "Asia/Jerusalem"
        event = {
            "summary": f"Dry Run: {user_name}",
            "description": "Scheduled via Dry Run Scheduler App",
            "start": {"dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": tz_name},
            "end":   {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),   "timeZone": tz_name},
            "attendees": [{"email": user_email}],
            "sendUpdates": "all",
        }
        calendar_id = st.secrets.get("CALENDAR_ID", "rachelyayn@gmail.com")
        print(f"[GCAL] Inserting event to calendar: {calendar_id}")
        print(f"[GCAL] Event payload: {event}")
        result = service.events().insert(calendarId=calendar_id, body=event, sendNotifications=True).execute()
        print(f"[GCAL] Event created successfully! id={result.get('id')}, link={result.get('htmlLink')}")
        return True
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[GCAL] EXCEPTION in create_calendar_event:\n{tb}")
        st.warning(f"⚠️ ההזמנה נשמרה, אך שליחת הזמנת לוח השנה נכשלה: {e}")
        st.error(f"🔴 פרטי שגיאה (create_calendar_event):\n```\n{tb}\n```")
        return False


# ── CSS ───────────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stMarkdown, p, div, span, label {
        font-family: 'Inter', 'Segoe UI', sans-serif !important;
        font-size: 17px;
    }
    h1 { font-size: 30px !important; font-weight: 800 !important; }
    h2 { font-size: 24px !important; font-weight: 700 !important; }
    h3 { font-size: 21px !important; font-weight: 700 !important; }
    .stApp { background: #f0f2f6; }

    /* Hero */
    .hero {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 60%, #a21caf 100%);
        color: white; border-radius: 22px; padding: 30px 34px; margin-bottom: 26px;
        box-shadow: 0 10px 40px rgba(79,70,229,0.35);
    }
    .hero h1 { font-size:30px!important; font-weight:800!important;
               margin:0 0 6px; color:white!important; }
    .hero p   { font-size:17px!important; margin:0; opacity:.88; color:white!important; }

    /* Date card */
    .date-card {
        background: white; border-radius: 18px; padding: 22px 26px 10px;
        margin-bottom: 18px; box-shadow: 0 3px 14px rgba(0,0,0,0.08);
        border: 1.5px solid #e5e7eb;
    }
    .date-card .gc { font-size:20px; font-weight:700; color:#111827; }
    .date-card .hc { font-size:18px; color:#6b21a8; font-weight:600;
                     direction:rtl; text-align:right; margin-top:2px; }

    /* My slot */
    .my-slot {
        background: linear-gradient(135deg,#059669,#10b981); color:white;
        border-radius:20px; padding:22px 28px; margin-bottom:22px;
        box-shadow:0 6px 24px rgba(5,150,105,0.30);
    }
    .my-slot h2 { font-size:22px!important; font-weight:800!important;
                  margin:0 0 8px; color:white!important; }
    .my-slot .row { font-size:17px; margin:4px 0; color:white; }
    .my-slot .heb { font-size:18px; direction:rtl; color:#d1fae5; }

    /* Buttons */
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

    /* Badges */
    .badge { display:inline-block; border-radius:20px; padding:5px 16px;
             font-size:14px; font-weight:700; }
    .b-avail  { background:#ede9fe; color:#4f46e5; }
    .b-booked { background:#d1fae5; color:#065f46; }
    .b-none   { background:#f3f4f6; color:#6b7280; }

    /* Section title */
    .sec-title { font-size:20px!important; font-weight:800!important;
                 color:#111827!important; margin:0 0 14px!important; }

    /* Avatar */
    .avatar {
        width:42px; height:42px; border-radius:50%;
        background:linear-gradient(135deg,#4f46e5,#7c3aed);
        color:white; font-size:17px; font-weight:800;
        display:inline-flex; align-items:center; justify-content:center;
    }

    /* Booked overview card */
    .bov-card {
        background:white; border-radius:16px; padding:16px 20px; margin-bottom:10px;
        border-left:5px solid #7c3aed; box-shadow:0 2px 8px rgba(0,0,0,0.06);
    }
    .bov-card .slot-info { font-size:18px; font-weight:700; color:#111827; }
    .bov-card .user-info { font-size:15px; color:#6b7280; margin-top:4px; }
    .bov-card .heb-info  { font-size:16px; color:#6b21a8; direction:rtl; margin-top:2px; }

    /* Tabs */
    .stTabs [data-baseweb="tab"] { font-size:16px!important; font-weight:700!important;
                                    padding:12px 22px!important; }

    /* Footer */
    .footer { text-align:center; color:#9ca3af; font-size:14px; margin-top:36px; }
    #MainMenu, footer, header { visibility:hidden; }
    </style>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# DB — USERS
# ═══════════════════════════════════════════════════════════════
def get_user(email: str):
    r = supabase.table("users").select("*").eq("email", email.lower().strip()).execute()
    return r.data[0] if r.data else None

def create_user(name: str, email: str, phone: str):
    supabase.table("users").insert({
        "name": name.strip(), "email": email.lower().strip(), "phone": phone.strip(),
    }).execute()

def get_all_users():
    return supabase.table("users").select("*").order("name").execute().data or []

def delete_user(email: str):
    r = supabase.table("slots").select("id").eq("user_email", email).eq("is_booked", True).execute()
    for s in (r.data or []):
        cancel_slot(s["id"])
    supabase.table("users").delete().eq("email", email).execute()

# ═══════════════════════════════════════════════════════════════
# DB — SLOTS
# ═══════════════════════════════════════════════════════════════
def fetch_slots(filter_date=None, only_available: bool = False):
    q = supabase.table("slots").select("*")
    if filter_date:
        q = q.eq("date", filter_date.isoformat())
    elif only_available:
        tomorrow = (now_il().date() + timedelta(days=1)).isoformat()
        q = q.gte("date", tomorrow)
    if only_available:
        q = q.eq("is_booked", False)
    return q.order("date").order("time_slot").execute().data or []

def fetch_booked_slots():
    return (supabase.table("slots").select("*")
            .eq("is_booked", True).order("date").order("time_slot").execute().data or [])

def fetch_user_slot(user_email: str):
    r = (supabase.table("slots").select("*")
         .eq("is_booked", True).eq("user_email", user_email).execute())
    return r.data[0] if r.data else None

def add_slot(slot_date: date, time_slot: str) -> bool:
    ex = supabase.table("slots").select("id").eq("date", slot_date.isoformat()).eq("time_slot", time_slot).execute()
    if ex.data:
        return False
    supabase.table("slots").insert({
        "date": slot_date.isoformat(), "time_slot": time_slot, "is_booked": False,
    }).execute()
    return True

def book_slot(slot_id: int, user_email: str, user_name: str):
    supabase.table("slots").update({
        "is_booked": True, "user_email": user_email, "booked_by": user_name,
    }).eq("id", slot_id).execute()

def cancel_slot(slot_id: int):
    supabase.table("slots").update({
        "is_booked": False, "user_email": None, "booked_by": None,
    }).eq("id", slot_id).execute()

def delete_slot(slot_id: int):
    supabase.table("slots").delete().eq("id", slot_id).execute()

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def valid_email(email: str) -> bool:
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

def get_mode() -> str:
    return st.query_params.get("mode", "user")

# ═══════════════════════════════════════════════════════════════
# USER VIEW
# ═══════════════════════════════════════════════════════════════
def user_view():
    def slot_range_label(start_time: str) -> str:
        t = start_time[:5]  # handle both HH:MM and HH:MM:SS from DB
        start_dt = datetime.strptime(t, "%H:%M")
        end_dt = start_dt + timedelta(hours=1)
        return f"{t} - {end_dt.strftime('%H:%M')}"

    st.markdown("""
    <div class="hero">
        <h1>📅 תיאום Dry Run</h1>
        <p>בחרי מועד שנוח לך 👇</p>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.get("user_profile"):
        with st.container(border=True):
            st.markdown('<p class="sec-title">🔑 הכניסי את האימייל שלך</p>', unsafe_allow_html=True)
            email_input = st.text_input("אימייל", placeholder="your@email.com",
                                        label_visibility="collapsed")
            if st.button("המשך ←", type="primary", use_container_width=True):
                if not valid_email(email_input):
                    st.error("נא להכניס כתובת אימייל תקינה.")
                else:
                    user = get_user(email_input)
                    if not user:
                        st.error("❌ האימייל הזה אינו רשום. פני למנהל/ת.")
                    else:
                        st.session_state.user_profile = user
                        st.rerun()
        return

    user = st.session_state.user_profile
    st.markdown(f"👋 **שלום, {user['name']}!**")

    my_slot = fetch_user_slot(user["email"])

    if my_slot:
        gd = date.fromisoformat(my_slot["date"])
        slot_range = slot_range_label(my_slot["time_slot"])
        st.markdown(f"""
        <div class="my-slot">
            <h2>✅ הפגישה שלך</h2>
            <div class="row">📅 {gd.strftime('%A, %d %B %Y')}</div>
            <div class="heb">{to_heb(gd)}</div>
            <div class="row">🕐 {slot_range}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("רוצה לשנות? ניתן לבטל ולבחור מועד אחר.")
            if st.button("🗑️ ביטול הפגישה", use_container_width=True):
                st.session_state.confirm_cancel = True

        if st.session_state.get("confirm_cancel"):
            with st.container(border=True):
                st.warning(f"לבטל את **{gd.strftime('%d/%m/%Y')} @ {slot_range}**?")
                c1, c2 = st.columns(2)
                if c1.button("כן, בטלי", type="primary", use_container_width=True):
                    cancel_slot(my_slot["id"])
                    st.session_state.confirm_cancel = False
                    st.rerun()
                if c2.button("השאירי", use_container_width=True):
                    st.session_state.confirm_cancel = False
                    st.rerun()
    else:
        slots = fetch_slots(only_available=True)
        if not slots:
            st.info("🕐 אין מועדים פנויים כרגע.")
        else:
            st.markdown('<p class="sec-title">🗓️ מועדים פנויים</p>', unsafe_allow_html=True)
            df = pd.DataFrame(slots)
            for slot_date_str, group in df.groupby("date"):
                gd = date.fromisoformat(slot_date_str)
                st.markdown(f"""
                <div class="date-card">
                    <div class="gc">📅 {gd.strftime('%A, %d %B %Y')}</div>
                    <div class="hc">{to_heb(gd)}</div>
                </div>
                """, unsafe_allow_html=True)
                rows = list(group.iterrows())
                cols = st.columns(min(len(rows), 4))
                for idx, (_, row) in enumerate(rows):
                    slot_range = slot_range_label(row["time_slot"])
                    if cols[idx % 4].button(f"🕐 {slot_range}", key=f"s_{row['id']}"):
                        st.session_state.pending_slot = {
                            "id": row["id"], "date": slot_date_str,
                            "time": row["time_slot"], "time_range": slot_range, "heb": to_heb(gd),
                        }

            if st.session_state.get("pending_slot"):
                ps = st.session_state.pending_slot
                gd_p = date.fromisoformat(ps["date"])
                with st.container(border=True):
                    st.subheader("✅ אישור הזמנה")
                    st.markdown(f"""
                    - 📅 **{gd_p.strftime('%A, %d %B %Y')}**
                    - <span dir="rtl">{ps['heb']}</span>
                    - 🕐 **{ps['time_range']}**
                    - ⏳ **שעת התחלה:** {ps['time']} | **שעת סיום:** {ps['time_range'].split(' - ')[1]}
                    - 👤 **{user['name']}**
                    """, unsafe_allow_html=True)
                    c1, c2 = st.columns(2)
                    if c1.button("✅ אישור", type="primary", use_container_width=True):
                        book_slot(ps["id"], user["email"], user["name"])
                        gcal_ok = create_calendar_event(
                            date.fromisoformat(ps["date"]),
                            ps["time"],
                            user["name"],
                            user["email"],
                        )
                        if gcal_ok:
                            st.toast("📅 הזמנת לוח השנה נשלחה לאימייל שלך!")
                        st.session_state.pending_slot = None
                        st.balloons()
                        st.rerun()
                    if c2.button("❌ ביטול", use_container_width=True):
                        st.session_state.pending_slot = None
                        st.rerun()

    if st.button("🚪 יציאה", use_container_width=True):
        st.session_state.user_profile = None
        st.rerun()

# ═══════════════════════════════════════════════════════════════
# ADMIN VIEW
# ═══════════════════════════════════════════════════════════════
def admin_view():
    def slot_range_label(start_time: str) -> str:
        t = start_time[:5]  # handle both HH:MM and HH:MM:SS from DB
        start_dt = datetime.strptime(t, "%H:%M")
        end_dt = start_dt + timedelta(hours=1)
        return f"{t} - {end_dt.strftime('%H:%M')}"

    st.markdown("""
    <div class="hero">
        <h1>🔧 Admin Dashboard</h1>
        <p>ניהול מועדים ומשתמשים</p>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.get("admin_auth"):
        with st.container(border=True):
            st.markdown('<p class="sec-title">🔐 כניסת מנהל</p>', unsafe_allow_html=True)
            pwd = st.text_input("סיסמה", type="password", label_visibility="collapsed",
                                placeholder="הכנס סיסמה")
            if st.button("כניסה", type="primary", use_container_width=True):
                if pwd == st.secrets.get("ADMIN_PASSWORD", "dryrun2026"):
                    st.session_state.admin_auth = True
                    st.rerun()
                else:
                    st.error("סיסמה שגויה.")
        return

    tab1, tab2, tab3 = st.tabs(["📅 מועדים", "👁️ סקירת הזמנות", "👥 משתמשים"])

    # TAB 1 — SLOTS
    with tab1:
        with st.container(border=True):
            st.markdown('<p class="sec-title">➕ הוספת מועד</p>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            today_il = now_il().date()
            tomorrow_il = today_il + timedelta(days=1)
            sel_date = c1.date_input("תאריך", value=tomorrow_il, min_value=tomorrow_il,
                                     format="DD/MM/YYYY")
            # Only full hours; exclude times already saved for this date
            all_hour_opts = [f"{h:02d}:00" for h in range(7, 22)]
            if sel_date:
                taken = {
                    s["time_slot"][:5]
                    for s in fetch_slots(filter_date=sel_date)
                }
                available_opts = [t for t in all_hour_opts if t not in taken]
            else:
                available_opts = all_hour_opts
            if not available_opts:
                c2.warning("כל השעות לתאריך זה כבר תפוסות.")
                time_slot = None
            else:
                time_slot = c2.selectbox(
                    "שעה (משך כל פגישה: שעה)",
                    available_opts,
                    format_func=slot_range_label,
                )
            if sel_date:
                st.markdown(
                    f'<p style="color:#6b21a8;font-size:17px;direction:rtl;">'
                    f'📜 {to_heb(sel_date)}</p>',
                    unsafe_allow_html=True,
                )
                st.caption(f"משך המועד: {slot_range_label(time_slot)}")
            if st.button("💾 שמור מועד", type="primary", use_container_width=True):
                if not time_slot:
                    st.warning("אין שעות פנויות לתאריך זה.")
                elif add_slot(sel_date, time_slot):
                    st.success("✅ מועד נוסף!")
                    st.rerun()
                else:
                    st.warning("המועד הזה כבר קיים.")

        with st.container(border=True):
            st.markdown('<p class="sec-title">📋 כל המועדים</p>', unsafe_allow_html=True)
            filter_d = st.date_input("סנן לפי תאריך", value=None,
                                     format="DD/MM/YYYY", key="admin_fd")
            slots = fetch_slots(filter_date=filter_d)
            if not slots:
                st.info("אין מועדים.")
            else:
                df = pd.DataFrame(slots)
                for slot_date_str, group in df.groupby("date"):
                    gd = date.fromisoformat(slot_date_str)
                    st.markdown(
                        f"**📅 {gd.strftime('%A, %d/%m/%Y')}**"
                        f"<span style='color:#6b21a8;margin-right:10px;'>"
                        f" — {to_heb_short(gd)}</span>",
                        unsafe_allow_html=True,
                    )
                    for _, row in group.iterrows():
                        c1, c2, c3, c4 = st.columns([1.5, 3, 1.5, 0.7])
                        c1.markdown(f"**🕐 {slot_range_label(row['time_slot'])}**")
                        if row["is_booked"]:
                            c2.markdown(
                                f'<span class="badge b-booked">✅ {row.get("booked_by","?")} '
                                f'({row.get("user_email","?")})</span>',
                                unsafe_allow_html=True)
                            if c3.button("↩️ בטל הזמנה", key=f"unb_{row['id']}"):
                                cancel_slot(row["id"])
                                st.rerun()
                        else:
                            c2.markdown('<span class="badge b-avail">🟢 פנוי</span>',
                                        unsafe_allow_html=True)
                            c3.empty()
                        if c4.button("🗑️", key=f"del_{row['id']}"):
                            delete_slot(row["id"])
                            st.rerun()
                    st.divider()

    # TAB 2 — BOOKED OVERVIEW
    with tab2:
        st.markdown('<p class="sec-title">👁️ סקירת הזמנות</p>', unsafe_allow_html=True)
        booked = fetch_booked_slots()
        if not booked:
            st.info("אין הזמנות פעילות כרגע.")
        else:
            users_list = get_all_users()
            user_map = {u["email"]: u for u in users_list}
            for s in booked:
                gd = date.fromisoformat(s["date"])
                u = user_map.get(s.get("user_email", ""), {})
                uname  = u.get("name", s.get("booked_by", "—"))
                uemail = s.get("user_email", "—")
                uphone = u.get("phone", "—")
                st.markdown(f"""
                <div class="bov-card">
                    <div class="slot-info">🕐 {s['time_slot']} &nbsp;|&nbsp; 📅 {gd.strftime('%d/%m/%Y')}</div>
                    <div class="heb-info">{to_heb_short(gd)}</div>
                    <div class="user-info">👤 {uname} &nbsp;·&nbsp; ✉️ {uemail} &nbsp;·&nbsp; 📞 {uphone}</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown(f"**סה״כ: {len(booked)} הזמנות**")

    # TAB 3 — USERS
    with tab3:
        with st.container(border=True):
            st.markdown('<p class="sec-title">➕ הוספת משתמש</p>', unsafe_allow_html=True)
            nc1, nc2, nc3 = st.columns(3)
            new_name  = nc1.text_input("שם מלא", placeholder="רחל כהן")
            new_email = nc2.text_input("אימייל", placeholder="rachel@example.com")
            new_phone = nc3.text_input("טלפון", placeholder="+972-50-...")
            if st.button("➕ הוסף משתמש", type="primary", use_container_width=True):
                if not new_name or not valid_email(new_email):
                    st.error("נא למלא שם ואימייל תקין.")
                elif get_user(new_email):
                    st.warning("משתמש עם האימייל הזה כבר קיים.")
                else:
                    create_user(new_name, new_email, new_phone)
                    st.success(f"✅ {new_name} נוסף/ה!")
                    st.rerun()

        with st.container(border=True):
            st.markdown('<p class="sec-title">👥 משתמשים רשומים</p>', unsafe_allow_html=True)
            users = get_all_users()
            if not users:
                st.info("אין משתמשים רשומים.")
            else:
                all_slots = fetch_slots()
                booked_map = {
                    s["user_email"]: f"{s['date']} @ {s['time_slot']}"
                    for s in all_slots if s.get("is_booked") and s.get("user_email")
                }
                for u in users:
                    uc1, uc2, uc3, uc4, uc5 = st.columns([0.55, 2, 2.5, 2.5, 0.7])
                    initials = "".join(w[0].upper() for w in u["name"].split()[:2])
                    uc1.markdown(f'<div class="avatar">{initials}</div>', unsafe_allow_html=True)
                    uc2.markdown(f"**{u['name']}**")
                    uc3.caption(u["email"])
                    slot_label = booked_map.get(u["email"])
                    if slot_label:
                        uc4.markdown(f'<span class="badge b-booked">📅 {slot_label}</span>',
                                     unsafe_allow_html=True)
                    else:
                        uc4.markdown('<span class="badge b-none">אין הזמנה</span>',
                                     unsafe_allow_html=True)
                    if uc5.button("🗑️", key=f"delu_{u['email']}"):
                        delete_user(u["email"])
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
    if get_mode() == "admin":
        admin_view()
    else:
        user_view()

    now = now_il()
    st.markdown(
        f'<div class="footer">🕐 {now.strftime("%H:%M")} שעון ישראל'
        f' &nbsp;|&nbsp; <span dir="rtl">{to_heb_short(now.date())}</span></div>',
        unsafe_allow_html=True,
    )

if __name__ == "__main__":
    main()
