export const dynamic = "force-dynamic";
export const revalidate = 0;
// webstack/src/app/page.tsx
// OPTIMIZED VERSION - Uses SQL aggregation instead of loading individual transactions

import HeroSection from "@/src/components/HeroSection";
import SearchSection from "@/src/components/SearchSection";
import StatsGrid from "@/src/components/StatsGrid";
import RecentTradesHome from "@/src/components/RecentTradesHome";
import { prisma } from "@/src/lib/prisma";
import Link from "next/link";
import Image from "next/image";
import TickerBar from "@/src/components/TickerBar";
import { unstable_cache } from "next/cache";

// Performance monitoring functions
async function measureTimeAsync<T>(
  operationName: string,
  fn: () => Promise<T>
): Promise<T> {
  const start = performance.now();
  const result = await fn();
  const end = performance.now();
  const duration = end - start;

  console.log(`🚀 HOME: ${operationName} took ${duration.toFixed(2)}ms`);
  return result;
}

// OPTIMIZED: Get featured politicians with caching and efficient joins
const getFeaturedPoliticiansOptimized = unstable_cache(
  async () => {
    return measureTimeAsync("Featured Politicians SQL Query", async () => {
      const result = await prisma.$queryRaw<
        Array<{
          member_id: number;
          name: string;
          photo_url: string | null;
          party: string | null;
          state: string | null;
          chamber: string | null;
          trade_count: bigint;
          total_volume: number;
        }>
      >`
        SELECT 
          m.member_id,
          m.name,
          m.photo_url,
          m.party,
          m.state,
          m.chamber,
          COUNT(t.transaction_id) as trade_count,
          COALESCE(SUM((t.amount_range_low + t.amount_range_high) / 2.0), 0) as total_volume
        FROM "Members" m
        JOIN "Filings" f ON m.member_id = f.member_id
        JOIN "Transactions" t ON f.filing_id = t.filing_id
        GROUP BY m.member_id, m.name, m.photo_url, m.party, m.state, m.chamber
        ORDER BY trade_count DESC
        LIMIT 5
      `;

      return result.map((row) => ({
        member_id: row.member_id,
        name: row.name,
        photo_url: row.photo_url,
        party: row.party,
        state: row.state,
        chamber: row.chamber,
        tradeCount: Number(row.trade_count),
        totalVolume: row.total_volume,
      }));
    });
  },
  ["home:featured-politicians:v1"],
  { revalidate: 300 }
);

// OPTIMIZED: Get top stocks with caching and efficient joins
const getTopStocksOptimized = unstable_cache(
  async () => {
    return measureTimeAsync("Top Stocks SQL Query", async () => {
      const result = await prisma.$queryRaw<
        Array<{
          asset_id: number;
          ticker: string;
          company_name: string;
          trade_count: bigint;
          total_volume: number;
        }>
      >`
        SELECT 
          a.asset_id,
          a.ticker,
          a.company_name,
          COUNT(t.transaction_id) as trade_count,
          COALESCE(SUM((t.amount_range_low + t.amount_range_high) / 2.0), 0) as total_volume
        FROM "Assets" a
        JOIN "Transactions" t ON a.asset_id = t.asset_id
        WHERE a.ticker IS NOT NULL
        GROUP BY a.asset_id, a.ticker, a.company_name
        ORDER BY trade_count DESC
        LIMIT 5
      `;

      return result.map((row) => ({
        asset_id: row.asset_id,
        ticker: row.ticker || "N/A",
        company_name: row.company_name,
        tradeCount: Number(row.trade_count),
        totalVolume: row.total_volume,
      }));
    });
  },
  ["home:top-stocks:v1"],
  { revalidate: 300 }
);

// OPTIMIZED: Get platform statistics with caching
const getPlatformStatsOptimized = unstable_cache(
  async () => {
    return measureTimeAsync("Platform Statistics SQL Queries", async () => {
      const [totalTradesResult, totalMembersResult, totalVolumeResult] =
        await Promise.all([
          prisma.transactions.count(),
          prisma.members.count(),
          prisma.$queryRaw<Array<{ total_volume: number }>>`
          SELECT COALESCE(SUM((amount_range_low + amount_range_high) / 2.0), 0) as total_volume
          FROM "Transactions"
        `,
        ]);

      return {
        totalTrades: totalTradesResult,
        totalMembers: totalMembersResult,
        totalVolume: Number(totalVolumeResult[0]?.total_volume || 0),
      };
    });
  },
  ["home:platform-stats:v1"],
  { revalidate: 60 }
);

export default async function Home() {
  const pageStart = performance.now();
  console.log("🔍 HOME: Starting Home page render with SQL optimization");

  // Run all optimized queries in parallel
  const [
    featuredPoliticians,
    topStocks,
    platformStats,
    recentTrades,
    latestApiRequest,
  ] = await Promise.all([
    getFeaturedPoliticiansOptimized(),
    getTopStocksOptimized(),
    getPlatformStatsOptimized(),
    // Recent trades still need individual records since they're displayed
    measureTimeAsync("Recent Trades Query", () =>
      prisma.transactions.findMany({
        include: {
          Assets: true,
          Filings: {
            include: {
              Members: true,
            },
          },
        },
        orderBy: {
          transaction_date: "desc",
        },
        take: 20,
      })
    ),
    // Get the latest API request to determine last update time
    measureTimeAsync("Latest API Request Query", () =>
      prisma.aPI_Requests.findFirst({
        orderBy: {
          created_at: "desc",
        },
        select: {
          created_at: true,
        },
      })
    ),
  ]);

  const pageEnd = performance.now();
  console.log(
    `🚀 HOME: TOTAL PAGE TIME: ${(pageEnd - pageStart).toFixed(2)}ms`
  );

  // Fetch the top 30 largest transactions for the ticker (server-side SQL query)
  const topTransactions = await prisma.transactions.findMany({
    where: {
      AND: [
        { amount_range_high: { not: null } },
        { amount_range_low: { not: null } },
        { Assets: { ticker: { not: null } } },
      ],
    },
    include: {
      Assets: true,
      Filings: {
        include: {
          Members: true,
        },
      },
    },
    orderBy: {
      amount_range_high: "desc",
    },
    take: 30,
  });

  // Helper to format currency
  function formatCurrency(value: number | null) {
    if (value == null) return "N/A";
    if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
    return `${value}`;
  }

  // Helper to format date with deterministic locale and timezone to avoid hydration mismatches
  function formatDate(date: Date | string | null) {
    if (!date) return "";
    const d = date instanceof Date ? date : new Date(date);
    try {
      return d.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      });
    } catch {
      // Fallback: ISO slice
      return d.toISOString().slice(0, 10);
    }
  }

  // Use the topTransactions for the ticker
  const tickerTrades = topTransactions.map((trade) => {
    const member = trade.Filings?.Members?.name || "Unknown";
    const ticker = trade.Assets?.ticker || "???";
    const low = formatCurrency(trade.amount_range_low);
    const high = formatCurrency(trade.amount_range_high);
    const amount = `$${low}–$${high}`;
    const type = trade.transaction_type.toLowerCase().includes("purchase")
      ? "Purchase"
      : "Sale";
    const date = formatDate(trade.transaction_date);
    return { member, ticker, amount, type, date };
  });

  return (
    <div
      className="min-h-screen"
      style={{
        background:
          "linear-gradient(120deg, var(--c-navy-50) 0%, var(--c-gray-50) 100%)",
        color: "var(--c-navy)",
      }}
    >
      {/* Top Ticker Bar Only */}
      <div
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          width: "100vw",
          background:
            "linear-gradient(90deg, var(--c-navy), var(--c-navy-600))",
          color: "#fff",
          minHeight: "56px",
          display: "flex",
          alignItems: "center",
          overflow: "hidden",
          zIndex: 100,
        }}
      >
        <TickerBar items={tickerTrades} />
        <style>{`body { margin-top: 56px !important; }`}</style>
      </div>
      {/* Hero Section with Sidebars */}
      <div className="relative py-4 px-4">
        <div
          style={{
            width: "1500px",
            maxWidth: "100%",
            margin: "0 auto",
            padding: 16,
            background:
              "linear-gradient(5deg, var(--c-navy), var(--c-navy-600))",
            borderRadius: "0.75rem",
            border: "1px solid #fff",
          }}
        >
          <div className="grid lg:grid-cols-12 gap-6">
            {/* Left Sidebar - Featured Members */}
            <div className="lg:col-span-3 order-2 lg:order-1">
              <div
                className="rounded-lg p-6 border h-full"
                style={{
                  background:
                    "linear-gradient(5deg, var(--c-navy), var(--c-navy-600))",
                  borderColor: "var(--c-navy-600)",
                }}
              >
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-xl font-bold text-white">
                    Featured Members
                  </h2>
                  <Link
                    href="/members"
                    className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                  >
                    View All →
                  </Link>
                </div>
                <div
                  className="space-y-2 overflow-hidden"
                  style={{ height: "408px" }}
                >
                  {featuredPoliticians.slice(0, 5).map((politician) => (
                    <Link
                      key={politician.member_id}
                      href={`/members/${politician.member_id}`}
                      className="block bg-gray-700 rounded-lg p-3 hover:bg-gray-600 transition-colors"
                      style={{ height: "76px" }}
                    >
                      <div className="flex items-center justify-between h-full">
                        <div className="flex items-center space-x-3 flex-1 min-w-0">
                          <div className="relative w-10 h-10 rounded-full overflow-hidden bg-gray-600 flex-shrink-0">
                            {politician.photo_url ? (
                              <Image
                                src={politician.photo_url}
                                alt={politician.name}
                                fill
                                className="object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm font-semibold">
                                {politician.name.charAt(0)}
                              </div>
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="text-white font-semibold text-sm truncate">
                              {politician.name}
                            </h3>
                            <p className="text-xs text-gray-400">
                              {politician.party} • {politician.chamber}
                            </p>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0 ml-2">
                          <div className="text-white font-semibold text-sm">
                            {politician.tradeCount} trades
                          </div>
                          <div className="text-xs text-gray-400">
                            ${(politician.totalVolume / 1000000) | 0}M
                          </div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            </div>

            {/* Center - Hero Section */}
            <div className="lg:col-span-6 order-1 lg:order-2">
              <HeroSection lastUpdateDate={latestApiRequest?.created_at} />
            </div>

            {/* Right Sidebar - Top Traded Stocks */}
            <div className="lg:col-span-3 order-3 lg:order-3">
              <div
                className="rounded-lg p-6 border h-full"
                style={{
                  background:
                    "linear-gradient(5deg, var(--c-navy), var(--c-navy-600))",
                  borderColor: "var(--c-navy-600)",
                }}
              >
                <div className="flex justify-between items-center mb-6">
                  <h2 className="text-xl font-bold text-white">
                    Top Traded Stocks
                  </h2>
                  <Link
                    href="/trades"
                    className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                  >
                    View All →
                  </Link>
                </div>
                <div
                  className="space-y-2 overflow-hidden"
                  style={{ height: "408px" }}
                >
                  {topStocks.slice(0, 5).map((stock) => (
                    <Link
                      key={stock.ticker}
                      href={`/stocks/${stock.asset_id}`}
                      className="block bg-gray-700 rounded-lg p-3 hover:bg-gray-600 transition-colors"
                      style={{ height: "76px" }}
                    >
                      <div className="flex items-center justify-between h-full">
                        <div className="flex items-center space-x-3 flex-1 min-w-0">
                          <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center flex-shrink-0">
                            <span className="text-white font-bold text-xs">
                              {stock.ticker}
                            </span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <h3 className="text-white font-semibold text-sm truncate">
                              {stock.company_name}
                            </h3>
                            <p className="text-xs text-gray-200">
                              {stock.tradeCount} trades
                            </p>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0 ml-2">
                          <div className="text-white font-semibold text-sm">
                            ${(stock.totalVolume / 1000000) | 0}M
                          </div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <RecentTradesHome trades={recentTrades} />
      <SearchSection />

      {/* Platform Statistics moved to bottom */}
      <StatsGrid
        totalTrades={platformStats.totalTrades}
        totalMembers={platformStats.totalMembers}
        totalVolume={platformStats.totalVolume}
      />

      {/* Newsletter Section */}
      <div className="py-12 px-4">
        <div className="max-w-7xl mx-auto">
          <div
            className="card text-center"
            style={{
              background:
                "linear-gradient(5deg, var(--c-navy), var(--c-navy-600))",
              border: "none",
            }}
          >
            <h3
              className="text-2xl font-bold mb-4"
              style={{ color: "var(--c-jade)" }}
            >
              Stay Updated on Congressional Trading
            </h3>
            <p className="mb-6 max-w-2xl mx-auto text-white">
              Get weekly insights and alerts about significant trades made by
              members of Congress. Join thousands of investors and journalists
              who rely on our data.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 max-w-md mx-auto">
              <input
                type="email"
                placeholder="Enter your email"
                className="flex-1 px-4 py-3 rounded-lg"
                id="newsletter-email"
                name="email"
              />
              <button className="button-primary">Subscribe</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
