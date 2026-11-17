<div dir="rtl">

# صيّاد الوظائف (Job Hunter)

أداة بسيطة تبحث كل صباح عن **وظائف عن بُعد جديدة يمكنك التقديم عليها من العراق**، وترتّبها حسب ملاءمتها لك، وتجهّز ملفاً جاهزاً للصقه في Claude لكتابة رسائل التقديم (Cover Letters).

> ⚠️ الأداة **لا تقدّم على أي وظيفة تلقائياً**. أنت تراجع كل وظيفة وتقدّم بنفسك.

## كيف تعمل؟

1. **تجمع الوظائف** من أربعة مصادر عامة:
   - Remotive (واجهة API عامة)
   - Remote OK (واجهة API عامة)
   - Himalayas (واجهة API عامة، مع فلتر "مفتوحة للعراق")
   - We Work Remotely (خلاصات RSS)
2. **فلتر الأهلية (الأهم):** تبقي فقط الوظائف المفتوحة لـ Worldwide / Anywhere / MENA / الشرق الأوسط / EMEA / العراق.
   - تحذف الوظائف المقيّدة بدول معيّنة (US only، EU only، Egypt only، أو اسم مدينة/دولة في العنوان مثل "Sales Rep, Singapore").
   - تحذف الوظائف التي يقول وصفها مثلاً "must reside in the US" أو "US citizenship required".
   - إذا كان الموقع غير واضح تبقيها مع علامة **"check location"** (باللون الأصفر في Excel).
3. **إزالة التكرار:** تحفظ روابط الوظائف التي رأيتها في ملف `data/seen.sqlite`، فلا تظهر لك إلا الوظائف الجديدة.
4. **التقييم (بدون ذكاء اصطناعي):** درجة من 0 إلى 100 حسب كلمات مفتاحية موزونة في `keywords.yaml`:
   - كلمات ترفع الدرجة: n8n، Make، Zapier، AI agent، automation، Python، video editor، AI video، content producer، Arabic…
   - كلمات تخفضها: senior، 5+ years، US citizen، on-site، hybrid…
   - الكلمة الموجودة في **العنوان** تحسب 1.5 ضعف (وتظهر بعلامة `*` في عمود السبب).
   - سطر "السبب" يوضح الكلمات التي طابقت.

## الملفات الناتجة (في مجلد `output/`)

| الملف | المحتوى |
|---|---|
| `YYYY-MM-DD.xlsx` | جدول: title, company, location, salary, score, reason, link, letter (+ eligibility, source) |
| `YYYY-MM-DD.html` | ملخص مرتّب يُفتح في المتصفح (يُفتح تلقائياً عند التشغيل على جهازك) |
| `YYYY-MM-DD_for_claude.md` | أفضل 15 وظيفة مع أول 1200 حرف من كل وصف — انسخه والصقه في Claude |

### كتابة رسائل التقديم مع Claude
1. افتح ملف `..._for_claude.md` لليوم.
2. ضع ملخص سيرتك الذاتية مكان السطر `My profile`.
3. الصق الملف كاملاً في محادثة Claude واطلب الرسائل.
4. الصق كل رسالة في عمود `letter` في ملف Excel إن أردت تتبّعها.

## التشغيل التلقائي على GitHub Actions (الطريقة الأساسية)

- الملف `.github/workflows/daily.yml` يشغّل الأداة **كل يوم الساعة 05:00 UTC = 8:00 صباحاً بتوقيت أربيل**.
- بعد كل تشغيل يحفظ (commit) ملفات اليوم في مجلد `output/` وقاعدة `data/seen.sqlite` داخل المستودع.
- **للتشغيل يدوياً:** في صفحة المستودع على GitHub ← تبويب **Actions** ← **Daily job hunt** ← زر **Run workflow**.
- **لقراءة النتائج:** افتح مجلد `output/` في المستودع. ملف `.md` يُعرض مباشرة على GitHub. لملف HTML نزّله وافتحه، ولملف Excel اضغط Download.
- ملاحظة: GitHub قد يؤخر التشغيل المجدول بضع دقائق أحياناً.

## التشغيل على جهازك (اختياري)

تحتاج Python 3.10 أو أحدث. من PowerShell داخل المجلد:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

السكربت يسحب آخر نسخة من GitHub أولاً (حتى لا تتكرر الوظائف)، ينشئ بيئة `.venv`، يثبت المتطلبات، ثم يشغّل الأداة ويفتح ملف HTML.

خيارات إضافية:

```powershell
.\run.ps1 --no-open     # لا تفتح المتصفح
.\run.ps1 --dry-run     # تجربة بدون تسجيل الوظائف كـ"مشاهدة"
```

بعد التشغيل المحلي، ارفع التغييرات (`git add output data; git commit -m "local run"; git push`) حتى يعرف GitHub بالوظائف التي رأيتها.

## تخصيص الكلمات المفتاحية

عدّل `keywords.yaml`:
- `search_terms`: كلمات البحث المرسلة لـ Himalayas.
- `remotive_searches`: كلمات البحث في Remotive (**4 كحد أقصى** — شروط Remotive تطلب 4 طلبات يومياً كحد أقصى).
- `positive` / `negative`: القواعد وأوزانها. `term` = عبارة عادية، `regex` = تعبير نمطي.
- `min_score`: الوظائف تحت هذه الدرجة تُتجاهل.
- `max_age_days`: تجاهل الإعلانات الأقدم من هذا العدد من الأيام.

## الاختبارات

```powershell
python -m pytest -q
```

تختبر فلتر الأهلية (Worldwide / US-only / القوائم / العبارات في الوصف…) والتقييم. تعمل أيضاً تلقائياً قبل كل تشغيل على GitHub.

## شروط المصادر (تم التحقق منها في 2026-11-17)

| المصدر | ما يسمح به | ما نلتزم به |
|---|---|---|
| Remotive | API عام | 4 طلبات يومياً كحد أقصى، رابط للوظيفة على Remotive وذكر المصدر، عدم إرسال الوظائف لمواقع وظائف أخرى |
| Remote OK | API عام | رابط للوظيفة على Remote OK وذكر المصدر |
| Himalayas | API عام | رابط التقديم كما هو بدون تعديل، ذكر Himalayas كمصدر، طلب واحد لكل كلمة يومياً |
| We Work Remotely | خلاصات RSS عامة | شروط الموقع لا تمنع الوصول الآلي؛ 6 خلاصات مرة يومياً |

كل ملف ناتج يذكر مصدر كل وظيفة مع رابطها الأصلي. الأداة للاستخدام الشخصي فقط.

## هيكل المشروع

```
main.py                 نقطة التشغيل
keywords.yaml           الكلمات والأوزان والإعدادات
jobhunter/sources.py    جلب الوظائف من المصادر الأربعة
jobhunter/eligibility.py فلتر الأهلية للعراق
jobhunter/scoring.py    التقييم من 0 إلى 100
jobhunter/store.py      قاعدة SQLite للوظائف المشاهدة
jobhunter/output.py     Excel + HTML + ملف Claude
tests/                  الاختبارات
run.ps1                 تشغيل محلي على Windows
.github/workflows/      التشغيل اليومي على GitHub
```

</div>
