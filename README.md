

# 📅 Dry Run Scheduler

מערכת לניהול ותזמון פגישות "Dry Run" המשלבת לוח שנה גרגוריאני ועברי מלא. המערכת מאפשרת למנהל להגדיר חלונות זמן, ולמשתמשים מורשים להשתבץ לסלוט אחד בלבד לאחר זיהוי באימייל.

## 🛠 דרישות קדם (Prerequisites)

* **Python 3.9+** מותקן על המחשב.
* חשבון ב-[Supabase](https://supabase.com/).
* חשבון ב-GitHub (לצורך העלאה ופריסה ב-Streamlit Cloud).

---

## 💾 שלב 1: הגדרת בסיס הנתונים (Supabase)

היכנסי ל-SQL Editor בלוח הבקרה של Supabase והריצי את השאילתות הבאות ליצירת הטבלאות:

```sql
-- יצירת טבלת משתמשים
CREATE TABLE users (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT
);

-- יצירת טבלת סלוטים
CREATE TABLE slots (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    time_slot TEXT NOT NULL,
    is_booked BOOLEAN DEFAULT FALSE,
    booked_by_email TEXT REFERENCES users(email) ON DELETE SET NULL,
    UNIQUE(date, time_slot)
);

```

---

## ⚙️ שלב 2: הגדרת קובץ ה-Secrets

כדי שהאפליקציה תוכל לתקשר עם בסיס הנתונים, עלייך ליצור קובץ הגדרות מקומי.

1. בתוך תיקיית הפרויקט, צרי תיקייה בשם `.streamlit`.
2. בתוכה, צרי קובץ בשם `secrets.toml`.
3. הדביקי בתוכו את התוכן הבא (עם הפרטים שלך):

```toml
SUPABASE_URL = "your_project_url_here"
SUPABASE_KEY = "your_anon_key_here"
ADMIN_PASSWORD = "your_chosen_admin_password"

```

> **⚠️ חשוב מאוד:** ודאי שקובץ זה מופיע ב-`.gitignore` שלך כדי שלא יעלה ל-GitHub!

---

## 🚀 שלב 3: התקנה והרצה מקומית

פתחי את הטרמינל בתיקיית הפרויקט והריצי את הפקודות הבאות:

1. **יצירת סביבה וירטואלית (מומלץ):**
```bash
python -m venv .venv
source .venv/bin/activate  # ב-Windows השתמשי ב: .venv\Scripts\activate

```


2. **התקנת הספריות הדרושות:**

```bash
   pip install streamlit supabase pyluach pandas pytz

```

3. **הרצת האפליקציה:**
```bash
streamlit run app.py

```



---

## 🌐 שלב 4: פריסה לענן (Streamlit Cloud)

1. העלי את הקוד ל-GitHub (ללא קובץ ה-`secrets.toml`).
2. ב-Streamlit Cloud, צרי אפליקציה חדשה המחוברת לריפו שלך.
3. ב-**Advanced Settings**, העתיקי את תוכן קובץ ה-`secrets.toml` לתיבת ה-**Secrets**.
4. לחצי על **Deploy**.

---

## 📂 מבנה הפרויקט

```text
scheduling_app/
├── .streamlit/
│   └── secrets.toml      # הגדרות סודיות (לא עולה ל-Git)
├── app.py                # הקוד הראשי של האפליקציה
├── requirements.txt      # רשימת הספריות להתקנה
└── README.md             # קובץ זה

```

---

### 💡 טיפ לניהול שוטף

כדי להוסיף חברות למערכת, היכנסי לקישור האפליקציה בתוספת `?mode=admin` (למשל: `myapp.streamlit.app/?mode=admin`). שם תוכלו להוסיף את המיילים שלהן לטבלת המשתמשים כדי לאפשר להן להזמין סלוטים.

```

```