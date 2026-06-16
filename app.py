"""
Scheduling App — thin UI layer.
All business logic lives in services/, repositories/, utils/.

Modules:
  - Dry Run Management  (existing, ?mode=user or session active_module="dryrun")
  - Grandma Visits      (new, session active_module="grandma")
Admin dashboard at ?mode=admin covers both modules.
"""
import logging
import sys
import os

# ── SSL: use Windows certificate store (fixes corporate proxy SSL inspection) ──
# Must run before any network-capable import (streamlit, supabase, httpx, etc.).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    # truststore is missing — print a clear install instruction and exit.
    # Using print here because logging is not yet configured at this point.
    print(
        "\n[SSL ERROR] The 'truststore' package is required on this machine to "
        "connect through the corporate SSL proxy.\n"
        "Fix: run  pip install truststore  then restart the app.\n",
        file=sys.stderr,
    )
    sys.exit(1)

import streamlit as st
from supabase import create_client, Client
from datetime import date, datetime, timedelta
import pytz
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="תיאום פגישות",
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
from repositories.descendants_repository import (
    get_descendant_by_name, get_all_descendants,
    create_descendant, deactivate_descendant, reactivate_descendant,
)
from repositories.visit_slots_repository import (
    fetch_available_visit_slots, fetch_all_visit_slots,
    add_visit_slot, delete_visit_slot,
    fetch_private_blocked_slot_ids,
)
from repositories.grandma_visits_repository import (
    get_future_visits, get_past_visits, get_all_visits,
    update_visit_notes_photo, cancel_visit, upload_visit_photo,
    get_visits_with_photos,
)
from repositories.grandmas_repository import (
    get_active_grandmas, get_grandma_by_id,
    get_all_grandmas, create_grandma, update_grandma, set_grandma_active,
)
from repositories import managers_repository
from services import booking_service, grandma_visit_service
from utils.constants import SERVICE_DRY_RUN, SERVICE_GRANDMA

# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_mode() -> str:
    return st.query_params.get("mode", "")

def _do_cancel(slot_id: int, gcal_event_id: str = "") -> None:
    booking_service.cancel(supabase, st.secrets, slot_id, gcal_event_id or "")

def _format_slot_dt(slot_iso: str) -> str:
    """Format a TIMESTAMPTZ ISO string to Israeli 'dd/MM/yyyy HH:mm'."""
    dt = datetime.fromisoformat(slot_iso).astimezone(IL_TZ)
    return dt.strftime("%d/%m/%Y %H:%M")

def _slot_dt(slot_iso: str) -> datetime:
    # Python 3.10 fromisoformat() can't parse 'Z'; Supabase sometimes returns it
    if slot_iso.endswith("Z"):
        slot_iso = slot_iso[:-1] + "+00:00"
    return datetime.fromisoformat(slot_iso).astimezone(IL_TZ)


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
    /* Dry Run hero */
    .hero {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 60%, #a21caf 100%);
        color: white; border-radius: 22px; padding: 30px 34px; margin-bottom: 26px;
        box-shadow: 0 10px 40px rgba(79,70,229,0.35);
    }
    .hero h1 { font-size:30px!important; font-weight:800!important; margin:0 0 6px; color:white!important; }
    .hero p   { font-size:17px!important; margin:0; opacity:.88; color:white!important; }
    /* Grandma hero */
    .hero-grandma {
        background: linear-gradient(135deg, #d97706 0%, #dc2626 55%, #be185d 100%);
        color: white; border-radius: 22px; padding: 30px 34px; margin-bottom: 26px;
        box-shadow: 0 10px 40px rgba(220,38,38,0.30);
        direction: rtl; text-align: right;
    }
    .hero-grandma h1 { font-size:30px!important; font-weight:800!important; margin:0 0 6px; color:white!important; }
    .hero-grandma p  { font-size:17px!important; margin:0; opacity:.88; color:white!important; }
    /* Module selection cards */
    .module-card {
        background: white; border-radius: 22px; padding: 36px 28px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.10); text-align: center;
        border: 2px solid #e5e7eb; cursor: pointer; transition: all .2s;
    }
    .module-card:hover { border-color: #7c3aed; transform: translateY(-3px); }
    .module-card .mc-icon { font-size: 52px; margin-bottom: 12px; }
    .module-card .mc-title { font-size: 20px; font-weight: 800; color: #111827; }
    .module-card .mc-sub   { font-size: 14px; color: #6b7280; margin-top: 6px; }
    /* Shared */
    .date-card {
        background: white; border-radius: 18px; padding: 22px 26px 10px;
        margin-bottom: 18px; box-shadow: 0 3px 14px rgba(0,0,0,0.08);
        border: 1.5px solid #e5e7eb; direction:rtl; text-align:right;
    }
    .date-card .gc { font-size:20px; font-weight:700; color:#111827; direction:rtl; text-align:right; }
    .date-card .hc { font-size:18px; color:#6b21a8; font-weight:600; direction:rtl; text-align:right; margin-top:2px; }
    .my-slot {
        background: linear-gradient(135deg,#059669,#10b981); color:white;
        border-radius:20px; padding:22px 28px; margin-bottom:22px;
        box-shadow:0 6px 24px rgba(5,150,105,0.30);
    }
    .my-slot h2 { font-size:22px!important; font-weight:800!important; margin:0 0 8px; color:white!important; }
    .my-slot .row { font-size:17px; margin:4px 0; color:white; }
    .my-slot .heb { font-size:18px; direction:rtl; color:#d1fae5; }
    /* Visit cards */
    .visit-card {
        background: white; border-radius: 16px; padding: 18px 22px; margin-bottom: 12px;
        border-left: 5px solid #d97706; box-shadow: 0 2px 10px rgba(0,0,0,0.07);
        direction: rtl; text-align: right;
    }
    .visit-card .vc-time { font-size: 18px; font-weight: 700; color: #111827; }
    .visit-card .vc-heb  { font-size: 15px; color: #92400e; margin-top: 2px; }
    .visit-card .vc-status { font-size: 14px; color: #6b7280; margin-top: 4px; }
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
    .b-warm   { background:#fef3c7; color:#92400e; }
    .sec-title { font-size:20px!important; font-weight:800!important; color:#111827!important; margin:0 0 14px!important; text-align:right!important; direction:rtl!important; }
    .avatar {
        width:42px; height:42px; border-radius:50%;
        background:linear-gradient(135deg,#4f46e5,#7c3aed);
        color:white; font-size:17px; font-weight:800;
        display:inline-flex; align-items:center; justify-content:center;
    }
    .bov-card {
        background:white; border-radius:16px; padding:16px 20px; margin-bottom:10px;
        border-left:5px solid #7c3aed; box-shadow:0 2px 8px rgba(0,0,0,0.06);
        direction:rtl; text-align:right;
    }
    .bov-card .slot-info { font-size:18px; font-weight:700; color:#111827; }
    .bov-card .user-info { font-size:15px; color:#6b7280; margin-top:4px; }
    .bov-card .heb-info  { font-size:16px; color:#6b21a8; direction:rtl; margin-top:2px; }
    .stTabs [data-baseweb="tab"] { font-size:16px!important; font-weight:700!important; padding:12px 22px!important; }
    .footer { text-align:center; color:#9ca3af; font-size:14px; margin-top:36px; }
    #MainMenu, footer, header { visibility:hidden; }
    /* Grandma selection cards */
    .grandma-card {
        background: white; border-radius: 22px; padding: 28px 20px 20px;
        text-align: center; direction: rtl;
        border: 2px solid #fed7aa;
        box-shadow: 0 4px 18px rgba(217,119,6,0.10);
        transition: all 0.2s; margin-bottom: 12px;
    }
    .grandma-card:hover {
        border-color: #d97706; transform: translateY(-3px);
        box-shadow: 0 8px 28px rgba(217,119,6,0.22);
    }
    .grandma-card .gc-photo {
        width: 88px; height: 88px; border-radius: 50%;
        object-fit: cover; display: block;
        margin: 0 auto 14px; border: 3px solid #fde68a;
    }
    .grandma-card .gc-emoji { font-size: 64px; display: block; margin-bottom: 10px; line-height: 1; }
    .grandma-card .gc-name  { font-size: 22px; font-weight: 800; color: #92400e; margin-bottom: 8px; }
    .grandma-card .gc-desc  { font-size: 14px; color: #6b7280; line-height: 1.6; }
    /* RTL alert messages (info/warning/error/success) */
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
        direction: rtl !important;
        text-align: right !important;
    }
    /* RTL form controls — Hebrew-first app */
    .stTextInput input, .stTextArea textarea, .stNumberInput input {
        direction: rtl !important;
        text-align: right !important;
    }
    /* Password inputs stay LTR so typed characters never slide under the
       reveal-eye icon (Streamlit toggles type to "text" when revealed). */
    .stTextInput input[type="password"] {
        direction: ltr !important;
        text-align: left !important;
    }
    /* Labels: force block + full width so text-align:right always takes effect. */
    [data-testid="stWidgetLabel"] {
        direction: rtl !important;
        text-align: right !important;
        display: block !important;
        width: 100% !important;
    }
    [data-testid="stWidgetLabel"] p { text-align: right !important; }
    .stRadio [role="radiogroup"] { direction: rtl !important; }
    .stRadio label { direction: rtl !important; }
    </style>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# MODULE SELECTION
# ═══════════════════════════════════════════════════════════════
def module_selection_view():
    st.markdown("""
    <div style="text-align:center; padding: 28px 0 18px;">
        <div style="font-size:36px; font-weight:900; color:#111827;">ברוכים הבאים 👋</div>
        <div style="font-size:18px; color:#6b7280; margin-top:8px;">בחרו מודול להמשך</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("""
        <div class="module-card">
            <div class="mc-icon">📅</div>
            <div class="mc-title">ניהול Dry Run</div>
            <div class="mc-sub">תיאום פגישות לצוות</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("כניסה → Dry Run", key="sel_dryrun", use_container_width=True):
            st.session_state.active_module = "dryrun"
            st.rerun()

    with col2:
        st.markdown("""
        <div class="module-card" style="border-color:#fbbf24;">
            <div class="mc-icon">🌸</div>
            <div class="mc-title" style="direction:rtl;">ביקורים אצל סבתא</div>
            <div class="mc-sub" style="direction:rtl;">קביעת ביקורים משפחתיים</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("כניסה ← ביקורי סבתא", key="sel_grandma", use_container_width=True):
            st.session_state.active_module = "grandma"
            st.rerun()


# ═══════════════════════════════════════════════════════════════
# USER VIEW (Dry Run — unchanged)
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
        if st.button("← חזרה לתפריט", use_container_width=True):
            st.session_state.active_module = None
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
        st.session_state.active_module = None
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# GRANDMA VISITS MODULE
# ═══════════════════════════════════════════════════════════════

def _grandma_reset():
    """Clear all grandma session state and return to module selection."""
    for key in ["grandma_screen", "grandma_visitor", "grandma_selected_grandma",
                "grandma_pending_slot", "grandma_note_visit",
                "grandma_booking_success", "grandma_name_not_found"]:
        st.session_state.pop(key, None)
    # Clear dynamic prefixed keys to prevent ghost UI state on re-entry:
    #   confirm_cancel_visit_{id} — per-visit cancellation dialogs
    #   grandma_pc_{slot_id}      — participant-count stepper values
    for prefix in ("confirm_cancel_visit_", "grandma_pc_"):
        stale = [k for k in st.session_state if k.startswith(prefix)]
        for k in stale:
            del st.session_state[k]
    st.session_state.active_module = None


def _grandma_error_card(title: str, body: str) -> None:
    """Render a polished RTL error card (replaces plain st.error for Grandma module)."""
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg,#fef2f2,#fff7ed);
        border: 2px solid #fca5a5;
        border-radius: 18px;
        padding: 20px 24px;
        direction: rtl;
        text-align: right;
        margin: 14px 0 4px;
        box-shadow: 0 4px 14px rgba(239,68,68,0.12);
    ">
        <div style="font-size:26px;margin-bottom:8px;">😔</div>
        <div style="font-size:17px;font-weight:700;color:#991b1b;margin-bottom:5px;">{safe(title)}</div>
        <div style="font-size:15px;color:#b91c1c;line-height:1.7;">{safe(body)}</div>
    </div>
    """, unsafe_allow_html=True)


def grandma_module():
    screen = st.session_state.get("grandma_screen", "identify")
    if screen == "identify":
        grandma_identify_view()
    elif screen == "select_grandma":
        grandma_select_view()
    elif screen == "dashboard":
        grandma_dashboard_view()
    elif screen == "schedule":
        grandma_schedule_view()
    elif screen == "notes":
        grandma_notes_view()
    elif screen == "gallery":
        grandma_gallery_view()


def grandma_select_view():
    visitor = st.session_state.get("grandma_visitor", {})
    name = visitor.get("name", "")

    # ── Deep-link: ?mode=grandma&gid=<uuid> skips the card grid ──────────────
    gid_param = st.query_params.get("gid", "")
    if gid_param:
        try:
            grandma = get_grandma_by_id(supabase, gid_param)
        except Exception:
            logger.exception("[GRANDMA] deep-link grandma lookup failed gid=%s", gid_param)
            grandma = None
        if grandma and grandma.get("is_active"):
            st.session_state.grandma_selected_grandma = grandma
            st.session_state.grandma_screen = "dashboard"
            st.rerun()
            return
        # Invalid or inactive gid — fall through to the normal card grid

    st.markdown(f"""
    <div class="hero-grandma">
        <h1>🌸 שלום {safe(name)}!</h1>
        <p>אצל איזו סבתא תרצי לבקר?</p>
    </div>
    """, unsafe_allow_html=True)

    try:
        grandmas = get_active_grandmas(supabase)
    except Exception:
        logger.exception("[GRANDMA] Failed to load grandmas list")
        st.error("שגיאה בטעינת הנתונים. אנא נסי שוב.")
        if st.button("חזרה לתפריט →", use_container_width=True):
            _grandma_reset()
            st.rerun()
        return

    if not grandmas:
        st.info("אין סבתות פעילות כרגע. אנא פני למנהל/ת התוכנית.")
        if st.button("חזרה לתפריט →", use_container_width=True):
            _grandma_reset()
            st.rerun()
        return

    cols_count = min(len(grandmas), 3)
    cols = st.columns(cols_count, gap="large")
    for idx, grandma in enumerate(grandmas):
        with cols[idx % cols_count]:
            if grandma.get("photo_url"):
                media_html = f'<img src="{safe(grandma["photo_url"])}" class="gc-photo" alt="">'
            else:
                media_html = '<span class="gc-emoji">👵</span>'
            desc_html = (
                f'<div class="gc-desc">{safe(grandma["description"])}</div>'
                if grandma.get("description") else ""
            )
            st.markdown(f"""
            <div class="grandma-card">
                {media_html}
                <div class="gc-name">{safe(grandma["name"])}</div>
                {desc_html}
            </div>
            """, unsafe_allow_html=True)
            if st.button(
                "בחרי ←",
                key=f"sel_g_{grandma['id']}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state.grandma_selected_grandma = grandma
                st.session_state.grandma_screen = "dashboard"
                st.rerun()

    st.divider()
    if st.button("חזרה לתפריט →", use_container_width=True):
        _grandma_reset()
        st.rerun()


def grandma_identify_view():
    st.markdown("""
    <div class="hero-grandma">
        <h1>🌸 ביקור אצל סבתא</h1>
        <p>הכניסי את שמך כדי להמשיך</p>
    </div>
    """, unsafe_allow_html=True)

    # Persistent error card (survives rerun)
    if st.session_state.get("grandma_name_not_found"):
        _grandma_error_card(
            "השם לא נמצא במערכת",
            "לא מצאנו את השם במערכת. כדי לקבוע ביקור, אנא פני למנהל/ת התוכנית.",
        )

    with st.container(border=True):
        st.markdown('<p class="sec-title" style="direction:rtl;">שם מלא</p>',
                    unsafe_allow_html=True)
        name_input = st.text_input("שם מלא", placeholder="למשל: רחל כהן",
                                   label_visibility="collapsed")
        if st.button("המשך ←", type="primary", use_container_width=True):
            st.session_state.grandma_name_not_found = False
            name_stripped = name_input.strip()
            if not name_stripped:
                st.warning("נא להכניס שם.")
            else:
                descendant = None
                try:
                    descendant = get_descendant_by_name(supabase, name_stripped)
                except Exception:
                    logger.exception("[GRANDMA] name lookup failed")
                    # descendant stays None — treated identically to not-found below
                if not descendant:
                    st.session_state.grandma_name_not_found = True
                    st.rerun()
                else:
                    st.session_state.grandma_visitor = descendant
                    st.session_state.grandma_screen = "select_grandma"
                    st.rerun()

    if st.button("חזרה לתפריט →", use_container_width=True):
        _grandma_reset()
        st.rerun()


def grandma_dashboard_view():
    visitor = st.session_state.get("grandma_visitor", {})
    name = visitor.get("name", "")
    desc_id = visitor.get("id", "")

    # Guard: grandma must be selected before reaching dashboard
    grandma = st.session_state.get("grandma_selected_grandma")
    if not grandma:
        st.session_state.grandma_screen = "select_grandma"
        st.rerun()
        return

    grandma_id   = grandma["id"]
    grandma_name = grandma["name"]

    st.markdown(f"""
    <div class="hero-grandma">
        <h1>🌸 שלום {safe(name)}!</h1>
        <p>הביקורים שלך אצל {safe(grandma_name)}</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Success banner ─────────────────────────────────────────
    if st.session_state.pop("grandma_booking_success", False):
        st.balloons()
        st.success("🌸 הביקור נקבע בהצלחה! סבתא מחכה לך.")
        st.divider()

    # ── Future visits (scoped to this grandma) ─────────────────
    future_visits = get_future_visits(supabase, desc_id, grandma_id=grandma_id)
    st.markdown('<p class="sec-title" style="direction:rtl;">📅 הביקורים הקרובים שלך</p>',
                unsafe_allow_html=True)
    if not future_visits:
        st.info("אין ביקורים מתוכננים כרגע.")
    else:
        for v in future_visits:
            dt = _slot_dt(v["slot_start"])
            heb = to_heb_short(dt.date())
            with st.container():
                st.markdown(f"""
                <div class="visit-card">
                    <div class="vc-time">📅 {safe(dt.strftime('%d/%m/%Y'))} &nbsp; 🕐 {safe(dt.strftime('%H:%M'))}</div>
                    <div class="vc-heb">{safe(heb)}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"🗑️ ביטול ביקור זה", key=f"cancel_v_{v['id']}",
                             use_container_width=True):
                    st.session_state[f"confirm_cancel_visit_{v['id']}"] = True

                if st.session_state.get(f"confirm_cancel_visit_{v['id']}"):
                    with st.container(border=True):
                        st.warning("לבטל את הביקור הזה?")
                        cc1, cc2 = st.columns(2)
                        if cc1.button("כן, בטלי", type="primary",
                                      key=f"yes_cancel_{v['id']}", use_container_width=True):
                            grandma_visit_service.cancel_booked_visit(
                                supabase, v["id"], v.get("slot_id") or "",
                                descendant_id=desc_id or None,
                                secrets=st.secrets,
                                descendant_name=v.get("descendant_name") or name,
                                grandma_id=v.get("grandma_id") or grandma_id,
                                grandma_name=v.get("grandma_name") or grandma_name,
                                slot_start=v.get("slot_start") or "",
                                participant_count=int(v.get("participant_count") or 1),
                            )
                            st.session_state.pop(f"confirm_cancel_visit_{v['id']}", None)
                            st.rerun()
                        if cc2.button("השאירי", key=f"no_cancel_{v['id']}",
                                      use_container_width=True):
                            st.session_state.pop(f"confirm_cancel_visit_{v['id']}", None)
                            st.rerun()

    st.divider()
    if st.button("🌸 קביעת ביקור חדש", type="primary", use_container_width=True):
        st.session_state.grandma_screen = "schedule"
        st.rerun()
    if st.button("📸 גלריית תמונות", use_container_width=True):
        st.session_state.grandma_screen = "gallery"
        st.rerun()

    # ── Past visits eligible for notes (scoped to this grandma) ─
    past_visits = get_past_visits(supabase, desc_id, grandma_id=grandma_id)
    if past_visits:
        st.markdown('<p class="sec-title" style="direction:rtl; margin-top:20px;">📝 ביקורים שעברו — הוסיפי סיכום</p>',
                    unsafe_allow_html=True)
        for v in past_visits:
            dt = _slot_dt(v["slot_start"])
            label = dt.strftime("%d/%m/%Y %H:%M")
            status_label = "✅ הושלם" if v["status"] == "completed" else "ממתין לסיכום"
            st.markdown(f"""
            <div class="visit-card" style="border-color:#6b21a8;">
                <div class="vc-time">📅 {safe(label)}</div>
                <div class="vc-status">{status_label}</div>
            </div>
            """, unsafe_allow_html=True)
            btn_label = "✏️ ערכי סיכום" if v["status"] == "completed" else "📝 הוסיפי סיכום"
            if st.button(btn_label, key=f"notes_{v['id']}", use_container_width=True):
                st.session_state.grandma_note_visit = v
                st.session_state.grandma_screen = "notes"
                st.rerun()

    st.divider()
    if st.button("🚪 יציאה", use_container_width=True):
        _grandma_reset()
        st.rerun()


def grandma_schedule_view():
    visitor = st.session_state.get("grandma_visitor", {})
    name = visitor.get("name", "")

    # Guard: grandma must be selected
    grandma = st.session_state.get("grandma_selected_grandma")
    if not grandma:
        st.session_state.grandma_screen = "select_grandma"
        st.rerun()
        return

    grandma_id   = grandma["id"]
    grandma_name = grandma["name"]

    st.markdown(f"""
    <div class="hero-grandma">
        <h1>📅 בחירת מועד לביקור</h1>
        <p>ביקור אצל {safe(grandma_name)}</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Confirmation panel ─────────────────────────────────────
    if st.session_state.get("grandma_pending_slot"):
        ps = st.session_state.grandma_pending_slot
        dt = _slot_dt(ps["slot_start"])
        heb = to_heb_short(dt.date())
        remaining = ps.get("remaining_spots", ps.get("max_participants", 1))

        with st.container(border=True):
            st.markdown("""
            <style>
            /* Radio — tight, RTL, circle visually attached to its label */
            div[data-testid="stRadio"] [role="radiogroup"] { direction: rtl; gap: 4px; }
            div[data-testid="stRadio"] label {
                direction: rtl; display: flex; flex-direction: row;
                align-items: center; gap: 8px; text-align: right;
            }
            div[data-testid="stRadio"] label p { text-align: right; margin: 0; }
            /* Compact participant stepper value box (aligns with the +/- buttons) */
            .pc-value {
                text-align: center; font-size: 26px; font-weight: 800; color: #111827;
                line-height: 3.4rem; background: #fff7ed;
                border: 2px solid #fed7aa; border-radius: 16px;
            }
            </style>
            """, unsafe_allow_html=True)
            st.markdown('<p class="sec-title" style="direction:rtl;">✅ אישור ביקור</p>',
                        unsafe_allow_html=True)
            st.markdown(f"""
            <div style="direction:rtl; text-align:right; font-size:17px; line-height:2.2;">
                <strong>שם המבקר/ת:</strong> {safe(name)}<br>
                <strong>סבתא:</strong> 🌸 {safe(grandma_name)}<br>
                <strong>תאריך:</strong> 📅 {safe(dt.strftime('%d/%m/%Y'))}<br>
                <strong>שעה:</strong> 🕐 {safe(dt.strftime('%H:%M'))} — {safe((_slot_dt(ps['slot_end'])).strftime('%H:%M'))}<br>
                <span style="color:#92400e;">{safe(heb)}</span>
            </div>
            """, unsafe_allow_html=True)

            # Participant count — compact custom stepper. Replaces st.number_input,
            # whose +/- steppers render detached and spread out under direction:rtl.
            # Value persists across reruns in session_state (does not reset the flow).
            remaining = int(remaining)
            pc_key = f"grandma_pc_{ps['id']}"
            if pc_key not in st.session_state:
                st.session_state[pc_key] = 1
            # Clamp to current capacity (slot capacity can shift between reruns).
            st.session_state[pc_key] = max(1, min(st.session_state[pc_key], remaining))

            st.markdown(
                '<p style="direction:rtl;text-align:right;font-weight:700;margin-top:14px;">👥 כמה משתתפים תגיעו?</p>',
                unsafe_allow_html=True,
            )
            # Narrow, centered row: ➖ (left) — value — ➕ (right). Spacer columns keep it compact.
            _, c_minus, c_val, c_plus, _ = st.columns([3, 1, 1.3, 1, 3])
            if c_minus.button("➖", key=f"pc_minus_{ps['id']}", use_container_width=True,
                              disabled=st.session_state[pc_key] <= 1):
                st.session_state[pc_key] -= 1
                st.rerun()
            c_val.markdown(f"<div class='pc-value'>{st.session_state[pc_key]}</div>",
                           unsafe_allow_html=True)
            if c_plus.button("➕", key=f"pc_plus_{ps['id']}", use_container_width=True,
                             disabled=st.session_state[pc_key] >= remaining):
                st.session_state[pc_key] += 1
                st.rerun()
            participant_count = st.session_state[pc_key]
            if remaining > 1:
                st.markdown(
                    f'<p style="direction:rtl;text-align:right;font-size:13px;color:#6b7280;margin-top:4px;">ניתן לבחור עד {remaining} משתתפים</p>',
                    unsafe_allow_html=True,
                )

            allow_joiners = False
            if ps.get("allows_shared_visits"):
                st.markdown(
                    '<p style="direction:rtl;text-align:right;font-weight:700;margin-top:10px;">🤝 האם אפשר להצטרף אליכם לביקור?</p>',
                    unsafe_allow_html=True,
                )
                joiners_choice = st.radio(
                    "הצטרפות",
                    options=["כן, אפשר להצטרף אלינו", "לא, נעדיף ביקור פרטי"],
                    index=0,
                    label_visibility="collapsed",
                )
                allow_joiners = joiners_choice.startswith("כן")

            # c1=left=חזרה, c2=right=אישור — natural RTL order
            c1, c2 = st.columns(2)
            if c1.button("חזרה →", use_container_width=True):
                st.session_state.grandma_pending_slot = None
                st.rerun()
            if c2.button("✅ אישור", type="primary", use_container_width=True):
                result = grandma_visit_service.book_visit(
                    supabase, st.secrets,
                    slot_id=ps["id"],
                    slot_start=ps["slot_start"],
                    slot_end=ps["slot_end"],
                    descendant_id=visitor["id"],
                    descendant_name=name,
                    grandma_id=grandma_id,
                    grandma_name=grandma_name,
                    participant_count=int(participant_count),
                    allow_joiners=allow_joiners,
                )
                if not result["success"]:
                    err_msg = result.get("error_msg") or "⚠️ לא ניתן לקבוע את הביקור. אנא בחרי מועד אחר."
                    st.warning(err_msg)
                    st.session_state.grandma_pending_slot = None
                    st.rerun()
                else:
                    st.session_state.grandma_pending_slot = None
                    st.session_state.grandma_booking_success = True
                    st.session_state.grandma_screen = "dashboard"
                    st.rerun()
        return

    # ── Available slots ────────────────────────────────────────
    # Only slots assigned to this grandma; filter out private-blocked slots.
    slots = fetch_available_visit_slots(supabase, grandma_id=grandma_id)
    private_blocked = fetch_private_blocked_slot_ids(supabase, grandma_id)
    slots = [s for s in slots if s.get("grandma_id") and s["id"] not in private_blocked]

    if slots:
        # One query: booked participant totals for all visible slot IDs.
        slot_ids = [s["id"] for s in slots]
        booked_rows = (
            supabase.table("grandma_visits")
            .select("slot_id, participant_count")
            .eq("status", "scheduled")
            .in_("slot_id", slot_ids)
            .execute().data or []
        )
        booked_by_slot: dict = {}
        for row in booked_rows:
            sid = row["slot_id"]
            booked_by_slot[sid] = booked_by_slot.get(sid, 0) + (row.get("participant_count") or 1)

        def _remaining(s: dict) -> int:
            booked = booked_by_slot.get(s["id"], 0)
            # Non-shareable slots: any existing booking makes the slot unavailable.
            if not s.get("allows_shared_visits") and booked > 0:
                return 0
            return s["max_participants"] - booked

        # Drop slots that are actually full (capacity cache may lag slightly)
        slots = [s for s in slots if _remaining(s) > 0]

    if not slots:
        st.info("אין מועדים פנויים כרגע. כדאי לבדוק שוב מאוחר יותר.")
    else:
        st.markdown('<p class="sec-title" style="direction:rtl;">🗓️ מועדים פנויים</p>',
                    unsafe_allow_html=True)
        from collections import defaultdict
        by_date: dict = defaultdict(list)
        for s in slots:
            by_date[_slot_dt(s["slot_start"]).date()].append(s)

        for slot_date, day_slots in sorted(by_date.items()):
            heb = to_heb_short(slot_date)
            st.markdown(f"""
            <div class="date-card">
                <div class="gc">📅 {safe(slot_date.strftime('%d/%m/%Y'))}</div>
                <div class="hc">{safe(heb)}</div>
            </div>
            """, unsafe_allow_html=True)
            cols = st.columns(min(len(day_slots), 4))
            for idx, s in enumerate(day_slots):
                dt     = _slot_dt(s["slot_start"])
                dt_end = _slot_dt(s["slot_end"])
                rem    = _remaining(s)
                # Show remaining spots on the button only for shared slots with >1 capacity
                spots_suffix = f" ({rem} מקומות)" if s.get("allows_shared_visits") and s["max_participants"] > 1 else ""
                label = f"🕐 {dt.strftime('%H:%M')} - {dt_end.strftime('%H:%M')}{spots_suffix}"
                if cols[idx % 4].button(label, key=f"vs_{s['id']}"):
                    st.session_state.grandma_pending_slot = {**s, "remaining_spots": rem}
                    st.rerun()

    st.divider()
    if st.button("חזרה לדשבורד →", use_container_width=True):
        st.session_state.grandma_screen = "dashboard"
        st.rerun()


def grandma_notes_view():
    visit = st.session_state.get("grandma_note_visit", {})
    visit_id = visit.get("id", "")

    if not visit_id:
        st.session_state.grandma_screen = "dashboard"
        st.rerun()
        return

    # Guard: grandma must be selected
    grandma = st.session_state.get("grandma_selected_grandma")
    if not grandma:
        st.session_state.grandma_screen = "select_grandma"
        st.rerun()
        return

    grandma_name   = grandma["name"]
    dt_sched_start = _slot_dt(visit["slot_start"])
    dt_sched_end   = _slot_dt(visit["slot_end"])

    st.markdown(f"""
    <div class="hero-grandma">
        <h1>📝 סיכום הביקור</h1>
        <p>{safe(grandma_name)} · {safe(dt_sched_start.strftime('%d/%m/%Y'))}</p>
    </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        existing_notes = visit.get("notes") or ""
        existing_photo = visit.get("photo_url") or ""

        # ── Actual times ──────────────────────────────────────
        st.markdown('<p style="direction:rtl; font-weight:700;">🕐 זמן הביקור בפועל (אופציונלי)</p>',
                    unsafe_allow_html=True)
        tc1, tc2 = st.columns(2)
        actual_start_time = tc1.time_input(
            "שעת תחילה", value=dt_sched_start.time(), key="notes_actual_start",
        )
        actual_end_time = tc2.time_input(
            "שעת סיום", value=dt_sched_end.time(), key="notes_actual_end",
        )

        # ── Notes ─────────────────────────────────────────────
        st.markdown('<p style="direction:rtl; font-weight:700; margin-top:16px;">💬 איך היה הביקור?</p>',
                    unsafe_allow_html=True)
        notes = st.text_area("סיכום", value=existing_notes, height=150,
                             placeholder="ספרי לנו על הביקור...",
                             label_visibility="collapsed")

        # ── Photo ─────────────────────────────────────────────
        st.markdown('<p style="direction:rtl; font-weight:700; margin-top:16px;">📷 הוסיפי תמונה (אופציונלי)</p>',
                    unsafe_allow_html=True)
        if existing_photo:
            st.markdown(f'<a href="{safe(existing_photo)}" target="_blank">📎 תמונה קיימת</a>',
                        unsafe_allow_html=True)

        uploaded = st.file_uploader("תמונה", type=["jpg", "jpeg", "png", "gif", "webp"],
                                    label_visibility="collapsed")

        photo_url = existing_photo
        if uploaded is not None:
            if not uploaded.type.startswith("image/"):
                st.error("רק קבצי תמונה מותרים.")
                uploaded = None
            elif uploaded.size > 10 * 1024 * 1024:
                st.error("גודל הקובץ חייב להיות עד 10MB.")
                uploaded = None

        if st.button("💾 שמירה", type="primary", use_container_width=True):
            # Validate times before saving anything
            if actual_start_time >= actual_end_time:
                st.warning("⚠️ שעת התחילה חייבת להיות לפני שעת הסיום. אנא תקני את הזמנים.")
            else:
                # Build full TIMESTAMPTZ strings: scheduled date + actual clock time + IL timezone
                visit_date      = dt_sched_start.date()
                actual_start_iso = IL_TZ.localize(
                    datetime.combine(visit_date, actual_start_time)
                ).isoformat()
                actual_end_iso   = IL_TZ.localize(
                    datetime.combine(visit_date, actual_end_time)
                ).isoformat()

                if uploaded is not None:
                    with st.spinner("מעלה תמונה..."):
                        new_url = upload_visit_photo(
                            supabase, visit_id,
                            uploaded.read(), uploaded.name, uploaded.type,
                        )
                    if new_url:
                        photo_url = new_url
                    else:
                        st.warning("⚠️ לא הצלחנו להעלות את התמונה, הסיכום נשמר ללא תמונה.")

                update_visit_notes_photo(
                    supabase, visit_id,
                    notes=notes or None,
                    photo_url=photo_url or None,
                    actual_start=actual_start_iso,
                    actual_end=actual_end_iso,
                )
                st.success("💛 תודה! פרטי הביקור נשמרו.")
                st.session_state.grandma_note_visit = None
                st.session_state.grandma_screen = "dashboard"
                st.rerun()

    if st.button("חזרה לדשבורד →", use_container_width=True):
        st.session_state.grandma_note_visit = None
        st.session_state.grandma_screen = "dashboard"
        st.rerun()


def grandma_gallery_view():
    visitor  = st.session_state.get("grandma_visitor", {})
    grandma  = st.session_state.get("grandma_selected_grandma")
    if not grandma:
        st.session_state.grandma_screen = "select_grandma"
        st.rerun()
        return

    grandma_id   = grandma["id"]
    grandma_name = grandma["name"]
    desc_id      = visitor.get("id")

    st.markdown(f"""
    <div class="hero-grandma">
        <h1>📸 גלריית תמונות</h1>
        <p>זיכרונות מביקורים אצל {safe(grandma_name)}</p>
    </div>
    """, unsafe_allow_html=True)

    try:
        photos = get_visits_with_photos(supabase, grandma_id=grandma_id)
    except Exception:
        logger.exception("[GRANDMA] Failed to load gallery grandma=%s", grandma_id)
        st.error("שגיאה בטעינת הגלריה. אנא נסי שוב.")
        if st.button("חזרה לדשבורד →", use_container_width=True):
            st.session_state.grandma_screen = "dashboard"
            st.rerun()
        return

    if not photos:
        st.info("עדיין אין תמונות מביקורים קודמים.")
    else:
        cols = st.columns(3, gap="medium")
        for idx, v in enumerate(photos):
            with cols[idx % 3]:
                dt = _slot_dt(v["slot_start"])
                caption_parts = [dt.strftime("%d/%m/%Y")]
                visitor_name = v.get("descendant_name") or ""
                if visitor_name:
                    caption_parts.append(visitor_name)
                st.image(v["photo_url"], use_container_width=True)
                st.caption("  |  ".join(caption_parts))
                if v.get("notes"):
                    st.markdown(
                        f'<p style="direction:rtl;font-size:13px;color:#6b7280;">'
                        f'{safe(v["notes"][:120])}{"..." if len(v["notes"]) > 120 else ""}'
                        f'</p>',
                        unsafe_allow_html=True,
                    )

    st.divider()
    if st.button("חזרה לדשבורד →", use_container_width=True):
        st.session_state.grandma_screen = "dashboard"
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# GRANDMA ADMIN VIEW  (?mode=grandma_admin)
# ═══════════════════════════════════════════════════════════════
def _render_managers_admin(supabase, key_prefix: str):
    """
    Shared admin UI for the scoped manager model (managers + manager_assignments).

    Renders four sections:
      1. Add a manager (global person)
      2. Dry Run managers  — assignment to the dry_run scope
      3. Per-grandma managers — assignment per active grandma
      4. All managers list — global activate/deactivate

    key_prefix keeps Streamlit widget keys unique between the two admin views.
    """
    # ── 1. Add a manager (global person) ───────────────────────
    with st.container(border=True):
        st.markdown('<p class="sec-title" style="direction:rtl;">➕ הוספת מנהל/ת</p>',
                    unsafe_allow_html=True)
        mn1, mn2 = st.columns(2)
        new_name  = mn1.text_input("שם מנהל/ת", placeholder="שרה לוי",
                                   key=f"{key_prefix}_new_mgr_name")
        new_email = mn2.text_input("אימייל מנהל/ת", placeholder="sara@example.com",
                                   key=f"{key_prefix}_new_mgr_email")
        if st.button("➕ הוסף מנהל/ת", type="primary", use_container_width=True,
                     key=f"{key_prefix}_add_mgr"):
            norm_email = normalize_email(new_email)
            if not new_name.strip() or not valid_email(norm_email):
                st.error("נא למלא שם ואימייל תקין.")
            elif managers_repository.get_manager_by_email(supabase, norm_email):
                st.warning("מנהל/ת עם אימייל זה כבר קיים/ת.")
            else:
                managers_repository.create_manager(supabase, new_name, norm_email)
                st.success(f"✅ {safe(new_name)} נוסף/ה!")
                st.rerun()

    active_mgrs = managers_repository.list_managers(supabase, include_inactive=False)
    mgr_label = {m["id"]: f'{m["name"]} ({m["email"]})' for m in active_mgrs}
    mgr_ids = [m["id"] for m in active_mgrs]

    # ── 2. Dry Run managers ────────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="sec-title" style="direction:rtl;">🏢 מנהלי Dry Run</p>',
                    unsafe_allow_html=True)
        if not active_mgrs:
            st.info("הוסיפו מנהל/ת תחילה כדי לשייך ל-Dry Run.")
        else:
            dry_assignments = managers_repository.list_assignments(supabase, SERVICE_DRY_RUN)
            dry_by_mgr = {a["manager_id"]: a["id"] for a in dry_assignments}
            with st.form(f"{key_prefix}_dryrun_form"):
                sel = st.multiselect(
                    "מנהלים שיקבלו התראות Dry Run",
                    options=mgr_ids,
                    default=[mid for mid in dry_by_mgr if mid in mgr_ids],
                    format_func=lambda i: mgr_label.get(i, i),
                    key=f"{key_prefix}_dryrun_ms",
                )
                if st.form_submit_button("💾 שמירת מנהלי Dry Run", use_container_width=True):
                    _save_assignments(supabase, SERVICE_DRY_RUN, None,
                                      set(sel), dry_by_mgr)
                    st.success("✅ נשמר.")
                    st.rerun()

    # ── 3. Per-grandma managers ────────────────────────────────
    with st.container(border=True):
        st.markdown('<p class="sec-title" style="direction:rtl;">👵 מנהלים לכל סבתא</p>',
                    unsafe_allow_html=True)
        grandmas = get_active_grandmas(supabase)
        if not grandmas:
            st.info("אין סבתות פעילות.")
        elif not active_mgrs:
            st.info("הוסיפו מנהל/ת תחילה כדי לשייך לסבתא.")
        else:
            for g in grandmas:
                with st.expander(f"👵 {g['name']}"):
                    g_assignments = managers_repository.list_assignments(
                        supabase, SERVICE_GRANDMA, g["id"])
                    g_by_mgr = {a["manager_id"]: a["id"] for a in g_assignments}
                    with st.form(f"{key_prefix}_gr_form_{g['id']}"):
                        sel = st.multiselect(
                            "מנהלים שיקבלו התראות לסבתא זו",
                            options=mgr_ids,
                            default=[mid for mid in g_by_mgr if mid in mgr_ids],
                            format_func=lambda i: mgr_label.get(i, i),
                            key=f"{key_prefix}_gr_ms_{g['id']}",
                        )
                        if st.form_submit_button("💾 שמירה", use_container_width=True):
                            _save_assignments(supabase, SERVICE_GRANDMA, g["id"],
                                              set(sel), g_by_mgr)
                            st.success("✅ נשמר.")
                            st.rerun()

    # ── 4. All managers list (global activate / deactivate) ────
    with st.container(border=True):
        st.markdown('<p class="sec-title" style="direction:rtl;">📧 כל המנהלים</p>',
                    unsafe_allow_html=True)
        all_mgrs = managers_repository.list_managers(supabase, include_inactive=True)
        if not all_mgrs:
            st.info("אין מנהלים.")
        else:
            for m in all_mgrs:
                mc1, mc2, mc3, mc4 = st.columns([2.5, 3, 1.3, 0.8])
                mc1.markdown(f"**{safe(m['name'])}**")
                mc2.caption(m["email"])
                mc3.markdown("🟢 פעיל/ה" if m["is_active"] else "🔴 לא פעיל/ה")
                if m["is_active"]:
                    if mc4.button("🚫", key=f"{key_prefix}_deact_mgr_{m['id']}"):
                        managers_repository.set_manager_active(supabase, m["id"], False)
                        st.rerun()
                else:
                    if mc4.button("✅", key=f"{key_prefix}_react_mgr_{m['id']}"):
                        managers_repository.set_manager_active(supabase, m["id"], True)
                        st.rerun()


def _save_assignments(supabase, service_type, entity_id, selected_ids, current_by_mgr):
    """
    Reconcile a multiselect against existing assignments.
    selected_ids: set of manager_ids the admin wants assigned.
    current_by_mgr: {manager_id: assignment_id} of currently-active assignments.
    Adds missing ones (idempotent reactivate) and soft-removes deselected ones.
    """
    current_ids = set(current_by_mgr)
    for mgr_id in selected_ids - current_ids:
        managers_repository.add_assignment(supabase, mgr_id, service_type, entity_id)
    for mgr_id in current_ids - selected_ids:
        managers_repository.remove_assignment(supabase, current_by_mgr[mgr_id])


def grandma_admin_view():
    st.markdown("""
    <div class="hero-grandma">
        <h1>🌸 ניהול ביקורי סבתא</h1>
        <p>אזור מנהלים — מועדים, ביקורים, נכדים/ות</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Auth ───────────────────────────────────────────────────
    if not st.session_state.get("grandma_admin_auth"):
        admin_pwd = st.secrets.get("ADMIN_PASSWORD", "")
        if not admin_pwd:
            st.error("🔴 ADMIN_PASSWORD לא מוגדר ב-Secrets.")
            return
        with st.container(border=True):
            st.markdown('<p class="sec-title" style="direction:rtl;">🔐 כניסת מנהל/ת</p>',
                        unsafe_allow_html=True)
            pwd = st.text_input("סיסמה", type="password", label_visibility="collapsed",
                                placeholder="הכנס/י סיסמה")
            if st.button("כניסה", type="primary", use_container_width=True, key="ga_login"):
                if pwd == admin_pwd:
                    st.session_state.grandma_admin_auth = True
                    st.rerun()
                else:
                    st.error("סיסמה שגויה.")
        return

    # ── Tabs ───────────────────────────────────────────────────
    gtab1, gtab2, gtab3, gtab4, gtab5, gtab6 = st.tabs([
        "📅 מועדים", "📋 ביקורים", "👥 נכדים/ות", "📧 מנהלים", "👵 סבתות", "📸 גלריה"
    ])

    # ── TAB 1: Slots ──────────────────────────────────────────
    with gtab1:
        try:
            with st.container(border=True):
                st.markdown('<p class="sec-title" style="direction:rtl;">➕ הוספת מועד ביקור</p>',
                            unsafe_allow_html=True)
                # Grandma selector — required; no slot without a grandma
                slot_grandmas = get_active_grandmas(supabase)
                if not slot_grandmas:
                    st.warning("אין סבתות פעילות. הוסיפי סבתא בטאב 👵 סבתות תחילה.")
                else:
                    grandma_name_map = {g["name"]: g["id"] for g in slot_grandmas}
                    sel_gr_name = st.selectbox(
                        "סבתא", list(grandma_name_map.keys()), key="ga_slot_grandma",
                    )
                    sel_gr_id = grandma_name_map[sel_gr_name]

                    gc1, gc2 = st.columns(2)
                    today_il = now_il().date()
                    all_hours = [f"{h:02d}:00" for h in range(7, 22)]
                    # gc1 = left column (שעה), gc2 = right column (תאריך) — RTL natural order
                    g_time = gc1.selectbox("שעה", all_hours, key="ga_slot_time",
                                           format_func=slot_range_label)
                    g_date = gc2.date_input("תאריך", value=today_il,
                                            min_value=today_il, format="DD/MM/YYYY",
                                            key="ga_slot_date")

                    cp1, cp2 = st.columns(2)
                    max_parts = cp1.number_input(
                        "מקסימום משתתפים", min_value=1, max_value=50, value=1, step=1,
                        key="ga_slot_max",
                    )
                    allow_shared = cp2.checkbox(
                        "ביקור משותף (כמה משפחות)", value=False, key="ga_slot_shared",
                    )

                    if st.button("💾 הוסף מועד", type="primary", use_container_width=True,
                                 key="ga_add_slot"):
                        h_val, m_val = int(g_time[:2]), int(g_time[3:5])
                        slot_start_dt = IL_TZ.localize(
                            datetime(g_date.year, g_date.month, g_date.day, h_val, m_val)
                        )
                        slot_end_dt = slot_start_dt + timedelta(hours=1)
                        if add_visit_slot(
                            supabase, slot_start_dt, slot_end_dt,
                            grandma_id=sel_gr_id,
                            max_participants=int(max_parts),
                            allows_shared_visits=allow_shared,
                        ):
                            st.success("✅ מועד נוסף!")
                            st.rerun()
                        else:
                            st.warning("מועד זה כבר קיים לסבתא זו.")

            with st.container(border=True):
                st.markdown('<p class="sec-title" style="direction:rtl;">📋 כל המועדים</p>',
                            unsafe_allow_html=True)
                # Build grandma id→name map for the listing
                all_gr_map = {g["id"]: g["name"] for g in get_all_grandmas(supabase)}
                all_vslots = fetch_all_visit_slots(supabase)
                if not all_vslots:
                    st.info("אין מועדים.")
                else:
                    for s in all_vslots:
                        dt = _slot_dt(s["slot_start"])
                        avail = "🟢 פנוי" if s["is_available"] else "🔴 תפוס"
                        badge = "b-avail" if s["is_available"] else "b-booked"
                        gr_label = all_gr_map.get(s.get("grandma_id"), "—")
                        shared_label = " | משותף" if s.get("allows_shared_visits") else ""
                        sc1, sc2, sc3 = st.columns([3, 2, 0.7])
                        sc1.markdown(
                            f"**📅 {safe(dt.strftime('%d/%m/%Y %H:%M'))}** "
                            f"· {safe(gr_label)} "
                            f"· עד {s.get('max_participants', 1)}{safe(shared_label)}"
                        )
                        sc2.markdown(f'<span class="badge {badge}">{avail}</span>',
                                     unsafe_allow_html=True)
                        if sc3.button("🗑️", key=f"ga_del_vs_{s['id']}"):
                            delete_visit_slot(supabase, s["id"])
                            st.rerun()
        except Exception:
            logger.exception("[GRANDMA_ADMIN] slots tab error")
            st.error("שגיאה בטעינת המועדים.")

    # ── TAB 2: Bookings ───────────────────────────────────────
    with gtab2:
        try:
            st.markdown('<p class="sec-title" style="direction:rtl;">📋 כל הביקורים</p>',
                        unsafe_allow_html=True)
            all_gvisits = get_all_visits(supabase)
            if not all_gvisits:
                st.info("אין ביקורים רשומים.")
            else:
                status_map = {
                    "scheduled": "🟡 מתוכנן",
                    "completed": "✅ הושלם",
                    "cancelled": "❌ בוטל",
                }
                for v in all_gvisits:
                    dt = _slot_dt(v["slot_start"])
                    heb = to_heb_short(dt.date())
                    status_lbl = status_map.get(v["status"], v["status"])
                    st.markdown(f"""
                    <div class="bov-card">
                        <div class="slot-info">👤 {safe(v['descendant_name'])} &nbsp;|&nbsp; 📅 {safe(dt.strftime('%d/%m/%Y %H:%M'))}</div>
                        <div class="heb-info">{safe(heb)}</div>
                        <div class="user-info">{status_lbl}</div>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown(f"**סה״כ: {len(all_gvisits)} ביקורים**")
        except Exception:
            logger.exception("[GRANDMA_ADMIN] bookings tab error")
            st.error("שגיאה בטעינת הביקורים.")

    # ── TAB 3: Descendants ────────────────────────────────────
    with gtab3:
        try:
            with st.container(border=True):
                st.markdown('<p class="sec-title" style="direction:rtl;">➕ הוספת נכד/ה</p>',
                            unsafe_allow_html=True)
                dn1, dn2, dn3 = st.columns(3)
                new_desc_name  = dn1.text_input("שם מלא", placeholder="רחל כהן",
                                                key="ga_new_desc_name")
                new_desc_phone = dn2.text_input("טלפון", placeholder="050-...",
                                                key="ga_new_desc_phone")
                new_desc_email = dn3.text_input("אימייל (אופציונלי)", placeholder="rachel@...",
                                                key="ga_new_desc_email")
                if st.button("➕ הוסף נכד/ה", type="primary", use_container_width=True,
                             key="ga_add_desc"):
                    if not new_desc_name.strip():
                        st.error("נא להכניס שם.")
                    elif get_descendant_by_name(supabase, new_desc_name):
                        st.warning("נכד/ה עם שם זה כבר קיים/ת במערכת.")
                    else:
                        create_descendant(supabase, new_desc_name,
                                          new_desc_phone, new_desc_email)
                        st.success(f"✅ {safe(new_desc_name)} נוסף/ה!")
                        st.rerun()

            with st.container(border=True):
                st.markdown('<p class="sec-title" style="direction:rtl;">👥 רשימת נכדים/ות</p>',
                            unsafe_allow_html=True)
                all_desc = get_all_descendants(supabase)
                if not all_desc:
                    st.info("אין נכדים/ות רשומים/ות.")
                else:
                    for d in all_desc:
                        dc1, dc2, dc3, dc4 = st.columns([2.5, 2, 2, 0.8])
                        dc1.markdown(f"**{safe(d['name'])}**")
                        dc2.caption(d.get("phone") or "—")
                        active_badge = "🟢 פעיל/ה" if d["is_active"] else "🔴 לא פעיל/ה"
                        dc3.markdown(active_badge)
                        if d["is_active"]:
                            if dc4.button("🚫", key=f"ga_deact_{d['id']}"):
                                deactivate_descendant(supabase, d["id"])
                                st.rerun()
                        else:
                            if dc4.button("✅", key=f"ga_react_{d['id']}"):
                                reactivate_descendant(supabase, d["id"])
                                st.rerun()
        except Exception:
            logger.exception("[GRANDMA_ADMIN] descendants tab error")
            st.error("שגיאה בטעינת רשימת הנכדים.")

    # ── TAB 4: Managers ───────────────────────────────────────
    with gtab4:
        try:
            _render_managers_admin(supabase, key_prefix="ga")
        except Exception:
            logger.exception("[GRANDMA_ADMIN] managers tab error")
            st.error("שגיאה בטעינת המנהלים.")

    # ── TAB 5: Grandmas ───────────────────────────────────────
    with gtab5:
        try:
            with st.container(border=True):
                st.markdown('<p class="sec-title" style="direction:rtl;">➕ הוספת סבתא</p>',
                            unsafe_allow_html=True)
                gr1, gr2, gr3 = st.columns(3)
                new_gr_name  = gr1.text_input("שם", placeholder="סבתא שושי",
                                              key="ga_new_gr_name")
                new_gr_photo = gr2.text_input("כתובת תמונה (אופציונלי)",
                                              placeholder="https://...",
                                              key="ga_new_gr_photo")
                new_gr_desc  = gr3.text_input("תיאור (אופציונלי)",
                                              placeholder="סבתא שמחה...",
                                              key="ga_new_gr_desc")
                if st.button("➕ הוסף סבתא", type="primary", use_container_width=True,
                             key="ga_add_gr"):
                    if not new_gr_name.strip():
                        st.error("נא להכניס שם.")
                    else:
                        create_grandma(supabase, new_gr_name, new_gr_photo, new_gr_desc)
                        st.success(f"✅ {safe(new_gr_name)} נוספה!")
                        st.rerun()

            with st.container(border=True):
                st.markdown('<p class="sec-title" style="direction:rtl;">👵 רשימת סבתות</p>',
                            unsafe_allow_html=True)
                all_grandmas_list = get_all_grandmas(supabase)
                if not all_grandmas_list:
                    st.info("אין סבתות רשומות.")
                else:
                    for g in all_grandmas_list:
                        if g.get("photo_url"):
                            photo_html = (
                                f'<img src="{safe(g["photo_url"])}" style="'
                                f'width:48px;height:48px;border-radius:50%;'
                                f'object-fit:cover;vertical-align:middle;'
                                f'margin-left:10px;border:2px solid #fde68a;">'
                            )
                        else:
                            photo_html = '<span style="font-size:32px;vertical-align:middle;margin-left:10px;">👵</span>'
                        active_label = "🟢 פעיל/ה" if g["is_active"] else "🔴 לא פעיל/ה"
                        st.markdown(f"""
                        <div style="direction:rtl;margin-bottom:6px;">
                            {photo_html}
                            <b style="font-size:18px;">{safe(g["name"])}</b>
                            &nbsp;{active_label}
                        </div>
                        """, unsafe_allow_html=True)

                        # Inline photo URL + description edit
                        pc1, pc2, pc3 = st.columns([4, 4, 1])
                        edited_url = pc1.text_input(
                            "כתובת תמונה",
                            value=g.get("photo_url") or "",
                            key=f"ga_gr_url_{g['id']}",
                            placeholder="https://example.com/photo.jpg",
                            label_visibility="collapsed",
                        )
                        edited_desc = pc2.text_input(
                            "תיאור",
                            value=g.get("description") or "",
                            key=f"ga_gr_desc_{g['id']}",
                            placeholder="תיאור קצר...",
                            label_visibility="collapsed",
                        )
                        if pc3.button("💾", key=f"ga_gr_save_{g['id']}", help="שמור שינויים"):
                            update_grandma(supabase, g["id"], photo_url=edited_url,
                                           description=edited_desc)
                            st.success("✅ עודכן!")
                            st.rerun()

                        # Active toggle
                        if g["is_active"]:
                            if st.button("🚫 השבת", key=f"ga_gr_deact_{g['id']}",
                                         use_container_width=True):
                                set_grandma_active(supabase, g["id"], False)
                                st.rerun()
                        else:
                            if st.button("✅ הפעל", key=f"ga_gr_react_{g['id']}",
                                         use_container_width=True):
                                set_grandma_active(supabase, g["id"], True)
                                st.rerun()
                        st.divider()
        except Exception:
            logger.exception("[GRANDMA_ADMIN] grandmas tab error")
            st.error("שגיאה בטעינת הסבתות.")

    # ── TAB 6: Gallery ────────────────────────────────────────
    with gtab6:
        try:
            st.markdown('<p class="sec-title" style="direction:rtl;">📸 גלריית תמונות</p>',
                        unsafe_allow_html=True)

            # Grandma filter
            all_gmas = get_all_grandmas(supabase)
            gal_grandma_id = None
            if all_gmas:
                gal_options = {"כל הסבתות": None}
                gal_options.update({g["name"]: g["id"] for g in all_gmas})
                sel_gal = st.selectbox(
                    "סינון לפי סבתא",
                    list(gal_options.keys()),
                    key="ga_gal_filter",
                )
                gal_grandma_id = gal_options[sel_gal]

            photos = get_visits_with_photos(supabase, grandma_id=gal_grandma_id)

            if not photos:
                st.info("אין תמונות להצגה.")
            else:
                cols = st.columns(3, gap="medium")
                for idx, v in enumerate(photos):
                    with cols[idx % 3]:
                        dt = _slot_dt(v["slot_start"])
                        grandma_label = v.get("grandma_name") or ""
                        visitor_label = v.get("descendant_name") or ""
                        st.image(v["photo_url"], use_container_width=True)
                        meta_parts = [dt.strftime("%d/%m/%Y")]
                        if grandma_label:
                            meta_parts.append(grandma_label)
                        if visitor_label:
                            meta_parts.append(visitor_label)
                        st.caption("  |  ".join(meta_parts))
                        if v.get("notes"):
                            st.markdown(
                                f'<p style="direction:rtl;font-size:13px;color:#6b7280;">'
                                f'{safe(v["notes"][:150])}{"..." if len(v["notes"]) > 150 else ""}'
                                f'</p>',
                                unsafe_allow_html=True,
                            )
        except Exception:
            logger.exception("[GRANDMA_ADMIN] gallery tab error")
            st.error("שגיאה בטעינת הגלריה.")

    st.divider()
    if st.button("🚪 יציאה", use_container_width=True, key="ga_logout"):
        st.session_state.grandma_admin_auth = False
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

    # ── Auth ───────────────────────────────────────────────────
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

    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 Dry Run — מועדים",
        "👁️ Dry Run — הזמנות",
        "👥 Dry Run — משתמשים",
        "🌸 ביקורי סבתא",
    ])

    # ── TAB 1: Dry Run Slots ───────────────────────────────────
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
            if st.button("💾 שמור מועד", type="primary", use_container_width=True, key="dr_add_slot"):
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

    # ── TAB 2: Dry Run Booked overview ────────────────────────
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

    # ── TAB 3: Dry Run Users ──────────────────────────────────
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

    # ── TAB 4: Grandma Visits Admin ───────────────────────────
    with tab4:
        st.markdown('<p class="sec-title" style="direction:rtl;">🌸 ניהול ביקורי סבתא</p>',
                    unsafe_allow_html=True)
        gtab1, gtab2, gtab3, gtab4 = st.tabs([
            "📅 מועדים", "📋 ביקורים", "👥 נכדים/ות", "📧 מנהלים"
        ])

        # ── Grandma: Slots ────────────────────────────────────
        with gtab1:
            try:
                with st.container(border=True):
                    st.markdown('<p class="sec-title" style="direction:rtl;">➕ הוספת מועד ביקור</p>',
                                unsafe_allow_html=True)
                    gc1, gc2 = st.columns(2)
                    today_il = now_il().date()
                    g_date = gc1.date_input("תאריך", value=today_il,
                                            min_value=today_il, format="DD/MM/YYYY",
                                            key="g_slot_date")
                    all_hours = [f"{h:02d}:00" for h in range(7, 22)]
                    g_time = gc2.selectbox("שעה", all_hours, key="g_slot_time",
                                           format_func=slot_range_label)
                    if st.button("💾 הוסף מועד", type="primary", use_container_width=True,
                                 key="g_add_slot"):
                        h_val, m_val = int(g_time[:2]), int(g_time[3:5])
                        slot_start_dt = IL_TZ.localize(
                            datetime(g_date.year, g_date.month, g_date.day, h_val, m_val)
                        )
                        slot_end_dt = slot_start_dt + timedelta(hours=1)
                        if add_visit_slot(supabase, slot_start_dt, slot_end_dt):
                            st.success("✅ מועד נוסף!")
                            st.rerun()
                        else:
                            st.warning("מועד זה כבר קיים.")

                with st.container(border=True):
                    st.markdown('<p class="sec-title" style="direction:rtl;">📋 כל המועדים</p>',
                                unsafe_allow_html=True)
                    all_vslots = fetch_all_visit_slots(supabase)
                    if not all_vslots:
                        st.info("אין מועדים.")
                    else:
                        for s in all_vslots:
                            dt = _slot_dt(s["slot_start"])
                            avail = "🟢 פנוי" if s["is_available"] else "🔴 תפוס"
                            badge = "b-avail" if s["is_available"] else "b-booked"
                            sc1, sc2, sc3 = st.columns([3, 1.5, 0.7])
                            sc1.markdown(f"**📅 {safe(dt.strftime('%d/%m/%Y %H:%M'))}**")
                            sc2.markdown(f'<span class="badge {badge}">{avail}</span>',
                                         unsafe_allow_html=True)
                            if sc3.button("🗑️", key=f"del_vs_{s['id']}"):
                                delete_visit_slot(supabase, s["id"])
                                st.rerun()
            except Exception:
                logger.exception("[ADMIN] Grandma slots tab error")
                st.error("שגיאה בטעינת המועדים.")

        # ── Grandma: Bookings ─────────────────────────────────
        with gtab2:
            try:
                st.markdown('<p class="sec-title" style="direction:rtl;">📋 כל הביקורים</p>',
                            unsafe_allow_html=True)
                all_gvisits = get_all_visits(supabase)
                if not all_gvisits:
                    st.info("אין ביקורים רשומים.")
                else:
                    status_map = {
                        "scheduled": "🟡 מתוכנן",
                        "completed": "✅ הושלם",
                        "cancelled": "❌ בוטל",
                    }
                    for v in all_gvisits:
                        dt = _slot_dt(v["slot_start"])
                        heb = to_heb_short(dt.date())
                        status_lbl = status_map.get(v["status"], v["status"])
                        st.markdown(f"""
                        <div class="bov-card">
                            <div class="slot-info">👤 {safe(v['descendant_name'])} &nbsp;|&nbsp; 📅 {safe(dt.strftime('%d/%m/%Y %H:%M'))}</div>
                            <div class="heb-info">{safe(heb)}</div>
                            <div class="user-info">{status_lbl}</div>
                        </div>
                        """, unsafe_allow_html=True)
                    st.markdown(f"**סה״כ: {len(all_gvisits)} ביקורים**")
            except Exception:
                logger.exception("[ADMIN] Grandma bookings tab error")
                st.error("שגיאה בטעינת הביקורים.")

        # ── Grandma: Descendants ──────────────────────────────
        with gtab3:
            try:
                with st.container(border=True):
                    st.markdown('<p class="sec-title" style="direction:rtl;">➕ הוספת נכד/ה</p>',
                                unsafe_allow_html=True)
                    dn1, dn2, dn3 = st.columns(3)
                    new_desc_name  = dn1.text_input("שם מלא", placeholder="רחל כהן", key="new_desc_name")
                    new_desc_phone = dn2.text_input("טלפון", placeholder="050-...", key="new_desc_phone")
                    new_desc_email = dn3.text_input("אימייל (אופציונלי)", placeholder="rachel@...", key="new_desc_email")
                    if st.button("➕ הוסף נכד/ה", type="primary", use_container_width=True,
                                 key="add_desc"):
                        if not new_desc_name.strip():
                            st.error("נא להכניס שם.")
                        elif get_descendant_by_name(supabase, new_desc_name):
                            st.warning("נכד/ה עם שם זה כבר קיים/ת במערכת.")
                        else:
                            create_descendant(supabase, new_desc_name,
                                              new_desc_phone, new_desc_email)
                            st.success(f"✅ {safe(new_desc_name)} נוסף/ה!")
                            st.rerun()

                with st.container(border=True):
                    st.markdown('<p class="sec-title" style="direction:rtl;">👥 רשימת נכדים/ות</p>',
                                unsafe_allow_html=True)
                    all_desc = get_all_descendants(supabase)
                    if not all_desc:
                        st.info("אין נכדים/ות רשומים/ות.")
                    else:
                        for d in all_desc:
                            dc1, dc2, dc3, dc4 = st.columns([2.5, 2, 2, 0.8])
                            dc1.markdown(f"**{safe(d['name'])}**")
                            dc2.caption(d.get("phone") or "—")
                            active_badge = "🟢 פעיל/ה" if d["is_active"] else "🔴 לא פעיל/ה"
                            dc3.markdown(active_badge)
                            if d["is_active"]:
                                if dc4.button("🚫", key=f"deact_{d['id']}"):
                                    deactivate_descendant(supabase, d["id"])
                                    st.rerun()
                            else:
                                if dc4.button("✅", key=f"react_{d['id']}"):
                                    reactivate_descendant(supabase, d["id"])
                                    st.rerun()
            except Exception:
                logger.exception("[ADMIN] Grandma descendants tab error")
                st.error("שגיאה בטעינת רשימת הנכדים.")

        # ── Grandma: Managers ─────────────────────────────────
        with gtab4:
            try:
                _render_managers_admin(supabase, key_prefix="adm")
            except Exception:
                logger.exception("[ADMIN] Grandma managers tab error")
                st.error("שגיאה בטעינת המנהלים.")

    st.divider()
    if st.button("🚪 יציאה", use_container_width=True):
        st.session_state.admin_auth = False
        st.rerun()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    inject_css()
    mode = _get_mode()

    if mode == "admin":
        admin_view()
    elif mode == "grandma_admin":
        # Dedicated grandma visits manager entry point — ignores any stale active_module
        grandma_admin_view()
    elif mode in ("user", "dryrun"):
        # Direct link to Dry Run (?mode=user legacy, ?mode=dryrun new)
        user_view()
    elif mode == "grandma":
        # Direct shareable link — bypass module selection entirely
        st.session_state.active_module = "grandma"
        grandma_module()
    else:
        active = st.session_state.get("active_module")
        if active == "dryrun":
            user_view()
        elif active == "grandma":
            grandma_module()
        else:
            module_selection_view()

    now = now_il()
    st.markdown(
        f'<div class="footer">🕐 {now.strftime("%H:%M")} שעון ישראל'
        f' &nbsp;|&nbsp; <span dir="rtl">{safe(to_heb_short(now.date()))}</span></div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
