# lifelog/utils/insight_engine.py

import json
import statistics
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any
from scipy.stats import pearsonr, spearmanr
import lifelog.config.config_manager as cf



LOG_FILE = cf.get_log_file()
TIME_FILE = cf.get_time_file()


def load_metric_data() -> List[Dict[str, Any]]:
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            return json.load(f).get("log", [])
    return []


def load_time_data() -> List[Dict[str, Any]]:
    if TIME_FILE.exists():
        with open(TIME_FILE, "r") as f:
            return json.load(f).get("history", [])
    return []


def daily_averages(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    daily = defaultdict(lambda: defaultdict(list))
    for e in entries:
        try:
            ts = datetime.fromisoformat(e["timestamp"])
            day = ts.date().isoformat()
            daily[day][e["metric"]].append(float(e["value"]))
        except Exception:
            continue

    result = defaultdict(dict)
    for day, metrics in daily.items():
        for metric, values in metrics.items():
            result[metric][day] = statistics.mean(values)
    return result


def compute_correlation(x: List[float], y: List[float]) -> Dict[str, float]:
    if len(x) < 2 or len(x) != len(y):
        return {"pearson": 0.0, "spearman": 0.0}
    try:
        return {
            "pearson": round(pearsonr(x, y)[0], 3),
            "spearman": round(spearmanr(x, y)[0], 3),
        }
    except Exception:
        return {"pearson": 0.0, "spearman": 0.0}


def generate_insights():
    metrics_data = daily_averages(load_metric_data())
    metric_names = list(metrics_data.keys())
    insights = []

    for i in range(len(metric_names)):
        for j in range(i + 1, len(metric_names)):
            m1 = metric_names[i]
            m2 = metric_names[j]

            days = set(metrics_data[m1].keys()) & set(metrics_data[m2].keys())
            if len(days) < 7:
                continue

            x = [metrics_data[m1][d] for d in sorted(days)]
            y = [metrics_data[m2][d] for d in sorted(days)]
            scores = compute_correlation(x, y)

            if abs(scores["pearson"]) > 0.4 or abs(scores["spearman"]) > 0.4:
                trend = "positive" if scores["pearson"] > 0 else "negative"
                insights.append(
                    {
                        "metrics": (m1, m2),
                        "correlation": scores,
                        "trend": trend,
                        "strength": abs(scores["pearson"]),
                        "note": f"When {m1} is higher, {m2} tends to be {trend}."
                    }
                )

    insights.sort(key=lambda i: i["strength"], reverse=True)
    return insights[:10]


if __name__ == "__main__":
    print("🔍 Analyzing your lifelog for meaningful patterns...")
    insights = generate_insights()
    print("\n✨ Top Correlated Patterns Found:")
    for i, insight in enumerate(insights, 1):
        print(f"{i}. {insight['note']} (Pearson: {insight['correlation']['pearson']})")
