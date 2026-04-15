"""
x402 Guard - Domain/Address Reputation Scorer

Scores payment destinations (domains or wallet addresses) on a 0.0-1.0 scale
where 1.0 is fully trusted and 0.0 is highly suspicious.

No external API calls - uses static knowledge + heuristics.
"""

import re
import math
from typing import Optional


# ── Known-good canonical domains / protocols ──────────────────────────────────

KNOWN_GOOD_DOMAINS = {
    # CEXs
    "coinbase.com": 1.0,
    "pro.coinbase.com": 1.0,
    "api.coinbase.com": 1.0,
    "okx.com": 1.0,
    "www.okx.com": 1.0,
    "binance.com": 0.95,
    "www.binance.com": 0.95,
    "kraken.com": 0.95,
    "gemini.com": 0.95,
    # DeFi protocols
    "uniswap.org": 1.0,
    "app.uniswap.org": 1.0,
    "aave.com": 1.0,
    "app.aave.com": 1.0,
    "compound.finance": 1.0,
    "app.compound.finance": 1.0,
    "curve.fi": 0.95,
    "convexfinance.com": 0.90,
    "yearn.finance": 0.90,
    "1inch.io": 0.90,
    "app.1inch.io": 0.90,
    "balancer.fi": 0.90,
    "app.balancer.fi": 0.90,
    "sushiswap.org": 0.88,
    # Infra / oracles
    "chainlink.com": 1.0,
    "chain.link": 1.0,
    "infura.io": 0.95,
    "alchemy.com": 0.95,
    "quicknode.com": 0.95,
    # Stablecoins / payment
    "circle.com": 1.0,
    "tether.to": 0.85,
    # X Layer / OKX ecosystem
    "xlayer.tech": 1.0,
    "okx.com": 1.0,
    "www.okx.com": 1.0,
    # Generic trusted TLDs / patterns (handled separately)
}

# Canonical root domains (without www/app prefixes) - for subdomain matching
TRUSTED_ROOT_DOMAINS = {d.split(".")[-2] + "." + d.split(".")[-1] for d in KNOWN_GOOD_DOMAINS}

# ── Known-bad patterns ────────────────────────────────────────────────────────

# Common typosquatting character substitutions
TYPOSQUAT_SUBSTITUTIONS = {
    "o": ["0"],
    "i": ["1", "l"],
    "l": ["1", "i"],
    "e": ["3"],
    "a": ["@", "4"],
    "s": ["5", "$"],
    "g": ["9"],
    "b": ["6"],
    "coinbase": ["c0inbase", "coinbas3", "c0inbas3", "coinbaes", "coiinbase"],
    "uniswap": ["unisvvap", "un1swap", "uniswap"],
    "aave": ["aav3", "aaave"],
    "compound": ["c0mpound", "cornpound"],
}

KNOWN_BAD_PATTERNS = [
    r"^.*\.tk$",           # .tk - free domain often abused
    r"^.*\.ml$",           # .ml - free domain often abused
    r"^.*\.ga$",           # .ga - free domain often abused
    r"^.*\.cf$",           # .cf - free domain often abused
    r"^.*\.gq$",           # .gq - free domain
    r"^.*-airdrop\.",      # airdrop scam
    r"^.*airdrop.*\.",     # airdrop scam
    r"^.*-claim\.",        # claim scam
    r"^.*claim-.*\.",      # claim scam
    r"^.*drainer.*\.",     # drainer
    r"^.*phish.*\.",       # phishing
    r"^.*swap-.*\.",       # fake swap
    r"^.*-swap\.",         # fake swap suffix
    r"^.*bonus.*\.",       # bonus scam
    r"^.*profit.*\.",      # profit scam
    r"^.*crypto-.*\.",     # generic crypto prefix scams
    r"^.*free.*crypto",    # free crypto scam
    r"^.*doubl.*btc",      # doubling scam
    r"^.*2x.*coin",        # doubling scam
]

# High-entropy subdomain regex (looks random - like malware C2 or generated domains)
_HIGH_ENTROPY_SUBDOMAIN = re.compile(r"^[a-z0-9]{16,}\.")


class DomainReputation:
    """
    Score a domain or wallet address for trustworthiness.

    score_domain(domain) -> float in [0.0, 1.0]
      1.0 = fully trusted known entity
      0.7+ = likely safe
      0.4-0.7 = unknown / neutral, proceed with caution
      <0.4 = suspicious or known-bad pattern
      0.0 = confirmed bad pattern
    """

    def score_domain(self, domain: str) -> float:
        """Return trust score 0.0-1.0 for the given domain or address."""
        if not domain:
            return 0.3

        domain = domain.lower().strip()

        # Wallet addresses (0x...) — neutral, scored by other factors
        if re.match(r"^0x[0-9a-f]{40}$", domain):
            return 0.5

        # Strip protocol prefix if present
        domain = re.sub(r"^https?://", "", domain)
        domain = domain.split("/")[0]   # remove path
        domain = domain.split("?")[0]   # remove query
        domain = domain.split(":")[0]   # remove port

        # 1. Exact match in known-good list
        if domain in KNOWN_GOOD_DOMAINS:
            return KNOWN_GOOD_DOMAINS[domain]

        # 2. Check known bad patterns
        for pattern in KNOWN_BAD_PATTERNS:
            if re.search(pattern, domain):
                return 0.0

        # 3. High-entropy subdomain check
        if _HIGH_ENTROPY_SUBDOMAIN.match(domain):
            return 0.1

        # 4. Typosquatting detection
        typosquat_score = self._check_typosquat(domain)
        if typosquat_score is not None:
            return typosquat_score

        # 5. Check if it's a subdomain of a trusted root
        parts = domain.split(".")
        if len(parts) >= 2:
            root = parts[-2] + "." + parts[-1]
            if root in TRUSTED_ROOT_DOMAINS:
                # Subdomain of trusted root - slightly lower trust
                return 0.85

        # 6. Entropy-based heuristic for the domain itself
        entropy = self._shannon_entropy(domain.replace(".", ""))
        # High entropy names look random/generated
        if entropy > 4.2:
            return 0.25
        if entropy > 3.8:
            return 0.40

        # 7. Check for numeric-heavy domains (suspicious)
        digits = sum(1 for c in domain if c.isdigit())
        if digits / max(len(domain), 1) > 0.4:
            return 0.30

        # 8. Very short domain with .io/.com — could be legit startup
        if len(parts) >= 2 and len(parts[-2]) <= 3 and parts[-1] in ("io", "com", "net"):
            return 0.55

        # 9. Default neutral-unknown score
        return 0.50

    def is_known_good(self, domain: str) -> bool:
        return self.score_domain(domain) >= 0.85

    def is_suspicious(self, domain: str) -> bool:
        return self.score_domain(domain) < 0.40

    # ── Internals ────────────────────────────────────────────────────────────

    def _check_typosquat(self, domain: str) -> Optional[float]:
        """
        Compare domain against known brand names with character substitutions.
        Returns low score if likely typosquat, None if no match found.
        """
        # Extract the second-level domain for comparison
        parts = domain.split(".")
        if len(parts) < 2:
            return None
        sld = parts[-2]  # second-level domain

        brands = [
            "coinbase", "uniswap", "aave", "compound", "binance",
            "kraken", "gemini", "okx", "curve", "balancer", "sushiswap",
            "chainlink", "infura", "alchemy", "metamask", "opensea",
        ]

        for brand in brands:
            if sld == brand:
                # Exact match but not in our known-good list by full domain
                return 0.60  # unknown subdomain of a known brand name

            # Character-substitution distance
            if self._levenshtein_distance(sld, brand) == 1:
                return 0.05  # one edit away = likely typosquat

            # Contains brand with extra chars (padding attack)
            if brand in sld and sld != brand:
                return 0.10

            # Brand is contained in sld with hyphens
            if f"-{brand}" in sld or f"{brand}-" in sld:
                return 0.10

        return None

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Compute edit distance between two strings."""
        if len(s1) < len(s2):
            return DomainReputation._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
            prev = curr
        return prev[-1]

    @staticmethod
    def _shannon_entropy(s: str) -> float:
        """Calculate Shannon entropy of string."""
        if not s:
            return 0.0
        freq = {}
        for c in s:
            freq[c] = freq.get(c, 0) + 1
        n = len(s)
        return -sum((f / n) * math.log2(f / n) for f in freq.values())


# Singleton
reputation = DomainReputation()
