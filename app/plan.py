from dataclasses import dataclass, field

from parse import Release


@dataclass
class Plan:
    variant: str
    picks: list = field(default_factory=list)
    covered: set = field(default_factory=set)
    owned: set = field(default_factory=set)
    missing: set = field(default_factory=set)
    dead: set = field(default_factory=set)
    horizon: int = 0
    size: int = 0


def plausible_cap(known_volumes, status, found=()):
    if known_volumes:
        return known_volumes + (1 if status == "FINISHED" else 4)
    ordered = sorted(v for v in set(found) if v >= 1)
    for a, b in zip(ordered, ordered[1:]):
        if b - a > 15:
            return a
    return None


def trim(release: Release, cap):
    if cap is None:
        return set(release.volumes)
    return {v for v in release.volumes if v <= cap}


def variants_summary(releases):
    out = {}
    for r in releases:
        if r.reject:
            continue
        s = out.setdefault(r.variant, {"releases": 0, "volumes": set(), "seeded": set()})
        s["releases"] += 1
        s["volumes"] |= r.volumes
        if r.seeders > 0:
            s["seeded"] |= r.volumes
    return out


def default_variant(releases):
    summary = variants_summary(releases)
    if "Standard" in summary and summary["Standard"]["seeded"]:
        return "Standard"
    if not summary:
        return "Standard"
    return max(summary, key=lambda k: len(summary[k]["seeded"]))


def build_plan(releases, variant, owned=frozenset(), known_volumes=None, status=None):
    found = [v for r in releases if not r.reject and r.variant == variant for v in r.volumes]
    cap = plausible_cap(known_volumes, status, found)
    pool, seen = [], set()
    for r in releases:
        if r.reject or r.variant != variant:
            continue
        key = r.info_hash or r.title.lower()
        if key in seen:
            continue
        seen.add(key)
        vols = trim(r, cap)
        if vols:
            pool.append((r, vols))

    alive = [(r, v) for r, v in pool if r.seeders > 0]
    reachable = set().union(*[v for _, v in alive]) if alive else set()
    everything = set().union(*[v for _, v in pool]) if pool else set()
    horizon = max([known_volumes or 0] + [v for v in everything if v > 0] or [0])
    target = {v for v in reachable if v >= 1} - set(owned)

    picks, covered = [], set()
    remaining = set(target)
    while remaining:
        best, best_key = None, None
        for r, vols in alive:
            if any(p[0] is r for p in picks):
                continue
            new = vols & remaining
            if not new:
                continue
            overlap = len(vols & (covered | set(owned)))
            score = r.quality * (len(new) - 0.15 * overlap)
            key = (score, r.seeders, r.official, -r.size)
            if best_key is None or key > best_key:
                best, best_key = (r, vols), key
        if best is None:
            break
        picks.append(best)
        covered |= best[1]
        remaining -= best[1]

    changed = True
    while changed:
        changed = False
        for i, (r, vols) in enumerate(picks):
            others = set(owned).union(*[v for j, (_, v) in enumerate(picks) if j != i])
            if (vols & target) <= others:
                picks.pop(i)
                changed = True
                break

    covered = set().union(*[v for _, v in picks]) if picks else set()
    plan = Plan(variant=variant, owned=set(owned), horizon=horizon)
    plan.picks = sorted(picks, key=lambda p: min(p[1]))
    plan.covered = covered
    wanted = set(range(1, horizon + 1))
    plan.missing = wanted - covered - set(owned)
    plan.dead = (everything - reachable) & plan.missing
    plan.size = sum(r.size for r, _ in picks)
    return plan
