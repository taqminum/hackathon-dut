def calculate_detour(baseline_seconds: int, candidate_seconds: int) -> int:
    return max(0, candidate_seconds - baseline_seconds)
