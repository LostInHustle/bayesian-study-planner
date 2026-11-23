from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from pgmpy.inference import VariableElimination

from .decision import ActionScore, score_actions
from .model import ACTION_HOURS, build_model, get_days_state


@dataclass(frozen=True)
class Exam:
    title: str
    date: date
    mastery: str
    difficulties: tuple[str, str, str]


@dataclass(frozen=True)
class TimeBlock:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class DayPlan:
    date: date
    days_left: int
    scores: list[ActionScore]
    feasible_actions: set[str]
    action: str
    session: TimeBlock | None


def get_study_days(today, exam_date):
    """Return dates from today through the day before the exam."""
    return [
        today + timedelta(days=offset) for offset in range((exam_date - today).days)
    ]


def find_study_block(day: date, hours: int, window: tuple[time, time], now, busy):
    """Find the first free block long enough for the session, or return None."""
    zone = now.tzinfo
    start, end = (
        datetime.combine(day, clock, zone).astimezone(UTC) for clock in window
    )
    now_utc = now.astimezone(UTC)
    if now_utc.second or now_utc.microsecond:
        now_utc = now_utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
    start = max(start, now_utc)
    duration = timedelta(hours=hours)

    # Use UTC so the session is still the right length when the clocks change.
    busy_times = sorted(
        (block.start.astimezone(UTC), block.end.astimezone(UTC)) for block in busy
    )
    for busy_start, busy_end in busy_times:
        if busy_end <= start:
            continue
        if start + duration <= busy_start:
            break
        start = busy_end

    if start + duration <= end:
        return TimeBlock(start.astimezone(zone), (start + duration).astimezone(zone))
    return None


def plan_study(exam: Exam, dates, window, now, busy=()):
    """Choose the action with the highest score that fits in each day."""
    inference = VariableElimination(build_model())
    scores_by_timing = {}
    plan = []

    for day in dates:
        days_left = (exam.date - day).days
        timing = get_days_state(days_left)
        # For example, 5 and 6 days left are both near, so they use the same scores.
        if timing not in scores_by_timing:
            scores_by_timing[timing] = score_actions(
                inference, exam.mastery, exam.difficulties, days_left
            )
        scores = scores_by_timing[timing]

        slots = {
            action: find_study_block(day, hours, window, now, busy)
            for action, hours in ACTION_HOURS.items()
            if hours > 0
        }
        feasible_actions = {"rest"} | {
            action for action, block in slots.items() if block is not None
        }
        # If two actions have the same score, choose the one that takes fewer hours.
        best = max(
            (score for score in scores if score.action in feasible_actions),
            key=lambda score: (
                round(score.expected_utility, 10),
                -ACTION_HOURS[score.action],
            ),
        )
        plan.append(
            DayPlan(
                day,
                days_left,
                scores,
                feasible_actions,
                best.action,
                slots.get(best.action),
            )
        )

    return plan
