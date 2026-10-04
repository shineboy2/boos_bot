# گزارش کالبدشکافی رپوهای Open Source مرتبط با بورس ایران

در این بررسی، رپوهایی که در مراحل قبلی نام برده شدند را در سه سطح بررسی کردم:

1. **معماری و ساختار پروژه**
2. **نحوه دسترسی و پردازش داده‌های TSETMC**
3. **ارزش واقعی برای استفاده در یک سیستم حرفه‌ای Market Data / Analytics**

یک نکته مهم: «کالبدشکافی عمیق» را بر اساس source tree، فایل‌های اصلی، مدل‌های داده، APIها، README، release/commit history، issueها و کدهای قابل مشاهده انجام دادم. به‌دلیل محدودیت دسترسی محیط فعلی به clone کامل GitHub، برای بعضی رپوها نمی‌توانم ادعا کنم تک‌تک خطوط کل repository را اجرا و تست کرده‌ام؛ بنابراین هرجا نتیجه مستقیماً از کد مشاهده‌شده باشد آن را از نتیجه معماری/تحلیلی جدا کرده‌ام.

---

## فهرست رپوهای بررسی‌شده

| #  | Repository                                    | نقش اصلی                            |
| -- | --------------------------------------------- | ----------------------------------- |
| 1  | `Glyphack/pytse-client`                       | Python Market Data Client           |
| 2  | `ghodsizadeh/tehran-stocks`                   | Historical Data + Database          |
| 3  | `mahs4d/tsetmc-api`                           | TSETMC API Client                   |
| 4  | `5j9/tsetmc`                                  | Async + Polars Market Data          |
| 5  | `alised/tse-index`                            | Historical Data + Index             |
| 6  | `m-ahmadi/tse-client`                         | JS/Node Universal Client + Intraday |
| 7  | `sm-sokout/tse-option`                        | Options Analytics                   |
| 8  | `Ali-Marandi/finsight-pro`                    | Financial Analysis Platform         |
| 9  | `Mmadrb/tehran-stock-exchange-buysell-engine` | Signal/Screener Engine              |
| 10 | `BabakEslami/tse-market-data`                 | TSETMC API Reverse Documentation    |

همچنین در خلال بررسی مشخص شد که اکوسیستم فعلی TSETMC پروژه‌های دیگری مثل `shahradelahi/tsetmc-client`، `mshojaei77/pytsetmc-api` و پروژه‌های جدیدتر را نیز شامل می‌شود؛ اما این گزارش روی **تمام رپوهایی که قبلاً نام برده بودیم** متمرکز است. GitHub در حال حاضر برای topic `tsetmc` حدود ۳۶ رپو نشان می‌دهد. ([GitHub][1])

---

# بخش اول — مهم‌ترین یافته

اگر بخواهم کل تحقیق را در یک جمله خلاصه کنم:

> **هیچ‌کدام از این رپوها به‌تنهایی یک Market Data Platform حرفه‌ای برای بورس ایران نیستند؛ اما کنار هم تقریباً تمام قطعات لازم برای طراحی چنین پلتفرمی را نشان می‌دهند.**

معماری‌ای که از ترکیب این پروژه‌ها به دست می‌آید تقریباً این است:

```text
                    TSETMC / TSE
                         │
             ┌───────────┴───────────┐
             │                       │
       cdn.tsetmc.com          webgw.tse.ir
             │                       │
             └───────────┬───────────┘
                         │
                  Data Acquisition
                         │
               ┌─────────┴─────────┐
               │                   │
           Reference            Market Data
             Data                   │
               │          ┌────────┼────────┐
               │          │        │        │
               │       Daily     Intraday  OrderBook
               │          │        │        │
               └──────────┴────────┴────────┘
                         │
                    Normalization
                         │
                    Data Storage
                         │
          ┌──────────────┼──────────────┐
          │              │              │
      Historical     Fundamentals    Market State
          │              │              │
          └──────────────┼──────────────┘
                         │
                 Analytics Engine
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    Technical        Fundamental       Options
        │                │                │
        └────────────────┼────────────────┘
                         │
                  Strategy / Screener
                         │
                 Backtesting Engine
                         │
                  API / Dashboard
                         │
                       AI/LLM
```

نکته بسیار مهم این است که `tse-market-data` نشان می‌دهد امروز دیگر نباید معماری را صرفاً حول endpointهای قدیمی `tsetmc.com` طراحی کرد. این پروژه دو gateway مهم را از هم جدا می‌کند: `cdn.tsetmc.com` با کلید `InsCode` و `webgw.tse.ir` با کلید ISIN؛ ضمن اینکه قابلیت‌های آن‌ها کاملاً یکسان نیست. ([GitHub][2])

---

# 1. Glyphack/pytse-client

[Glyphack/pytse-client](https://github.com/Glyphack/pytse-client?utm_source=chatgpt.com)

## مشخصات

* Python
* 452 commit
* 82 fork
* حدود 38 issue
* GPLv3
* نسخه فعلی repository: `0.19.1`
* dependencyهای اصلی:

  * pandas
  * requests
  * aiohttp
  * BeautifulSoup
  * lxml
  * tenacity
  * jdatetime

([GitHub][3])

### معماری

ساختار کلی:

```text
pytse_client/
│
├── ticker/
│   ├── ticker.py
│   ├── api_extractors/
│   └── ...
│
├── download/
├── proxy/
├── symbols_data
├── utils/
└── settings/config
```

مرکز معماری `Ticker` است.

کلاس `Ticker` در فایل اصلی بیش از ۸۰۰ خط دارد و در یک abstraction نسبتاً بزرگ اطلاعات مختلف نماد را جمع می‌کند. ([GitHub][4])

مدل `RealtimeTickerInfo` نیز داده‌هایی مثل:

* last
* close
* volume
* value
* order book
* حقیقی/حقوقی
* NAV
* market cap

را کنار هم قرار می‌دهد. ([GitHub][4])

## قابلیت‌ها

این repo از نظر breadth بسیار قوی است:

* historical prices
* adjusted/unadjusted
* realtime
* index history
* حقیقی/حقوقی
* EPS
* P/E
* base volume
* shareholders
* filter-writing statistics
* trade details
* orderbook

([GitHub][3])

## نقاط قوت

### 1. پوشش وسیع

برای یک کتابخانه Python ساده، دامنه داده بسیار خوب است.

### 2. retry

وجود `tenacity` نشان می‌دهد مسئله reliability هنگام ارتباط با TSETMC در معماری دیده شده است. ([GitHub][4])

### 3. تفکیک proxy از domain object

این قسمت ایده خوبی است:

```text
Ticker
  ↓
proxy
  ↓
TSETMC
```

یعنی consumer الزاماً مجبور نیست HTTP response خام را بشناسد.

### 4. normalization

تبدیل نام‌های فارسی و عربی در utilityها نیز دیده می‌شود.

---

## ضعف معماری

مشکل اصلی این است که `Ticker` بیش از حد بزرگ شده.

عملاً:

```text
Ticker
 ├── Identity
 ├── Price
 ├── OrderBook
 ├── Shareholders
 ├── Fundamental
 ├── ClientType
 ├── History
 ├── NAV
 └── ...
```

این برای یک library کاربردی خوب است، ولی برای platform بزرگ‌تر باعث coupling می‌شود.

### مشکل دوم: data access و domain abstraction کاملاً جدا نشده‌اند.

### مشکل سوم: وابستگی شدید به endpointهای TSETMC

Issueهای فعلی repository شامل گزارش دریافت اطلاعات نادرست از بورس است. ([GitHub][5])

### مشکل چهارم: license

GPLv3 است. این موضوع برای reuse در یک محصول proprietary بسیار مهم است. ([GitHub][6])

---

## نتیجه

**برای مطالعه:** بسیار ارزشمند.

**برای reuse مستقیم:** با احتیاط.

**برای architecture inspiration:** بسیار ارزشمند.

**برای یک سیستم تجاری proprietary:** license باید قبل از هر reuse جدی بررسی شود.

---

# 2. ghodsizadeh/tehran-stocks

[ghodsizadeh/tehran-stocks](https://github.com/ghodsizadeh/tehran-stocks?utm_source=chatgpt.com)

این پروژه رویکرد متفاوتی دارد.

اگر `pytse-client` را یک **API Client** بدانیم، `tehran-stocks` بیشتر یک **Local Market Dataset** است.

ساختار:

```text
TSETMC
   ↓
Downloader
   ↓
SQLite
   ↓
SQLAlchemy
   ↓
Stocks
   ↓
Pandas
```

ویژگی‌های اصلی:

* download all stocks
* group download
* offline access
* SQLite
* SQLAlchemy
* Pandas
* CSV
* Excel
* Stata
* CLI

([GitHub][7])

## معماری

نکته جالب:

```python
Stocks.query.filter_by(...)
```

یعنی data access به ORM منتقل شده است.

این از نظر platform architecture ایده مهمی است:

```text
Remote API
     ↓
Persistence
     ↓
ORM
     ↓
Query Layer
```

نه:

```text
Remote API
     ↓
Pandas
     ↓
Everything
```

## نقاط قوت

### Local-first

بعد از initial download امکان استفاده offline دارد.

### Incremental update

به جای اینکه همیشه کل تاریخچه را دانلود کند، امکان update دارد.

### SQLAlchemy

برای پروژه‌ای که بعدها بخواهد SQLite را با PostgreSQL عوض کند، این abstraction مفید است.

### CLI

نشان می‌دهد library صرفاً برای notebook طراحی نشده.

---

## ضعف‌ها

بزرگ‌ترین مشکل، سن پروژه و dependency آن به endpointهای قدیمی‌تر است.

Issueهای باز شامل:

* عدم دریافت قیمت
* خرابی API
* خطا در dataframe
* مشکلات نصب

هستند. ([GitHub][8])

یعنی architecture ایده خوبی دارد، اما **data acquisition layer آن نقطه ضعف است.**

---

## نتیجه

این repo برای یادگیری این بخش بسیار ارزشمند است:

> **چگونه Market Data را از یک API crawler به Dataset قابل query تبدیل کنیم.**

ولی من crawler آن را برای سیستم جدید استفاده نمی‌کنم.

---

# 3. mahs4d/tsetmc-api

[mahs4d/tsetmc-api](https://github.com/mahs4d/tsetmc-api?utm_source=chatgpt.com)

این یکی از تمیزترین معماری‌های این مجموعه را دارد.

Repository به componentهای مشخص تقسیم شده:

```text
tsetmc_api
│
├── symbol
├── market_watch
├── day_details
├── market_map
├── group
└── utils
```

([GitHub][9])

## نکته بسیار مهم: Domain decomposition

مثلاً `DayDetails`:

```text
DayDetails
 ├── Price Overview
 ├── Price Data
 ├── OrderBook
 ├── Trades
 ├── Thresholds
 ├── Shareholders
 └── Traders Type
```

([GitHub][10])

این decomposition بسیار منطقی است.

---

## Data model

برای خروجی‌ها از Pydantic استفاده شده.

مثلاً `WatchPriceDataRow` اطلاعات:

* symbol_id
* isin
* prices
* volume
* value
* EPS
* base volume
* visit count
* flow
* group
* thresholds
* orderbook

را مدل می‌کند. ([GitHub][11])

این دقیقاً چیزی است که برای API مدرن لازم داریم:

```text
Raw JSON
    ↓
Parser
    ↓
Typed DTO
    ↓
Consumer
```

---

## نقطه ضعف مهم

در کد فعلی، data layer مستقیماً از `requests.get()` استفاده می‌کند و endpointها در core functionها قرار دارند. برای نمونه `day_details/_core.py` مستقیماً URLهای TSETMC را صدا می‌زند. ([GitHub][12])

این یعنی:

```text
Domain
  ↓
Core
  ↓
requests
  ↓
TSETMC
```

و نه:

```text
Domain
  ↓
Repository Interface
  ↓
HTTP Client
  ↓
Provider
```

برای library کوچک قابل قبول است؛ برای platform بزرگ بهتر است جدا شود.

---

## Async

این پروژه async دارد، ولی نکته مهم:

> async واقعی نیست.

خود README توضیح می‌دهد که متدهای async از synchronous functionها در executor استفاده می‌کنند. ([GitHub][9])

یعنی:

```text
async API
   ↓
Thread Pool
   ↓
requests
```

نه:

```text
asyncio
   ↓
aiohttp/httpx async
   ↓
network
```

پس اگر throughput بالا بخواهیم، این architecture محدودیت دارد.

---

## نتیجه

از نظر:

**Domain modeling → بسیار خوب**

**Data modeling → بسیار خوب**

**Production ingestion → متوسط**

**معماری قابل مطالعه → بسیار خوب**

---

# 4. 5j9/tsetmc

[5j9/tsetmc](https://github.com/5j9/tsetmc?utm_source=chatgpt.com)

این پروژه از نظر تکنولوژی مدرن‌ترین data client این مجموعه است.

مشخصات:

* Python 3.13+
* asyncio
* Polars
* LazyFrame
* 960 commit
* GPL-3.0
* MarketWatch streaming/event model

([GitHub][13])

## معماری

```text
             TSETMC
                │
        Async HTTP Layer
                │
       ┌────────┴────────┐
       │                 │
   Instrument        MarketWatch
       │                 │
       └────────┬────────┘
                │
             Polars
                │
          LazyFrame
```

این تغییر بسیار مهم است.

در `pytse-client`:

```text
TSETMC → requests → Pandas
```

در این پروژه:

```text
TSETMC → async → Polars
```

---

## Instrument abstraction

```python
Instrument.from_search(...)
```

و سپس:

```python
await inst.info()
await inst.closing_price_info()
await inst.daily_closing_price()
```

این API بسیار تمیزتر از raw endpoint access است. ([GitHub][13])

---

## MarketWatch

یکی از بهترین بخش‌های پروژه:

```python
MarketWatch()
```

و سپس event-driven update.

```text
MarketWatch
      │
      ├── start()
      │
      └── update_event
               │
               ▼
          LazyFrame
```

([GitHub][13])

این architecture برای ساخت:

* dashboard
* realtime screener
* alert engine
* signal engine

خیلی مناسب‌تر از polling ساده است.

---

## Dataset

پروژه یک dataset آفلاین برای اطلاعات پایه instruments دارد که باید periodically update شود. ([GitHub][13])

این ایده مهم است:

```text
Reference Data
     ↓
Local Dataset
     ↓
Runtime Lookup
```

به‌جای اینکه برای هر request دوباره symbol discovery انجام شود.

---

## مشکل

نیاز به Python 3.13 دارد. ([GitHub][13])

برای production سازمانی، این الزام می‌تواند constraint ایجاد کند.

دوم:

GPL-3.0 است.

سوم:

این پروژه هنوز **Data Platform نیست**؛ یک client بسیار خوب است.

---

## نتیجه

از بین تمام data clientها:

> **از نظر معماری مدرن ingestion، این پروژه یکی از مهم‌ترین پروژه‌هایی است که باید مطالعه شود.**

---

# 5. alised/tse-index

[alised/tse-index](https://github.com/alised/tse-index?utm_source=chatgpt.com)

پروژه کوچک‌تر ولی از نظر historical-data architecture جالب است.

قابلیت‌ها:

* historical price
* index history
* instrument list
* search
* automatic merging old data
* adjustment
* daily/weekly/monthly

([GitHub][14])

## معماری

تقریباً:

```text
TSEClient
    ↓
Instrument Registry
    ↓
History Fetcher
    ↓
Pandas
    ↓
Adjustment
    ↓
Resampling
```

---

## نکته بسیار خوب

Batching دارد:

```text
chunksize = 50
```

و برای history چند instrument را در chunk دریافت می‌کند. ([GitHub][15])

این برای TSETMC بسیار مهم است.

---

## Incremental History

اگر قبلاً داده داشته باشد:

```text
Existing last date
       ↓
TSETMC
       ↓
Only missing data
```

این architecture برای production ingestion ضروری است.

---

## Adjustment

منطق adjustment در خود پروژه پیاده‌سازی شده و از نسبت‌های `AdjClose` و `Yesterday` برای تشخیص تغییرات و اعمال adjustment استفاده می‌کند. ([GitHub][15])

اما این قسمت را برای production **حتماً باید مستقل validate کرد**؛ چون corporate-action adjustment یکی از حساس‌ترین قسمت‌های Market Data است.

---

## مشکل

کد `reader` نسبتاً monolithic است؛ data acquisition، caching، transformation و resampling در یک abstraction بزرگ جمع شده‌اند.

همچنین GPL-3.0 است. ([GitHub][14])

---

# 6. m-ahmadi/tse-client

[m-ahmadi/tse-client](https://github.com/m-ahmadi/tse-client?utm_source=chatgpt.com)

این پروژه JavaScript است اما ارزش معماری آن زیاد است.

مشخصات:

* Browser
* Node
* CLI
* 989 commit
* caching
* crawler
* compression
* retry
* intraday
* adjustment

([GitHub][16])

## نکته بسیار مهم

این پروژه فقط:

```text
fetch price
```

نیست.

Intraday crawler دارد:

```text
Symbol
  ↓
Date Range
  ↓
Chunks
  ↓
Requests
  ↓
Retry
  ↓
Compression
  ↓
Merge
  ↓
Cache
```

و تنظیماتی برای:

* chunk delay
* max wait
* retry count
* retry delay
* servers

دارد. ([GitHub][16])

---

## Adjustment

حتی manual adjustment را هم در اختیار کاربر قرار داده است.

این نشان می‌دهد نویسنده متوجه شده:

> Adjustment یک transformation جدا از raw price data است.

این ایده را باید در معماری خودمان حفظ کنیم.

---

## نقطه قوت خاص

Universal architecture:

```text
                Core
                 │
       ┌─────────┼─────────┐
       │         │         │
    Browser     Node      CLI
```

برای ساخت یک SDK عمومی ایده خوبی است.

---

# 7. sm-sokout/tse-option

[sm-sokout/tse-option](https://github.com/sm-sokout/tse-option?utm_source=chatgpt.com)

این پروژه را نباید با data clientهای قبلی یکی دانست.

هدف:

> Options Analytics

قابلیت‌ها:

* Call
* Put
* Option Chain
* historical price
* IV
* leverage
* BSM
* Open Interest
* risk-free rate
* margin
* TSE/IFB

([GitHub][17])

---

## معماری مفهومی

```text
Underlying
    │
    ├── Price History
    │
    └── Volatility
             │
             ▼
        Option Chain
             │
       ┌─────┼─────┐
       │     │     │
      IV   BSM  Leverage
       │
       ▼
     Greeks
```

---

## نقطه قوت

این repo نشان می‌دهد Options باید **ماژول مستقل** داشته باشد.

نباید داخل مدل `Stock` چیزی مثل:

```text
option_strike
option_iv
option_expiry
```

اضافه کنیم.

بهتر است:

```text
Instrument
 ├── Equity
 ├── ETF
 ├── Option
 ├── Bond
 └── Index
```

و Options engine روی آن قرار گیرد.

---

## ضعف

فقط 17 commit دارد و از نظر engineering infrastructure با data clientهای بزرگ قابل مقایسه نیست. ([GitHub][17])

اما برای domain knowledge بسیار مفید است.

---

# 8. Ali-Marandi/finsight-pro

[Ali-Marandi/finsight-pro](https://github.com/Ali-Marandi/finsight-pro?utm_source=chatgpt.com)

این پروژه دیگر در لایه Market Data نیست؛ یک application کامل‌تر است.

معماری:

```text
Electron
   │
React + TypeScript
   │
FastAPI
   │
Services
   │
SQLAlchemy
   │
SQLite
```

و چند engine مختلف دارد:

* ratios
* bankruptcy
* OCR
* benchmarking
* compliance
* consolidation
* ARIMA
* GARCH
* VaR
* Monte Carlo
* Black-Scholes
* Markowitz
* AI Copilot
* TSETMC

([GitHub][18])

---

## معماری backend

طبق ساختار repository:

```text
api/
└── app/
    ├── routers/
    ├── services/
    ├── models/
    └── middleware/
```

ده router و ده service دارد. ([GitHub][18])

این separation از نظر application architecture خوب است.

---

## نکته مهم درباره AI

AI اینجا عمدتاً **لایه application** است، نه data infrastructure.

یعنی:

```text
Financial Data
       ↓
Analysis
       ↓
Context
       ↓
LLM
```

نه:

```text
LLM
 ↓
Raw TSETMC
```

این تفکیک بسیار مهم است.

---

## نقاط قوت

برای ساخت یک financial workstation ایده‌های زیادی دارد:

```text
Data
 +
Analytics
 +
Quant
 +
AI
 +
Reporting
```

و از لحاظ stack هم مدرن است:

* React
* TypeScript
* FastAPI
* SQLAlchemy
* SQLite
* ReportLab
* Tesseract
* httpx
* GitHub Actions

([GitHub][18])

---

## ضعف

### 1. Repository نسبتاً جوان

46 commit دارد. ([GitHub][18])

### 2. Commercial License

CLI تحت MIT است اما Desktop و API تحت Commercial License هستند. ([GitHub][18])

### 3. Scope بسیار بزرگ

قرار دادن:

```text
OCR
AI
TSETMC
GARCH
IFRS
Bankruptcy
Portfolio
```

در یک محصول باعث افزایش coupling می‌شود مگر اینکه boundaries بسیار دقیق باشند.

---

# 9. Mmadrb/tehran-stock-exchange-buysell-engine

[Mmadrb/tehran-stock-exchange-buysell-engine](https://github.com/Mmadrb/tehran-stock-exchange-buysell-engine?utm_source=chatgpt.com)

این پروژه در topicهای TSETMC با عنوان یک BUY/SELL signal engine با FastAPI و React معرفی شده و آخرین update ثبت‌شده آن در آوریل ۲۰۲۶ است. ([GitHub][19])

## جایگاه معماری

اینجا وارد لایه:

```text
Market Data
     ↓
Indicators
     ↓
Signals
     ↓
Screener
     ↓
Dashboard
```

می‌شویم.

این دقیقاً لایه‌ای است که باید **بعد از Data Platform** قرار گیرد.

---

## نکته معماری مهم

نباید چنین چیزی بسازیم:

```text
TSETMC
 ↓
BUY/SELL
```

بلکه:

```text
TSETMC
 ↓
Raw Data
 ↓
Normalized Data
 ↓
Feature Store
 ↓
Indicator Engine
 ↓
Strategy Engine
 ↓
Signal
```

اگر این separation رعایت نشود، بعداً backtesting قابل اعتماد بسیار سخت می‌شود.

---

## نتیجه درباره این repo

ارزش اصلی آن برای ما **Strategy/Application layer** است، نه ingestion.

و ادعای BUY/SELL آن را نباید با صحت استراتژی معاملاتی یکی دانست؛ وجود یک signal engine به خودی خود اثبات‌کننده عملکرد معاملاتی نیست.

---

# 10. BabakEslami/tse-market-data

[BabakEslami/tse-market-data](https://github.com/BabakEslami/tse-market-data?utm_source=chatgpt.com)

این پروژه از نظر من **غافلگیرکننده‌ترین و مهم‌ترین repository این بررسی** است.

چرا؟

چون بقیه پروژه‌ها عمدتاً می‌گویند:

> چگونه از TSETMC داده بگیریم؟

اما این پروژه می‌گوید:

> **اصلاً TSETMC چه endpointهایی دارد؟**

---

# معماری واقعی APIهای کشف‌شده

دو gateway:

```text
             Iran Capital Market
                     │
          ┌──────────┴──────────┐
          │                     │
   cdn.tsetmc.com         webgw.tse.ir
          │                     │
       InsCode                 ISIN
```

`cdn.tsetmc.com` مجموعه بزرگی از endpointهای undocumented دارد؛ `webgw.tse.ir` نیز gateway رسمی سایت `tse.ir` است و endpointهای متفاوتی ارائه می‌کند. ([GitHub][2])

---

## cdn

مثلاً:

```text
ClosingPrice
ClientType
Instrument
MarketData
Index
Fund
```

و مواردی مانند:

```text
GetClosingPriceDailyList
GetInstrumentSearch
GetInstrumentInfo
GetInstrumentIdentity
GetClientTypeHistory
GetMarketOverview
GetSectorsSummary
```

مستند شده‌اند. ([GitHub][20])

---

## webgw

قابلیت‌های مهم:

```text
MarketWatchCash
LiveInstrumentByIdQuery
History/Archive
InstrumentShortcut
MarketSummary
CompanyState
```

دارد. ([GitHub][20])

---

# مهم‌ترین کشف: دو شناسه برای Instrument

این مسئله برای معماری ما فوق‌العاده مهم است.

### cdn

```text
InsCode
```

مثلاً:

```text
17914401175772326
```

### webgw

```text
ISIN
```

مثلاً:

```text
IRO1...
```

([GitHub][2])

بنابراین مدل داخلی ما نباید فقط یکی از این‌ها باشد.

بهتر:

```text
Instrument
├── internal_id
├── isin
├── ins_code
├── symbol
├── company_name
├── market
├── instrument_type
└── ...
```

---

# Order Book

یک تفاوت بسیار مهم:

در cdn:

```text
BestLimits
```

ممکن است delta-oriented باشد و reconstruction لازم داشته باشد.

اما در webgw:

```text
LiveInstrumentByIdQuery
```

order book سطح ۱ را به‌صورت آماده ارائه می‌کند. ([GitHub][2])

این یعنی برای realtime system باید **provider abstraction** داشته باشیم:

```text
OrderBookProvider
       │
 ┌─────┴─────┐
 │           │
 CDN       WebGW
```

---

# Market Watch

این پروژه نشان می‌دهد endpoint قدیمی `GetMarketWatch` همیشه گزینه مناسبی نیست و webgw می‌تواند market watch کامل‌تری ارائه کند. همچنین یک endpoint legacy برای Excel MarketWatch نیز مستند شده است. ([GitHub][20])

این دقیقاً همان چیزی است که یک Data Acquisition Layer باید مدیریت کند:

```text
Provider A
   │
   ├── available?
   │
   ▼
Provider B
   │
   ▼
Fallback
```

---

# مقایسه نهایی رپوها

| Repository      | Data Acquisition | Historical | Intraday | Async | Storage | Analytics | Architecture |
| --------------- | ---------------- | ---------- | -------- | ----- | ------- | --------- | ------------ |
| pytse-client    | ★★★★★            | ★★★★★      | ★★★      | ★★★   | ★★      | ★★★       | ★★★★         |
| tehran-stocks   | ★★★              | ★★★★★      | ★        | ★     | ★★★★★   | ★★        | ★★★★         |
| tsetmc-api      | ★★★★             | ★★★★       | ★★★★     | ★★    | ★       | ★★        | ★★★★         |
| 5j9/tsetmc      | ★★★★★            | ★★★★★      | ★★★★★    | ★★★★★ | ★★★     | ★★        | ★★★★★        |
| tse-index       | ★★★★             | ★★★★★      | ★        | ★     | ★★      | ★★★       | ★★★          |
| tse-client JS   | ★★★★★            | ★★★★★      | ★★★★★    | ★★★★  | ★★★★    | ★★        | ★★★★         |
| tse-option      | ★★★              | ★★★★       | ★★       | ★     | ★       | ★★★★★     | ★★★          |
| finsight-pro    | ★★★              | ★★★        | ★★       | ★★    | ★★★★    | ★★★★★     | ★★★★         |
| buysell-engine  | ★★               | ★★         | ★★       | ★★    | ★★★     | ★★★★★     | ★★★★         |
| tse-market-data | ★★★★★            | —          | —        | —     | —       | —         | ★★★★★        |

> این ستاره‌ها **رتبه‌بندی کیفیت پروژه یا «بهترین/بدترین» نیستند**؛ یک خلاصه توصیفی از حوزه تمرکز و عمق فنی مشاهده‌شده‌اند.

---

# مهم‌ترین چیزهایی که باید از این رپوها برداریم

## 1. Provider abstraction

از `tse-market-data` مشخص می‌شود که نباید application را مستقیماً به TSETMC متصل کنیم.

```text
                 Market Data Interface
                         │
           ┌─────────────┼─────────────┐
           │             │             │
        TSETMC CDN      WebGW       Legacy
```

---

# 2. Instrument Master

یکی از مهم‌ترین componentهای سیستم باید باشد:

```text
Instrument Master
│
├── internal_id
├── ins_code
├── isin
├── symbol
├── name
├── market
├── market_type
├── industry
├── sub_industry
├── instrument_type
├── status
├── lifecycle
└── aliases
```

این ایده از کنار هم گذاشتن `pytse-client`، `5j9/tsetmc`، `tse-index` و مخصوصاً `tse-market-data` به‌وضوح بیرون می‌آید. ([GitHub][4])

---

# 3. Raw Data باید نگهداری شود

یک اشتباه رایج این است:

```text
TSETMC
 ↓
Parser
 ↓
Database
```

من پیشنهاد می‌کنم:

```text
TSETMC
 ↓
Raw Response
 ↓
Normalizer
 ↓
Canonical Model
 ↓
Analytics
```

چرا؟

چون endpointهای TSETMC ممکن است تغییر کنند.

اگر raw response را نداشته باشی، debugging و reprocessing سخت می‌شود.

---

# 4. Reference Data باید جدا باشد

```text
Instrument Master
Market Calendar
Industries
Indexes
Corporate Actions
```

از:

```text
Trades
Quotes
OrderBook
Prices
```

جدا باشند.

---

# 5. Historical و Intraday دو سیستم متفاوت‌اند

این موضوع در `tse-client` و `5j9/tsetmc` خیلی واضح دیده می‌شود. ([GitHub][16])

### Historical

```text
batch
chunk
incremental
storage
```

### Intraday

```text
stream/poll
delta
state
event
reconstruction
```

نباید یک crawler برای هر دو استفاده شود.

---

# 6. Adjustment باید یک Service مستقل باشد

```text
Raw Price
   │
   ├── Unadjusted
   │
   └── Adjustment Engine
             │
             ├── Capital Increase
             ├── Dividend
             └── Corporate Action
```

این مفهوم در `tse-index` و `tse-client` به‌خوبی دیده می‌شود. ([GitHub][15])

---

# 7. Market Data و Analytics نباید قاطی شوند

معماری درست:

```text
             Market Data
                  │
             Canonical Data
                  │
        ┌─────────┼─────────┐
        │         │         │
    Technical Fundamental Options
        │         │         │
        └─────────┼─────────┘
                  │
              Features
                  │
             Strategies
                  │
              Signals
```

نه اینکه داخل crawler مثلاً RSI یا BUY/SELL محاسبه کنیم.

---

# 8. AI باید آخر زنجیره باشد

از بررسی `finsight-pro` این نکته خیلی واضح است.

AI نباید مستقیماً مسئول جمع‌آوری داده باشد.

مدل درست:

```text
TSETMC
  ↓
Data Platform
  ↓
Financial Data
  ↓
Feature/Analytics
  ↓
Context Builder
  ↓
AI
```

مثلاً:

```text
AI
 ├── تحلیل گزارش مالی
 ├── توضیح تغییرات سهم
 ├── خلاصه اخبار
 ├── تحلیل اطلاعیه
 ├── پرسش روی historical data
 └── Natural Language Screener
```

---

# 9. Options باید bounded context جدا باشد

```text
Core Market
     │
     ├── Equity
     ├── ETF
     ├── Index
     ├── Bond
     │
     └── Derivatives
            │
            ├── Call
            ├── Put
            ├── Greeks
            ├── IV
            └── Option Chain
```

`tse-option` این domain را به‌خوبی نمایندگی می‌کند. ([GitHub][17])

---

# 10. برای production به fallback نیاز داریم

با توجه به تجربه پروژه‌های مختلف:

```text
Primary Provider
      ↓
Validation
      ↓
Failed?
      │
      ├── No → Accept
      │
      └── Yes
            ↓
       Secondary Provider
            ↓
          Legacy
```

این یکی از مهم‌ترین درس‌های کل پروژه‌هاست.

---

# معماری‌ای که من از این تحقیق استخراج می‌کنم

اگر قرار باشد بر اساس تمام این مطالعات **یک سیستم جدید** طراحی کنم، معماری را تقریباً این‌گونه می‌گذارم:

```text
                         ┌─────────────────────┐
                         │   External Sources  │
                         │                     │
                         │ TSETMC CDN          │
                         │ TSE WebGW           │
                         │ Legacy APIs         │
                         │ Codal               │
                         │ TGJU                │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Data Acquisition     │
                         │                     │
                         │ HTTP Client          │
                         │ Retry                │
                         │ Rate Control         │
                         │ Provider Fallback    │
                         │ Raw Capture          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Normalization       │
                         │                     │
                         │ JSON → Canonical    │
                         │ Persian Normalizer  │
                         │ Type Conversion     │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
             Instrument Master   Market Data     Corporate Actions
                    │               │                │
                    │        ┌──────┼──────┐         │
                    │        │      │      │         │
                    │      Daily  Trade  Quote      │
                    │             │      │           │
                    │             └──┬───┘           │
                    │                │               │
                    └────────────────┼───────────────┘
                                     ▼
                           ┌──────────────────┐
                           │   Data Storage   │
                           │                  │
                           │ PostgreSQL       │
                           │ Object Storage   │
                           │ Cache             │
                           └────────┬─────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
           Historical          Realtime          Feature Store
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ▼
                         ┌────────────────────┐
                         │ Analytics Platform │
                         │                    │
                         │ Technical          │
                         │ Fundamental        │
                         │ Options            │
                         │ Portfolio          │
                         └──────────┬─────────┘
                                    │
                                    ▼
                         ┌────────────────────┐
                         │ Strategy Engine    │
                         │                    │
                         │ Screener           │
                         │ Rules              │
                         │ Signals            │
                         │ Backtest           │
                         └──────────┬─────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                  REST            WebSocket          AI
                   API               │               │
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                              Web Dashboard
```

---

# نتیجه نهایی هر Repository

### `pytse-client`

**بهترین چیزی که از آن می‌گیریم:** breadth داده و abstraction نماد.

**چیزی که نمی‌گیریم:** معماری مستقیم آن برای یک platform بزرگ و dependency/licensing آن بدون بررسی بیشتر. ([GitHub][3])

### `tehran-stocks`

**بهترین درس:** Local Dataset + ORM + incremental update. ([GitHub][7])

### `tsetmc-api`

**بهترین درس:** domain decomposition و DTOهای typed. ([GitHub][21])

### `5j9/tsetmc`

**بهترین درس:** async واقعی، Polars، event-driven MarketWatch و offline instrument dataset. ([GitHub][13])

### `tse-index`

**بهترین درس:** batch historical ingestion، incremental update، adjustment و resampling. ([GitHub][15])

### `tse-client`

**بهترین درس:** crawler واقعی intraday، retry/chunk/cache/adjustment. ([GitHub][16])

### `tse-option`

**بهترین درس:** جدا کردن Options به‌عنوان domain مستقل و ساخت analytics روی آن. ([GitHub][17])

### `finsight-pro`

**بهترین درس:** اتصال Data + Financial Analytics + Quant + AI + UI در یک محصول. ([GitHub][18])

### `tehran-stock-exchange-buysell-engine`

**بهترین درس:** جدا کردن Strategy/Screener/Signal از Data Acquisition. ([GitHub][19])

### `tse-market-data`

**بهترین درس و شاید مهم‌ترین بخش کل تحقیق:** شناخت دقیق providerها، endpointها، تفاوت `InsCode` و `ISIN` و طراحی fallback بین gatewayها. ([GitHub][2])

---

# جمع‌بندی نهایی

اگر هدف تو **صرفاً استفاده از یک کتابخانه برای گرفتن قیمت بورس** باشد، این همه بررسی لازم نیست.

اما اگر هدفت چیزی شبیه:

> **یک پلتفرم جامع داده و تحلیل بورس ایران**

باشد، این تحقیق یک نتیجه بسیار مشخص دارد:

### نباید یک repository را fork کنیم و توسعه بدهیم.

بلکه باید:

```text
5j9/tsetmc
      +
tsetmc-api
      +
tse-market-data
      +
tehran-stocks
      +
tse-client
      +
tse-option
      +
ایده‌های application از finsight-pro
      +
strategy concepts از buysell-engine
```

را **مطالعه کنیم و یک معماری جدید مستقل بسازیم.**

و مهم‌تر اینکه ستون فقرات چنین سیستمی باید این چهار component باشد:

```text
1. Instrument Master
2. Provider / Data Acquisition Layer
3. Canonical Market Data Model
4. Historical + Realtime Storage
```

بعد از آن:

```text
Analytics
→ Screener
→ Strategy
→ Backtesting
→ Portfolio
→ AI
```

به آن متصل شوند.

**به‌نظر من مهم‌ترین قدم بعدی دیگر بررسی Repository جدید نیست؛ بلکه تبدیل این یافته‌ها به یک Architecture Blueprint واقعی است:** یعنی دقیقاً طراحی کنیم `Instrument` چه فیلدهایی داشته باشد، `InsCode/ISIN` را چگونه نگه داریم، raw و normalized data کجا ذخیره شوند، historical/intraday چگونه ingest شوند، provider fallback چگونه کار کند، چه DBای مناسب است و در نهایت API و AI روی این زیرساخت چگونه قرار بگیرند.

[1]: https://github.com/topics/tsetmc?o=desc&utm_source=chatgpt.com "tsetmc · GitHub Topics · GitHub"
[2]: https://github.com/BabakEslami/tse-market-data?utm_source=chatgpt.com "GitHub - BabakEslami/tse-market-data: مرجع کامل endpoint های API بازار سرمایه ایران — cdn.tsetmc.com (56مرجع کامل endpoint های API بازار سرمایه ایران — cdn.tsetmc.com و webgw.tse.ir (gateway رسمی tse.ir) endpoint) و webgw.tse.ir (gateway رسمی tse.ir)، تست‌شده و مستندشده · GitHub"
[3]: https://github.com/Glyphack/pytse-client?utm_source=chatgpt.com "GitHub - Glyphack/pytse-client: work with Tehran stock exchange data 💹 in Python · GitHub"
[4]: https://github.com/Glyphack/pytse-client/blob/master/pytse_client/ticker/ticker.py?utm_source=chatgpt.com "pytse-client/pytse_client/ticker/ticker.py at master · Glyphack/pytse-client · GitHub"
[5]: https://github.com/Glyphack/pytse-client/issues?utm_source=chatgpt.com "Issues · Glyphack/pytse-client · GitHub"
[6]: https://github.com/Glyphack/pytse-client/blob/master/pyproject.toml?utm_source=chatgpt.com "pytse-client/pyproject.toml at master · Glyphack/pytse-client · GitHub"
[7]: https://github.com/ghodsizadeh/tehran-stocks?utm_source=chatgpt.com "GitHub - ghodsizadeh/tehran-stocks: A python package to access tsetmc data · GitHub"
[8]: https://github.com/ghodsizadeh/tehran-stocks/issues?utm_source=chatgpt.com "Issues · ghodsizadeh/tehran-stocks · GitHub"
[9]: https://github.com/mahs4d/tsetmc-api?utm_source=chatgpt.com "GitHub - mahs4d/tsetmc-api: python library to fetch tehran stocks market data · GitHub"
[10]: https://github.com/mahs4d/tsetmc-api/blob/master/examples/day_details_example.py?utm_source=chatgpt.com "tsetmc-api/examples/day_details_example.py at master · mahs4d/tsetmc-api · GitHub"
[11]: https://github.com/mahs4d/tsetmc-api/blob/master/lib/tsetmc_api/market_watch/price.py?utm_source=chatgpt.com "tsetmc-api/lib/tsetmc_api/market_watch/price.py at master · mahs4d/tsetmc-api · GitHub"
[12]: https://github.com/mahs4d/tsetmc-api/blob/master/lib/tsetmc_api/day_details/_core.py?utm_source=chatgpt.com "tsetmc-api/lib/tsetmc_api/day_details/_core.py at master · mahs4d/tsetmc-api · GitHub"
[13]: https://github.com/5j9/tsetmc?utm_source=chatgpt.com "GitHub - 5j9/tsetmc: An async Python library to fetch data from https://tsetmc.com/ · GitHub"
[14]: https://github.com/alised/tse-index?utm_source=chatgpt.com "GitHub - alised/tse-index: Fetch stock indices data of Tehran Stock Exchange · GitHub"
[15]: https://github.com/alised/tse-index/blob/main/tse_index/tse.py?utm_source=chatgpt.com "tse-index/tse_index/tse.py at main · alised/tse-index · GitHub"
[16]: https://github.com/m-ahmadi/tse-client?utm_source=chatgpt.com "GitHub - m-ahmadi/tse-client: A client for fetching stock data from the Tehran Stock Exchange (TSETMC). Works in Browser, Node and as CLI. · GitHub"
[17]: https://github.com/sm-sokout/tse-option?utm_source=chatgpt.com "GitHub - sm-sokout/tse-option: بررسی و دریافت اطلاعات اختیار معاملات بورس تهران و فرابورس ایران | Options on the Tehran Stock Exchange (TSE) and IranFarabourse (IFB) · GitHub"
[18]: https://github.com/Ali-Marandi/finsight-pro?utm_source=chatgpt.com "GitHub - Ali-Marandi/finsight-pro: AI-Powered Financial Analysis Desktop App — 7 Engines, 17+ Ratios, Bankruptcy Prediction, TSETMC Live, 100% Offline · GitHub"
[19]: https://github.com/topics/tsetmc?o=asc&s=stars&utm_source=chatgpt.com "tsetmc · GitHub Topics · GitHub"
[20]: https://github.com/BabakEslami/tse-market-data/blob/main/ENDPOINTS.md?utm_source=chatgpt.com "tse-market-data/ENDPOINTS.md at main · BabakEslami/tse-market-data · GitHub"
[21]: https://github.com/mahs4d/tsetmc-api/blob/master/lib/tsetmc_api/day_details/day_details.py?utm_source=chatgpt.com "tsetmc-api/lib/tsetmc_api/day_details/day_details.py at master · mahs4d/tsetmc-api · GitHub"
