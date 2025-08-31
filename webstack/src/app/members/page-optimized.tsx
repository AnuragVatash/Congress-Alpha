// webstack/src/app/members/page-optimized.tsx
// OPTIMIZED VERSION - Uses SQL aggregation instead of JavaScript processing

import { prisma } from "@/src/lib/prisma";
import Link from "next/link";
import Image from "next/image";
import MembersTable from "@/src/components/MembersTable";

// Force dynamic rendering since this page requires database access
export const dynamic = "force-dynamic";

type ChamberStats = {
  memberCount: number;
  totalTrades: number;
  totalVolume: number;
};

function formatCurrency(value: number): string {
  if (value >= 1e9) {
    return `$${(value / 1e9).toFixed(1)}B`;
  }
  if (value >= 1e6) {
    return `$${(value / 1e6).toFixed(1)}M`;
  }
  if (value >= 1e3) {
    return `$${(value / 1e3).toFixed(1)}K`;
  }
  return `$${value}`;
}

// Performance monitoring function
function measureTime<T>(operationName: string, fn: () => T): T {
  const start = performance.now();
  const result = fn();
  const end = performance.now();
  const duration = end - start;

  console.log(`🚀 OPTIMIZED: ${operationName} took ${duration.toFixed(2)}ms`);
  return result;
}

// Async performance monitoring function
async function measureTimeAsync<T>(
  operationName: string,
  fn: () => Promise<T>
): Promise<T> {
  const start = performance.now();
  const result = await fn();
  const end = performance.now();
  const duration = end - start;

  console.log(`🚀 OPTIMIZED: ${operationName} took ${duration.toFixed(2)}ms`);
  return result;
}

// OPTIMIZED: Use raw SQL to get member stats with aggregation
async function getMembersDataOptimized() {
  console.log("🔍 OPTIMIZED: Starting getMembersDataOptimized()");

  // Single optimized query using raw SQL with aggregation
  const membersWithStats = await measureTimeAsync(
    "Optimized SQL Query with Aggregation",
    async () => {
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
          latest_trade_date: string | null;
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
        COALESCE(SUM((t.amount_range_low + t.amount_range_high) / 2.0), 0) as total_volume,
        MAX(t.transaction_date) as latest_trade_date
      FROM "Members" m
      LEFT JOIN "Filings" f ON m.member_id = f.member_id
      LEFT JOIN "Transactions" t ON f.filing_id = t.filing_id
      GROUP BY m.member_id, m.name, m.photo_url, m.party, m.state, m.chamber
      HAVING COUNT(t.transaction_id) > 0
      ORDER BY total_volume DESC
    `;

      // Convert BigInt to number and parse dates
      return result.map((row) => ({
        member_id: row.member_id,
        name: row.name,
        photo_url: row.photo_url,
        party: row.party,
        state: row.state,
        chamber: row.chamber,
        tradeCount: Number(row.trade_count),
        totalVolume: row.total_volume,
        latestTradeDate: row.latest_trade_date
          ? new Date(row.latest_trade_date)
          : null,
      }));
    }
  );

  console.log(
    `📊 OPTIMIZED: Got ${membersWithStats.length} members with trades directly from SQL`
  );
  return membersWithStats;
}

// OPTIMIZED: State stats with SQL aggregation
async function getStateStatsOptimized() {
  return measureTimeAsync("Optimized State Statistics Query", async () => {
    const result = await prisma.$queryRaw<
      Array<{
        state: string;
        member_count: bigint;
        total_trades: bigint;
        total_volume: number;
      }>
    >`
      SELECT 
        m.state,
        COUNT(DISTINCT m.member_id) as member_count,
        COUNT(t.transaction_id) as total_trades,
        COALESCE(SUM((t.amount_range_low + t.amount_range_high) / 2.0), 0) as total_volume
      FROM "Members" m
      LEFT JOIN "Filings" f ON m.member_id = f.member_id
      LEFT JOIN "Transactions" t ON f.filing_id = t.filing_id
      WHERE m.state IS NOT NULL
      GROUP BY m.state
      HAVING COUNT(t.transaction_id) > 0
      ORDER BY total_volume DESC
      LIMIT 10
    `;

    return result.map((row) => ({
      state: row.state,
      memberCount: Number(row.member_count),
      totalTrades: Number(row.total_trades),
      totalVolume: row.total_volume,
      avgTradesPerMember: Number(row.total_trades) / Number(row.member_count),
    }));
  });
}

// OPTIMIZED: Party stats with SQL aggregation
async function getPartyStatsOptimized() {
  return measureTimeAsync("Optimized Party Statistics Query", async () => {
    const result = await prisma.$queryRaw<
      Array<{
        party: string;
        member_count: bigint;
        total_trades: bigint;
        total_volume: number;
      }>
    >`
      SELECT 
        m.party,
        COUNT(DISTINCT m.member_id) as member_count,
        COUNT(t.transaction_id) as total_trades,
        COALESCE(SUM((t.amount_range_low + t.amount_range_high) / 2.0), 0) as total_volume
      FROM "Members" m
      LEFT JOIN "Filings" f ON m.member_id = f.member_id
      LEFT JOIN "Transactions" t ON f.filing_id = t.filing_id
      WHERE m.party IS NOT NULL
      GROUP BY m.party
      HAVING COUNT(t.transaction_id) > 0
      ORDER BY total_volume DESC
    `;

    return result.map((row) => ({
      party: row.party,
      memberCount: Number(row.member_count),
      totalTrades: Number(row.total_trades),
      totalVolume: row.total_volume,
      avgVolumePerMember: row.total_volume / Number(row.member_count),
    }));
  });
}

// OPTIMIZED: Chamber stats with SQL aggregation
async function getChamberStatsOptimized() {
  return measureTimeAsync("Optimized Chamber Statistics Query", async () => {
    const result = await prisma.$queryRaw<
      Array<{
        chamber: string;
        member_count: bigint;
        total_trades: bigint;
        total_volume: number;
      }>
    >`
      SELECT 
        m.chamber,
        COUNT(DISTINCT m.member_id) as member_count,
        COUNT(t.transaction_id) as total_trades,
        COALESCE(SUM((t.amount_range_low + t.amount_range_high) / 2.0), 0) as total_volume
      FROM "Members" m
      LEFT JOIN "Filings" f ON m.member_id = f.member_id
      LEFT JOIN "Transactions" t ON f.filing_id = t.filing_id
      WHERE m.chamber IS NOT NULL
      GROUP BY m.chamber
      HAVING COUNT(t.transaction_id) > 0
      ORDER BY total_volume DESC
    `;

    const chamberMap = new Map<string, ChamberStats>();
    result.forEach((row) => {
      chamberMap.set(row.chamber, {
        memberCount: Number(row.member_count),
        totalTrades: Number(row.total_trades),
        totalVolume: row.total_volume,
      });
    });

    return {
      house: chamberMap.get("House") || {
        memberCount: 0,
        totalTrades: 0,
        totalVolume: 0,
      },
      senate: chamberMap.get("Senate") || {
        memberCount: 0,
        totalTrades: 0,
        totalVolume: 0,
      },
    };
  });
}

export default async function OptimizedMembersPage() {
  const pageStart = performance.now();
  console.log("🔍 OPTIMIZED: Starting OptimizedMembersPage render");

  // All queries run in parallel for maximum efficiency
  const [membersWithStats, stateStats, partyStats, chamberStats] =
    await Promise.all([
      getMembersDataOptimized(),
      getStateStatsOptimized(),
      getPartyStatsOptimized(),
      getChamberStatsOptimized(),
    ]);

  // Top traders are already sorted by volume from SQL query
  const topTraders = measureTime("Top Traders (already sorted)", () => {
    return membersWithStats.slice(0, 20);
  });

  const pageEnd = performance.now();
  console.log(
    `🚀 OPTIMIZED TOTAL PAGE TIME: ${(pageEnd - pageStart).toFixed(2)}ms`
  );

  // Calculate totals from the already-aggregated data
  const totalMembers = membersWithStats.length;
  const totalTrades = membersWithStats.reduce(
    (sum, m) => sum + m.tradeCount,
    0
  );
  const totalVolume = membersWithStats.reduce(
    (sum, m) => sum + m.totalVolume,
    0
  );

  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--c-navy)", color: "var(--c-navy)" }}
    >
      {/* Congress Alpha Brand */}
      <div
        className="w-full"
        style={{
          background: "linear-gradient(5deg, var(--c-navy), var(--c-navy-600))",
        }}
      >
        <span className="text-3xl font-extrabold" style={{ color: "#fff" }}>
          Congress Alpha
        </span>
      </div>
      <div className="max-w-7xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div
          className="card"
          style={{
            background:
              "linear-gradient(5deg, var(--c-navy), var(--c-navy-600))",
          }}
        >
          <div className="flex items-center mb-4">
            <Link href="/" className="button-secondary">
              ← Back to Home
            </Link>
          </div>
          <h1
            className="text-4xl font-bold mb-4 text-white"
            style={{ color: "var(--c-jade)" }}
          >
            Congressional Members
          </h1>
          <p className="text-xl text-white">
            Comprehensive analysis of trading patterns across Congress
          </p>
        </div>

        {/* Overview Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-blue-400">
              {totalMembers}
            </div>
            <div className="text-sm text-gray-400">Active Traders</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-green-400">
              {formatCurrency(totalVolume)}
            </div>
            <div className="text-sm text-gray-400">Total Volume</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-yellow-400">
              {totalTrades.toLocaleString()}
            </div>
            <div className="text-sm text-gray-400">Total Trades</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-purple-400">
              {Math.round(totalTrades / totalMembers)}
            </div>
            <div className="text-sm text-gray-400">Avg Trades/Member</div>
          </div>
        </div>

        {/* Chamber Comparison */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-white mb-6">
            House vs Senate
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h3 className="text-xl font-semibold text-white mb-4">
                House of Representatives
              </h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-400">Active Traders:</span>
                  <span className="text-white font-semibold">
                    {chamberStats.house.memberCount}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Volume:</span>
                  <span className="text-green-400 font-semibold">
                    {formatCurrency(chamberStats.house.totalVolume)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Trades:</span>
                  <span className="text-blue-400 font-semibold">
                    {chamberStats.house.totalTrades.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Avg Volume/Member:</span>
                  <span className="text-yellow-400 font-semibold">
                    {formatCurrency(
                      chamberStats.house.totalVolume /
                        chamberStats.house.memberCount
                    )}
                  </span>
                </div>
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h3 className="text-xl font-semibold text-white mb-4">Senate</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-400">Active Traders:</span>
                  <span className="text-white font-semibold">
                    {chamberStats.senate.memberCount}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Volume:</span>
                  <span className="text-green-400 font-semibold">
                    {formatCurrency(chamberStats.senate.totalVolume)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Trades:</span>
                  <span className="text-blue-400 font-semibold">
                    {chamberStats.senate.totalTrades.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Avg Volume/Member:</span>
                  <span className="text-yellow-400 font-semibold">
                    {formatCurrency(
                      chamberStats.senate.totalVolume /
                        chamberStats.senate.memberCount
                    )}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Party Statistics */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-white mb-6">
            Trading by Political Party
          </h2>
          <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead
                  style={{ background: "var(--c-navy-700)", color: "#fff" }}
                >
                  <tr className="text-left">
                    <th className="px-6 py-4 text-sm font-medium text-gray-300">
                      Party
                    </th>
                    <th className="px-6 py-4 text-sm font-medium text-gray-300">
                      Members
                    </th>
                    <th className="px-6 py-4 text-sm font-medium text-gray-300">
                      Total Volume
                    </th>
                    <th className="px-6 py-4 text-sm font-medium text-gray-300">
                      Total Trades
                    </th>
                    <th className="px-6 py-4 text-sm font-medium text-gray-300">
                      Avg Volume/Member
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {partyStats.map((party) => (
                    <tr
                      key={party.party}
                      className="hover:bg-[var(--c-jade-100)]"
                    >
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex px-3 py-1 text-sm font-semibold rounded-full ${
                            party.party === "Republican"
                              ? "bg-red-900 text-red-300"
                              : party.party === "Democrat"
                              ? "bg-blue-900 text-blue-300"
                              : "bg-gray-700 text-gray-300"
                          }`}
                        >
                          {party.party}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-white">
                        {party.memberCount}
                      </td>
                      <td className="px-6 py-4 text-green-400 font-semibold">
                        {formatCurrency(party.totalVolume)}
                      </td>
                      <td className="px-6 py-4 text-blue-400">
                        {party.totalTrades.toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-yellow-400 font-semibold">
                        {formatCurrency(party.avgVolumePerMember)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="grid lg:grid-cols-2 gap-8 mb-8">
          {/* Top States by Trading Volume */}
          <div>
            <h2 className="text-2xl font-bold text-white mb-6">
              Top States by Trading Volume
            </h2>
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="space-y-2 p-4">
                {stateStats.map((state, index) => (
                  <div
                    key={state.state}
                    className="flex items-center justify-between p-3 bg-gray-700 rounded-lg"
                  >
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-sm">
                        {index + 1}
                      </div>
                      <div>
                        <div className="text-white font-semibold">
                          {state.state}
                        </div>
                        <div className="text-sm text-gray-400">
                          {state.memberCount} members • {state.totalTrades}{" "}
                          trades
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-green-400 font-semibold">
                        {formatCurrency(state.totalVolume)}
                      </div>
                      <div className="text-xs text-gray-400">
                        {state.avgTradesPerMember.toFixed(1)} avg trades/member
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Top Volume Traders */}
          <div>
            <h2 className="text-2xl font-bold text-white mb-6">
              Top Volume Traders
            </h2>
            <div className="bg-gray-800 rounded-lg border border-gray-700">
              <div className="space-y-2 p-4">
                {topTraders.slice(0, 10).map((member, index) => (
                  <Link
                    key={member.member_id}
                    href={`/members/${member.member_id}`}
                    className="flex items-center justify-between p-3 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors"
                  >
                    <div className="flex items-center space-x-3">
                      <div className="w-8 h-8 bg-yellow-600 rounded-full flex items-center justify-center text-white font-bold text-sm">
                        {index + 1}
                      </div>
                      <div className="relative w-10 h-10 rounded-full overflow-hidden bg-gray-600 flex-shrink-0">
                        {member.photo_url ? (
                          <Image
                            src={member.photo_url}
                            alt={member.name}
                            fill
                            className="object-cover"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm font-semibold">
                            {member.name.charAt(0)}
                          </div>
                        )}
                      </div>
                      <div>
                        <div className="text-white font-semibold">
                          {member.name}
                        </div>
                        <div className="text-sm text-gray-400">
                          {member.party} • {member.chamber} • {member.state}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-green-400 font-semibold">
                        {formatCurrency(member.totalVolume)}
                      </div>
                      <div className="text-xs text-gray-400">
                        {member.tradeCount} trades
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* All Members Table */}
        <MembersTable members={membersWithStats} />
      </div>
    </div>
  );
}
