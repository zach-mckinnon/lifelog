# lifelog/utils/reporting/comprehensive_reports.py

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
from collections import defaultdict

from lifelog.utils.db import track_repository, time_repository, task_repository
from lifelog.utils.db.report_repository import get_tracker_summary, get_time_summary
from lifelog.utils.shared_utils import now_utc
import logging

logger = logging.getLogger(__name__)


class PersonalAnalytics:
    """Comprehensive personal analytics with fallback support."""

    def __init__(self, fallback_local: bool = True):
        self.fallback_local = fallback_local

    def generate_productivity_insights(self, days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive productivity insights."""
        insights = {
            'period_days': days,
            'generated_at': datetime.now().isoformat(),
            'task_insights': self._analyze_tasks(days),
            'time_insights': self._analyze_time_tracking(days),
            'tracker_insights': self._analyze_trackers(days),
            'correlation_insights': self._analyze_correlations(days),
            'recommendations': []
        }

        # Generate actionable recommendations
        insights['recommendations'] = self._generate_recommendations(insights)

        return insights

    def _analyze_tasks(self, days: int) -> Dict[str, Any]:
        """Analyze task completion patterns."""
        try:
            # Get tasks from the last N days
            since = now_utc() - timedelta(days=days)

            try:
                if hasattr(task_repository, 'query_tasks'):
                    all_tasks = task_repository.query_tasks(
                        show_completed=True)
                else:
                    from lifelog.utils.db.db_helper import safe_query
                    rows = safe_query(
                        "SELECT * FROM tasks WHERE deleted = 0", ())
                    all_tasks = [dict(row) for row in rows]
            except Exception as e:
                logger.error("Failed to get tasks: %s", e)
                return {'error': 'Could not load task data'}

            if not all_tasks:
                return {'total_tasks': 0, 'message': 'No tasks found'}

            # Filter to recent tasks
            recent_tasks = []
            completed_tasks = []
            overdue_tasks = []

            for task in all_tasks:
                try:
                    if hasattr(task, '__dict__'):
                        task_dict = task.__dict__
                    else:
                        task_dict = task

                    created = task_dict.get('created')
                    if isinstance(created, str):
                        created_dt = datetime.fromisoformat(
                            created.replace('Z', '+00:00'))
                    else:
                        created_dt = created

                    if created_dt and created_dt >= since:
                        recent_tasks.append(task_dict)

                    # Check completion status
                    status = task_dict.get('status')
                    if status and (status == 'done' or str(status).endswith('done')):
                        completed_tasks.append(task_dict)

                    # Check for overdue
                    due = task_dict.get('due')
                    if due and status != 'done':
                        if isinstance(due, str):
                            due_dt = datetime.fromisoformat(
                                due.replace('Z', '+00:00'))
                        else:
                            due_dt = due

                        if due_dt < now_utc():
                            overdue_tasks.append(task_dict)

                except Exception as e:
                    logger.warning("Skipping invalid task: %s", e)
                    continue

            # Calculate metrics
            completion_rate = len(completed_tasks) / \
                len(recent_tasks) if recent_tasks else 0

            # Category analysis
            category_stats = defaultdict(lambda: {'total': 0, 'completed': 0})
            for task in recent_tasks:
                cat = task.get('category', 'uncategorized')
                category_stats[cat]['total'] += 1

                status = task.get('status')
                if status and (status == 'done' or str(status).endswith('done')):
                    category_stats[cat]['completed'] += 1

            return {
                'total_tasks': len(all_tasks),
                'recent_tasks': len(recent_tasks),
                'completed_tasks': len(completed_tasks),
                'overdue_tasks': len(overdue_tasks),
                'completion_rate': round(completion_rate * 100, 1),
                'category_breakdown': dict(category_stats),
                'avg_tasks_per_day': round(len(recent_tasks) / days, 1)
            }

        except Exception as e:
            logger.error("Task analysis failed: %s", e, exc_info=True)
            return {'error': f'Task analysis failed: {e}'}

    def _analyze_time_tracking(self, days: int) -> Dict[str, Any]:
        """Analyze time tracking patterns."""
        try:
            time_df = get_time_summary(
                since_days=days, fallback_local=self.fallback_local)

            if time_df.empty:
                return {'total_time': 0, 'message': 'No time tracking data found'}

            total_minutes = time_df['duration_minutes'].sum()
            avg_daily = total_minutes / days

            # Top categories
            top_categories = time_df.nlargest(
                5, 'duration_minutes').to_dict('records')

            return {
                'total_time_minutes': float(total_minutes),
                'total_time_hours': round(total_minutes / 60, 1),
                'avg_daily_minutes': round(avg_daily, 1),
                'avg_daily_hours': round(avg_daily / 60, 1),
                'top_categories': top_categories,
                'category_count': len(time_df)
            }

        except Exception as e:
            logger.error("Time tracking analysis failed: %s", e, exc_info=True)
            return {'error': f'Time tracking analysis failed: {e}'}

    def _analyze_trackers(self, days: int) -> Dict[str, Any]:
        """Analyze tracker data patterns."""
        try:
            tracker_df = get_tracker_summary(
                since_days=days, fallback_local=self.fallback_local)

            if tracker_df.empty:
                return {'total_entries': 0, 'message': 'No tracker data found'}

            # Calculate statistics per tracker
            tracker_stats = {}
            for tracker_title in tracker_df['tracker_title'].unique():
                if pd.isna(tracker_title):
                    continue

                tracker_data = tracker_df[tracker_df['tracker_title']
                                          == tracker_title]
                values = tracker_data['value'].dropna()

                if len(values) > 0:
                    tracker_stats[tracker_title] = {
                        'entries': len(values),
                        'avg_value': round(float(values.mean()), 2),
                        'min_value': float(values.min()),
                        'max_value': float(values.max()),
                        'std_dev': round(float(values.std()), 2) if len(values) > 1 else 0,
                        'trend': self._calculate_trend(values.tolist()),
                        'consistency_score': round(self._calculate_consistency(values.tolist()), 2)
                    }

            return {
                'total_entries': len(tracker_df),
                'unique_trackers': len(tracker_stats),
                'tracker_stats': tracker_stats,
                'avg_entries_per_day': round(len(tracker_df) / days, 1)
            }

        except Exception as e:
            logger.error("Tracker analysis failed: %s", e, exc_info=True)
            return {'error': f'Tracker analysis failed: {e}'}

    def _analyze_correlations(self, days: int) -> Dict[str, Any]:
        """Find correlations between different metrics."""
        try:
            tracker_df = get_tracker_summary(
                since_days=days, fallback_local=self.fallback_local)
            time_df = get_time_summary(
                since_days=days, fallback_local=self.fallback_local)

            correlations = []

            if not tracker_df.empty and not time_df.empty:
                # Group by date for correlation analysis
                daily_tracker = tracker_df.groupby(['date', 'tracker_title'])[
                    'value'].mean().unstack(fill_value=0)
                daily_time = time_df.groupby('date')['duration_minutes'].sum()

                # Find correlations between trackers and time spent
                for tracker in daily_tracker.columns:
                    # Need variance for correlation
                    if len(daily_tracker[tracker].unique()) > 1:
                        # Align dates
                        common_dates = daily_tracker.index.intersection(
                            daily_time.index)
                        if len(common_dates) > 3:  # Need enough data points
                            corr = daily_tracker.loc[common_dates, tracker].corr(
                                daily_time.loc[common_dates])
                            # Only significant correlations
                            if not pd.isna(corr) and abs(corr) > 0.3:
                                correlations.append({
                                    'tracker': tracker,
                                    'metric': 'total_daily_time',
                                    'correlation': round(float(corr), 3),
                                    'strength': 'strong' if abs(corr) > 0.7 else 'moderate',
                                    'direction': 'positive' if corr > 0 else 'negative'
                                })

            return {
                'correlations_found': len(correlations),
                'correlations': correlations,
                'analysis_period_days': days
            }

        except Exception as e:
            logger.error("Correlation analysis failed: %s", e, exc_info=True)
            return {'error': f'Correlation analysis failed: {e}'}

    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction for a series of values."""
        if len(values) < 2:
            return 'insufficient_data'

        # Simple linear trend
        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]

        if abs(slope) < 0.01:  # Threshold for "stable"
            return 'stable'
        elif slope > 0:
            return 'increasing'
        else:
            return 'decreasing'

    def _calculate_consistency(self, values: List[float]) -> float:
        """Calculate consistency score (0-1, where 1 is perfectly consistent)."""
        if len(values) < 2:
            return 1.0

        # Use coefficient of variation (inverse)
        mean_val = np.mean(values)
        if mean_val == 0:
            return 1.0

        cv = np.std(values) / mean_val
        # Convert to 0-1 scale where lower CV = higher consistency
        return max(0, 1 - min(cv, 1))

    def _generate_recommendations(self, insights: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on insights."""
        recommendations = []

        # Task recommendations
        task_insights = insights.get('task_insights', {})
        completion_rate = task_insights.get('completion_rate', 0)

        if completion_rate < 50:
            recommendations.append(
                "📈 Your task completion rate is below 50%. Consider breaking large tasks into smaller, manageable chunks.")
        elif completion_rate > 80:
            recommendations.append(
                "🎉 Excellent task completion rate! You're maintaining great productivity momentum.")

        overdue_tasks = task_insights.get('overdue_tasks', 0)
        if overdue_tasks > 5:
            recommendations.append(
                "⏰ You have several overdue tasks. Consider reviewing your time estimates and priorities.")

        # Time tracking recommendations
        time_insights = insights.get('time_insights', {})
        avg_daily_hours = time_insights.get('avg_daily_hours', 0)

        if avg_daily_hours < 4:
            recommendations.append(
                "⏱️ Low time tracking detected. Tracking more activities could provide better insights into your productivity patterns.")

        # Tracker recommendations
        tracker_insights = insights.get('tracker_insights', {})
        tracker_stats = tracker_insights.get('tracker_stats', {})

        for tracker_name, stats in tracker_stats.items():
            consistency = stats.get('consistency_score', 0)
            if consistency < 0.3:
                recommendations.append(
                    f"📊 '{tracker_name}' shows inconsistent patterns. Consider examining factors that influence this metric.")

            trend = stats.get('trend', '')
            if trend == 'decreasing' and 'mood' in tracker_name.lower():
                recommendations.append(
                    f"😟 '{tracker_name}' shows a declining trend. Consider lifestyle factors that might be affecting this.")

        # Correlation recommendations
        corr_insights = insights.get('correlation_insights', {})
        correlations = corr_insights.get('correlations', [])

        for corr in correlations:
            if corr['strength'] == 'strong':
                direction = corr['direction']
                tracker = corr['tracker']
                if direction == 'positive':
                    recommendations.append(
                        f"💡 Strong positive correlation found: Higher '{tracker}' values correlate with more productive time. Consider optimizing this metric.")
                else:
                    recommendations.append(
                        f"⚠️ Strong negative correlation found: Higher '{tracker}' values correlate with less productive time. This might need attention.")

        if not recommendations:
            recommendations.append(
                "📝 Keep up the consistent tracking! More data will unlock deeper insights over time.")

        return recommendations


def create_ascii_chart(data: List[Tuple[str, float]], title: str, max_width: int = 50) -> str:
    """Create simple ASCII bar chart for terminal display."""
    if not data:
        return f"{title}\n(No data available)"

    # Find max value for scaling
    max_val = max(val for _, val in data)
    if max_val == 0:
        return f"{title}\n(All values are zero)"

    lines = [title, "=" * len(title)]

    for label, value in data:
        # Scale bar length
        bar_length = int((value / max_val) * max_width)
        bar = "█" * bar_length + "░" * (max_width - bar_length)

        # Format value
        if value >= 1000:
            value_str = f"{value/1000:.1f}k"
        elif value >= 10:
            value_str = f"{value:.0f}"
        else:
            value_str = f"{value:.1f}"

        lines.append(f"{label[:20]:20} {bar} {value_str}")

    return "\n".join(lines)
