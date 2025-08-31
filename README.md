# Congress Alpha

> Real-time tracking of Congressional stock trades with comprehensive data analysis and transparency tools.

**🌐 Live Application:** [Congress Alpha](https://congressalpha.vercel.app/)  
**📊 Current Data:** 46,859+ trades across 696 members since 2012 (~$2.9B total disclosed)

## Overview

Congress Alpha is a production-ready web application that provides comprehensive tracking and analysis of stock trades made by members of the U.S. Congress. Built with modern technologies and real-time data ingestion, it offers transparency into congressional financial activities through an intuitive interface.

**⚠️ Educational Use Only:** This tool is designed for educational and transparency purposes only. The accuracy of data cannot be guaranteed, and it should not be used for making financial decisions or investment advice.

## 🚀 Features

- **Real-Time Data Ingestion:** Automated daily scraping from official House and Senate disclosure portals
- **Advanced Search:** Search by member name, ticker symbol, or issuer company
- **Member Profiles:** Detailed trading history and financial insights for individual Congress members
- **Trading Analytics:** Volume analysis, performance metrics, and trend visualization
- **Interactive Charts:** Real-time stock price charts with trading overlay markers
- **Recent Trades Dashboard:** Live feed of the latest disclosed transactions
- **Top Traded Stocks:** Ranking of most actively traded securities by Congress
- **API Endpoints:** RESTful API for programmatic access to trading data

## 📊 Data Sources & Legal Compliance

### Official Data Sources

- **House Financial Disclosures:** [House Financial Disclosure Reports](https://disclosures-clerk.house.gov/FinancialDisclosure)
- **Senate Financial Disclosures:** [U.S. Senate Public Disclosure](https://www.disclosure.senate.gov/)

### Compliance & Usage Notice

This application uses publicly available financial disclosure data as mandated by the STOCK Act. All data is sourced from official government portals:

- House disclosure data is used in accordance with the House Ethics Committee usage guidelines
- Senate disclosure data follows public access provisions under Senate rules
- Data extraction respects rate limits and terms of service of source systems
- No proprietary or non-public information is accessed or stored

**Legal Disclaimer:** This is an educational tool providing analysis of publicly disclosed information. It is not affiliated with or endorsed by the U.S. House of Representatives, U.S. Senate, or any government entity.

## 🏗️ System Overview

### Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Data Sources  │    │   Ingestion      │    │   Application   │
│                 │    │                  │    │                 │
│ • House Portal  │───▶│ • Python Scripts │───▶│ • Next.js App   │
│ • Senate Portal │    │ • LLM Parsing    │    │ • Prisma ORM    │
│ • Stock Prices  │    │ • Data Cleaning  │    │ • PostgreSQL    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   Supabase DB    │    │   Vercel CDN    │
                       │                  │    │                 │
                       │ • PostgreSQL     │    │ • Edge Caching  │
                       │ • Edge Functions │    │ • Global Deploy │
                       │ • Scheduled Jobs │    │ • Analytics     │
                       └──────────────────┘    └─────────────────┘
```

### Data Pipeline

1. **Daily Ingestion:** Automated scripts check for new PTR filings via Supabase Cron
2. **PDF Processing:** LLM-assisted extraction of tabular data from variable-format PDFs
3. **Data Normalization:** Asset matching, duplicate detection, and data validation
4. **Database Upsert:** Idempotent database operations with conflict resolution
5. **Real-time Updates:** Live data reflected in the web application

## 📋 Database Schema

### Core Tables

```sql
-- Congressional Members
Members (member_id, name, party, state, chamber, photo_url)

-- Financial Disclosure Filings
Filings (filing_id, member_id, doc_id, url, filing_date, verified)

-- Individual Trade Transactions
Transactions (transaction_id, filing_id, asset_id, transaction_type,
              transaction_date, amount_range_low, amount_range_high)

-- Traded Assets/Companies
Assets (asset_id, company_name, ticker, ticker_clean, company_clean)

-- Historical Stock Prices
StockPrices (ticker, date, open, high, low, close, volume, adj_close)

-- API Request Tracking
API_Requests (request_id, filing_id, model, tokens, response_status)
```

## 🛠️ Technology Stack

- **Frontend:** Next.js 15, React 19, TypeScript
- **Styling:** Tailwind CSS 4, PostCSS
- **Database:** PostgreSQL (Supabase)
- **ORM:** Prisma
- **Charts:** Chart.js, React Chart.js 2
- **Deployment:** Vercel (Frontend), Supabase (Database + Functions)
- **Analytics:** Vercel Analytics & Speed Insights
- **Data Ingestion:** Python (BeautifulSoup, Requests, OpenAI API)

## 🚀 Getting Started

### Prerequisites

- Node.js 18+
- pnpm
- PostgreSQL database (or Supabase account)

### Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/AnuragVatash/Congress-Alpha.git
   cd Congress-Alpha/webstack
   ```

2. **Install dependencies:**

   ```bash
   pnpm install
   ```

3. **Environment Setup:**

   ```bash
   cp .env.example .env
   ```

   Required environment variables:

   ```env
   # Supabase Configuration
   DATABASE_URL="postgresql://..."
   DIRECT_URL="postgresql://..."
   NEXT_PUBLIC_SUPABASE_URL="https://..."
   NEXT_PUBLIC_SUPABASE_ANON_KEY="..."
   SUPABASE_SERVICE_KEY="..."

   # Optional: Stock Price Data API
   TIINGO_API_KEY="your_tiingo_key"
   ```

4. **Database Setup:**

   ```bash
   pnpm db:generate
   pnpm db:migrate
   ```

5. **Run the development server:**

   ```bash
   pnpm dev
   ```

6. **Open [http://localhost:3000](http://localhost:3000)** in your browser.

### Data Ingestion (Optional)

The live application uses automated ingestion, but you can run scripts manually:

```bash
# Navigate to Scripts directory
cd ../Scripts

# Install Python dependencies
pip install -r common/requirements.txt

# Run House data scraper
cd "HOR Script"
python app.py

# Run Senate data scraper
cd "../Senate Script"
python app.py
```

## 📅 Automated Operations

### Scheduled Data Updates

- **Frequency:** Daily at 06:00 UTC
- **Trigger:** Supabase Cron Jobs
- **Process:** New PTR filings → PDF extraction → Database upsert
- **Monitoring:** Error alerting via Supabase Functions
- **Backup:** Daily database snapshots

### Data Quality Assurance

- Duplicate detection and merging
- Asset name standardization and ticker matching
- Transaction validation and anomaly detection
- Failed parsing review queue for manual verification

## 📊 API Endpoints

### Public API Routes

```typescript
// Recent trades
GET /api/recent?limit=50

// Search politicians
GET /api/search/politicians?q=pelosi

// Search stocks
GET /api/search/stocks?q=AAPL

// Member trading history
GET /api/members/[id]/trades

// Stock price data
GET /api/stock-prices/[ticker]

// All trades (paginated)
GET /api/trades?page=1&limit=100
```

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting (`pnpm lint`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines

- Follow TypeScript best practices
- Add tests for new features
- Update documentation as needed
- Ensure responsive design compatibility

## 📜 License

This project is licensed under the Apache License 2.0 - see the [LICENSE.txt](LICENSE.txt) file for details.

## 🔗 Links

- **Live Application:** [congressalpha.vercel.app](https://congressalpha.vercel.app/)
- **GitHub Repository:** [Congress-Alpha](https://github.com/AnuragVatash/Congress-Alpha)
- **House Disclosures:** [House Financial Disclosure Reports](https://disclosures-clerk.house.gov/FinancialDisclosure)
- **Senate Disclosures:** [U.S. Senate Public Disclosure](https://www.disclosure.senate.gov/)

## 📞 Contact

For questions, feedback, or issues:

- Open a GitHub Issue
- Email: [Your Contact Email]

---

**Built with ❤️ for government transparency and financial accountability.**
