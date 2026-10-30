"""Simple, explainable adaptive traffic-signal decision engine for CITINOVA AI."""
ROADS = ("North", "South", "East", "West")

def calculate_priority(vehicles, waiting):
    """Weighted congestion score; higher means the road needs more green time."""
    return round(max(0, vehicles) * 2.0 + max(0, waiting) * 0.7, 1)

def select_signal(traffic_data, emergency=None):
    """Return (road, green_seconds, mode). Emergency requests override congestion."""
    if emergency:
        road = str(emergency).capitalize()
        if road not in ROADS:
            raise ValueError("Unknown road")
        return road, 45, "EMERGENCY PRIORITY"
    if not traffic_data:
        return "North", 20, "NORMAL"
    scores = {
        road: calculate_priority(
            int(data.get("vehicles", 0)),
            int(data.get("waiting", 0))
        )
        for road, data in traffic_data.items()
    }
    road = max(scores, key=scores.get)
    # Keep demo signal timing bounded and easy to explain.
    duration = max(15, min(60, int(15 + scores[road] * 0.35)))
    return road, duration, "ADAPTIVE"
