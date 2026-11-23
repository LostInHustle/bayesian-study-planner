import argparse
from datetime import date, datetime, time, timedelta
from importlib.metadata import version
from itertools import product
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .model import ACTION_HOURS, DIFFICULTIES, LEVELS, build_model, get_days_state
from .schedule import Exam, get_study_days, plan_study


def print_plan(exam, plan, show_probabilities=False):
    print(f"\n{exam.title}")
    print(f"Exam date = {exam.date}, Mastery = {exam.mastery}")
    print(f"Concept difficulties = {', '.join(exam.difficulties)}")
    print("Expected utility for each day")
    shown_timings = set()

    for day in plan:
        session = ""
        if day.session is not None:
            session = f" {day.session.start:%H:%M}–{day.session.end:%H:%M %Z}"
        scores = []
        for score in day.scores:
            unavailable = (
                " (does not fit)" if score.action not in day.feasible_actions else ""
            )
            scores.append(f"{score.action} = {score.expected_utility:.2f}{unavailable}")

        days_label = "day" if day.days_left == 1 else "days"
        print(
            f"{day.date} ({day.days_left} {days_label} left): "
            f"{', '.join(scores)}. Action = {day.action}{session}"
        )
        timing = get_days_state(day.days_left)
        if show_probabilities and timing not in shown_timings:
            print("  Performance and stress (low, medium, high)")
            for score in day.scores:
                performance = ", ".join(f"{p:.1%}" for p in score.performance.values())
                stress = ", ".join(f"{p:.1%}" for p in score.stress.values())
                print(
                    f"  {score.action}: Performance = [{performance}], Stress = [{stress}]"
                )
            shown_timings.add(timing)


def run_demo():
    # Cases 1 and 2 use the same mastery and change the difficulty ratings.
    # All 3 cases have the same exam date and study hours.
    now = datetime(2027, 1, 4, 8, tzinfo=ZoneInfo("America/Vancouver"))
    exam_date = now.date() + timedelta(days=7)
    dates = get_study_days(now.date(), exam_date)
    window = (time(9), time(20))
    cases = (
        Exam(
            "Case 1: Weak student with three hard concepts",
            exam_date,
            "low",
            ("hard", "hard", "hard"),
        ),
        Exam(
            "Case 2: Weak student with one hard concept",
            exam_date,
            "low",
            ("hard", "easy", "easy"),
        ),
        Exam(
            "Case 3: Strong student with three easy concepts",
            exam_date,
            "high",
            ("easy", "easy", "easy"),
        ),
    )
    for exam in cases:
        print_plan(exam, plan_study(exam, dates, window, now), show_probabilities=True)


def print_cpts():
    """Print the probabilities for one combination of parent states on each line."""
    for cpt in build_model().get_cpds():
        parents = cpt.variables[1:]
        cases = product(*(cpt.state_names[parent] for parent in parents))
        print(f"\n{cpt.variable}")
        print(
            " | ".join(
                [*parents, *(f"P({state})" for state in cpt.state_names[cpt.variable])]
            )
        )
        for case, values in zip(cases, cpt.get_values().T, strict=True):
            print(
                " | ".join(
                    [*(str(state) for state in case), *(f"{p:.4f}" for p in values)]
                )
            )


def run_plan(args):
    try:
        zone = ZoneInfo(args.timezone)
    except ZoneInfoNotFoundError:
        raise ValueError(f"Unknown time zone: {args.timezone}") from None
    window = tuple(args.window)
    if window[0] >= window[1]:
        raise ValueError("The study window must end after it starts on the same day.")

    exam_date = args.exam_date
    exam_name = args.exam_name
    busy, started_days = [], set()
    if args.google:
        try:
            from . import google_calendar
        except ModuleNotFoundError as error:
            if not error.name.startswith(("google", "googleapiclient")):
                raise
            raise ValueError(
                "Install the Calendar libraries with python -m pip install -e '.[google]'."
            ) from None

        events = google_calendar.connect().events()
        if args.exam_event:
            event_title, exam_date = google_calendar.get_exam(
                events, args.calendar_id, args.exam_event, zone
            )
            exam_name = exam_name or event_title

    now = datetime.now(zone)
    if exam_date <= now.date():
        raise ValueError("The exam date must be after today in the selected time zone.")
    exam = Exam(exam_name or "Exam", exam_date, args.mastery, tuple(args.difficulty))
    dates = get_study_days(now.date(), exam.date)

    if args.google:
        plan_key = f"{exam.date}:{exam.title}"
        calendar_schedule = google_calendar.read_schedule(
            events, args.calendar_id, dates, now, plan_key
        )
        busy, started_days = calendar_schedule.busy, calendar_schedule.started_days

    dates = [day for day in dates if day not in started_days]
    plan = plan_study(exam, dates, window, now, busy)
    print_plan(exam, plan, args.probabilities)
    for day in sorted(started_days):
        print(f"{day}: The study session has already started.")

    if args.apply:
        print("\nGoogle Calendar changes")
        google_calendar.write_plan(
            events,
            args.calendar_id,
            exam,
            plan,
            calendar_schedule.planned_events,
            plan_key,
        )
    elif args.google:
        print("\nAdd --apply to save these sessions to Google Calendar.")


def parse_clock(value):
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Use a 24-hour time in HH:MM format."
        ) from None


def main():
    parser = argparse.ArgumentParser(
        description="Plan one student's study sessions for an exam."
    )
    parser.add_argument(
        "--version", action="version", version=version("bayesian-study-planner")
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Run the three example cases.")
    commands.add_parser("cpts", help="Print all conditional probability tables.")
    plan = commands.add_parser("plan", help="Choose study sessions before an exam.")
    exam = plan.add_mutually_exclusive_group(required=True)
    exam.add_argument(
        "--exam-date", type=date.fromisoformat, help="Exam date as YYYY-MM-DD."
    )
    exam.add_argument(
        "--exam-event", help="Google Calendar event ID for the exam. Requires --google."
    )
    plan.add_argument(
        "--exam-name", help="Title to use for the exam and study sessions."
    )
    plan.add_argument("--mastery", choices=LEVELS, required=True)
    plan.add_argument("--difficulty", choices=DIFFICULTIES, nargs=3, required=True)
    plan.add_argument(
        "--timezone",
        default="America/Vancouver",
        help="IANA time zone (default: America/Vancouver).",
    )
    plan.add_argument(
        "--window",
        type=parse_clock,
        nargs=2,
        default=(time(9), time(20)),
        metavar=("START", "END"),
    )
    plan.add_argument(
        "--probabilities",
        action="store_true",
        help="Print the performance and stress probabilities for far, near and urgent days.",
    )
    plan.add_argument(
        "--google", action="store_true", help="Use availability from Google Calendar."
    )
    plan.add_argument(
        "--calendar-id",
        default="primary",
        help="Google Calendar to read and write (default: primary).",
    )
    plan.add_argument(
        "--apply",
        action="store_true",
        help="Write the plan to Google Calendar. Requires --google.",
    )

    args = parser.parse_args()
    if args.command == "demo":
        run_demo()
    elif args.command == "cpts":
        print_cpts()
    else:
        if (args.apply or args.exam_event) and not args.google:
            plan.error("--apply and --exam-event require --google.")
        try:
            run_plan(args)
        except (ValueError, OSError) as error:
            plan.error(str(error))


if __name__ == "__main__":
    main()
