export const dynamic = "force-dynamic";
export const revalidate = 0;
// webstack/src/app/members/page.tsx
// OPTIMIZED VERSION - Uses SQL aggregation instead of loading 46K+ transactions into JavaScript

import { prisma } from "@/src/lib/prisma";
import Link from "next/link";
import Image from "next/image";
import MembersTable from "@/src/components/MembersTable";

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

  console.log(`🚀 PERFORMANCE: ${operationName} took ${duration.toFixed(2)}ms`);
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

  console.log(`🚀 PERFORMANCE: ${operationName} took ${duration.toFixed(2)}ms`);
  return result;
}

// OPTIMIZED: Use SQL aggregation instead of loading 46K+ transactions into JavaScript
async function getMembersData() {
  console.log("🔍 OPTIMIZED: Starting getMembersData() with SQL aggregation");

  // Single optimized query using raw SQL with aggregation - NO individual transactions loaded
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
    `📊 OPTIMIZED: Got ${membersWithStats.length} members with trades directly from SQL (no transaction processing)`
  );
  return membersWithStats;
}

// OPTIMIZED: Get state stats directly from SQL instead of JavaScript processing
async function getStateStats() {
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

// OPTIMIZED: Get party stats directly from SQL instead of JavaScript processing
async function getPartyStats() {
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

export default async function MembersPage() {
  const pageStart = performance.now();
  console.log("🔍 PERFORMANCE TEST: Starting MembersPage render");

  const membersWithStats = await getMembersData();
  const stateStats = await getStateStats();
  const partyStats = await getPartyStats();

  // Top traders - measure this too
  const topTraders = measureTime("Top Traders Calculation", () => {
    return membersWithStats
      .sort((a, b) => b.totalVolume - a.totalVolume)
      .slice(0, 20);
  });

  // Chamber statistics - measure this too
  const {
    houseMembers,
    senateMembers,
    houseTotalVolume,
    senateTotalVolume,
    houseTotalTrades,
    senateTotalTrades,
  } = measureTime("Chamber Statistics Calculation", () => {
    const houseMembers = membersWithStats.filter((m) => m.chamber === "House");
    const senateMembers = membersWithStats.filter(
      (m) => m.chamber === "Senate"
    );

    const houseTotalVolume = houseMembers.reduce(
      (sum, m) => sum + m.totalVolume,
      0
    );
    const senateTotalVolume = senateMembers.reduce(
      (sum, m) => sum + m.totalVolume,
      0
    );
    const houseTotalTrades = houseMembers.reduce(
      (sum, m) => sum + m.tradeCount,
      0
    );
    const senateTotalTrades = senateMembers.reduce(
      (sum, m) => sum + m.tradeCount,
      0
    );

    return {
      houseMembers,
      senateMembers,
      houseTotalVolume,
      senateTotalVolume,
      houseTotalTrades,
      senateTotalTrades,
    };
  });

  const pageEnd = performance.now();
  console.log(`🚀 TOTAL PAGE TIME: ${(pageEnd - pageStart).toFixed(2)}ms`);

  return (
    <div
      className="min-h-screen"
      style={{ background: "var(--c-navy)", color: "var(--c-navy)" }}
    >
      {/* Back button in top left corner */}
      <div
        style={{
          margin: "1.5rem 0 0 1.5rem",
          position: "absolute",
          top: 0,
          left: 0,
        }}
      >
        <Link href="/">
          <Image
            src="/return.png"
            alt="Back to Home"
            width={40}
            height={40}
            style={{ cursor: "pointer" }}
          />
        </Link>
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
              {membersWithStats.length}
            </div>
            <div className="text-sm text-gray-400">Active Traders</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-green-400">
              {formatCurrency(
                membersWithStats.reduce((sum, m) => sum + m.totalVolume, 0)
              )}
            </div>
            <div className="text-sm text-gray-400">Total Volume</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-yellow-400">
              {membersWithStats
                .reduce((sum, m) => sum + m.tradeCount, 0)
                .toLocaleString()}
            </div>
            <div className="text-sm text-gray-400">Total Trades</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
            <div className="text-3xl font-bold text-purple-400">
              {Math.round(
                membersWithStats.reduce((sum, m) => sum + m.tradeCount, 0) /
                  membersWithStats.length
              )}
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
              <h3 className="text-xl font-semibold mb-4">
                House of Representatives
              </h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-400">Active Traders:</span>
                  <span className="text-white font-semibold">
                    {houseMembers.length}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Volume:</span>
                  <span className="text-green-400 font-semibold">
                    {formatCurrency(houseTotalVolume)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Trades:</span>
                  <span className="text-blue-400 font-semibold">
                    {houseTotalTrades.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Avg Volume/Member:</span>
                  <span className="text-yellow-400 font-semibold">
                    {formatCurrency(houseTotalVolume / houseMembers.length)}
                  </span>
                </div>
              </div>
            </div>
            <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
              <h3 className="text-xl font-semibold mb-4">Senate</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-400">Active Traders:</span>
                  <span className="text-white font-semibold">
                    {senateMembers.length}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Volume:</span>
                  <span className="text-green-400 font-semibold">
                    {formatCurrency(senateTotalVolume)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Trades:</span>
                  <span className="text-blue-400 font-semibold">
                    {senateTotalTrades.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Avg Volume/Member:</span>
                  <span className="text-yellow-400 font-semibold">
                    {formatCurrency(senateTotalVolume / senateMembers.length)}
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
