import { lookup } from "node:dns/promises";

export type Resolver = (names: string[]) => Promise<Set<string>>;

const CACHE_MS = 60_000;
const MAPPED_PREFIX = "::ffff:";

export async function resolvePeers(names: string[]): Promise<Set<string>> {
  const addresses = new Set<string>();
  for (const name of names) {
    try {
      for (const item of await lookup(name, { all: true })) {
        addresses.add(item.address);
      }
    } catch {
      continue;
    }
  }
  return addresses;
}

export function plainAddress(address: string | undefined): string | null {
  if (address === undefined || address === "") {
    return null;
  }
  if (address.startsWith(MAPPED_PREFIX)) {
    return address.slice(MAPPED_PREFIX.length);
  }
  return address;
}

export class PeerCheck {
  private addresses = new Set<string>();
  private until = 0;
  private readonly names: string[];
  private readonly resolver: Resolver;
  private readonly clock: () => number;

  constructor(names: string[], resolver: Resolver = resolvePeers, clock: () => number = Date.now) {
    this.names = names;
    this.resolver = resolver;
    this.clock = clock;
  }

  async allows(remote: string | undefined): Promise<boolean> {
    const peer = plainAddress(remote);
    if (peer === null || this.names.length === 0) {
      return false;
    }
    const now = this.clock();
    if (now >= this.until || !this.addresses.has(peer)) {
      this.addresses = await this.resolver(this.names);
      this.until = now + CACHE_MS;
    }
    return this.addresses.has(peer);
  }
}
