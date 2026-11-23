# Bayesian Study Planner

The program takes in an exam date, the student's mastery and the difficulty of 3 concepts. The Bayes net gives the probabilities of exam performance and stress. I use these to choose between 5 hours of study, 1 hour of study and rest for each day before the exam.

The program uses Python 3.11 or later and pgmpy. To run it, use the following commands from this folder.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
study-planner demo
```

`study-planner demo` prints the 3 scores and the action for each day. The probabilities are printed when there are 7, 6 and 2 days left, since those are the first days in each Days Until Exam state.

I used the same exam date in all 3 cases. In cases 1 and 2, mastery is low and I change the number of hard concepts from 3 to 1. In case 3, mastery is high and all 3 concepts are easy. The results are in [MODEL.md](MODEL.md), along with the variables and my reasons for choosing the numbers. To print the full tables, run `study-planner cpts`. `study-planner --version` prints the installed version.

## Use your own exam date

```sh
study-planner plan --exam-name 'AI final' --exam-date 2027-01-11 \
  --mastery low --difficulty hard hard easy --probabilities
```

Change `--exam-date` to your exam date. Set `--mastery` to `low`, `medium` or `high`, then put one `easy` or `hard` after `--difficulty` for each of the 3 concepts. In the example, the first two concepts are hard and the third is easy.

The program uses 09:00 to 20:00 in `America/Vancouver` for the study hours. With `--window 10:00 17:00` it uses 10:00 to 17:00 instead. To change the time zone, use `--timezone`. The local run assumes these hours are free on each day through the day before the exam.

## Use Google Calendar

First run `python -m pip install -e '.[google]'`. In Google Cloud, enable the Calendar API and set up the OAuth consent screen. Add `https://www.googleapis.com/auth/calendar.events` under Data Access. For a personal Google account, set the audience to External and add your account as a test user while the app is in testing.

Create a Desktop app OAuth client. Save the downloaded file as `credentials.json` in this folder. The first Calendar run opens the browser to sign in and saves `token.json`. Both files are ignored by Git. If the token is revoked, remove `token.json` so the next run opens the sign-in page again. See [Google's Python quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python) and [list of scopes](https://developers.google.com/workspace/calendar/api/auth).

```sh
study-planner plan --exam-name 'AI final' --exam-date 2027-01-11 \
  --mastery low --difficulty hard hard easy --google
```

This reads the primary calendar and prints when the sessions would be. For example, if there is only 1 hour free on Tuesday, the 5 hour score is still printed and the choice is between light study and rest. Add `--apply` to save the sessions. A second run with the same exam name and date can move a session that has yet to start. If the program now chooses rest, it removes that session.

Use `--calendar-id ID` if you want to use another calendar you can edit. If the exam is on that calendar, you can give `--exam-event EVENT_ID` in place of `--exam-date`. Use the event's `id` from the [Calendar Events List API](https://developers.google.com/workspace/calendar/api/v3/reference/events/list). The program uses the name from the event unless you give it one using `--exam-name`.

## Code organisation

The files in `study_planner` follow the order of the program. `build_model()` in `model.py` adds the variables and CPTs and calls `model.check_model()`. In `decision.py`, `score_actions()` runs the query once for each action. `get_utility()` is separate so the performance and stress scores can be changed without changing the query.

`find_study_block()` in `schedule.py` returns the first free block of the right length. `plan_study()` uses those blocks and the 3 scores to choose the action for each day. The Calendar calls are in `google_calendar.py`, so `plan_study()` can use either the busy times from Calendar or the empty schedule from the demo. `__main__.py` reads the inputs and prints the results.
