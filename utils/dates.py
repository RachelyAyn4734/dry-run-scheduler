from datetime import date, datetime, timedelta
from pyluach import dates as heb_dates, gematria

_HEB_MONTHS = {
    1: "ניסן", 2: "אייר", 3: "סיון", 4: "תמוז", 5: "אב", 6: "אלול",
    7: "תשרי", 8: "חשון", 9: "כסלו", 10: "טבת", 11: "שבט", 12: "אדר",
    13: "אדר ב׳",
}


def to_heb(d: date) -> str:
    hd = heb_dates.HebrewDate.from_pydate(d)
    day_s = gematria._num_to_str(hd.day)
    mon_s = _HEB_MONTHS.get(hd.month, str(hd.month))
    yr_s = "ה׳" + gematria._num_to_str(hd.year % 1000)
    return f"{day_s} ב{mon_s} {yr_s}"


def to_heb_short(d: date) -> str:
    hd = heb_dates.HebrewDate.from_pydate(d)
    return (
        f"{gematria._num_to_str(hd.day)} "
        f"{_HEB_MONTHS.get(hd.month, '')} "
        f"{gematria._num_to_str(hd.year % 1000)}"
    )


def slot_range_label(start_time: str) -> str:
    """Convert 'HH:MM' or 'HH:MM:SS' to 'HH:MM - HH:MM' range string."""
    t = start_time[:5]
    start_dt = datetime.strptime(t, "%H:%M")
    end_dt = start_dt + timedelta(hours=1)
    return f"{t} - {end_dt.strftime('%H:%M')}"
