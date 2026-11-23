from dataclasses import dataclass
from itertools import product

from pgmpy.inference import VariableElimination

from .model import ACTION_HOURS, CONCEPTS, LEVELS, get_days_state

PERFORMANCE_REWARD = {"low": 0, "medium": 50, "high": 100}
# High stress costs as much as going up one level of exam performance.
STRESS_COST = {"low": 0, "medium": 20, "high": 50}


@dataclass(frozen=True)
class ActionScore:
    action: str
    performance: dict[str, float]
    stress: dict[str, float]
    expected_utility: float


def get_utility(performance, stress):
    return PERFORMANCE_REWARD[performance] - STRESS_COST[stress]


def score_actions(inference: VariableElimination, mastery, difficulties, days_left):
    """Return the performance probabilities, stress probabilities and score for each action."""
    evidence = {
        "Mastery": mastery,
        "Days Until Exam": get_days_state(days_left),
        **dict(zip(CONCEPTS, difficulties, strict=True)),
    }
    scores = []
    for action in ACTION_HOURS:
        # Keep the student and the exam date the same for all 3 queries.
        result = inference.query(
            variables=["Exam Performance", "Student Stress"],
            evidence={**evidence, "Action": action},
            elimination_order="MinFill",
            show_progress=False,
        )

        performance = dict.fromkeys(LEVELS, 0.0)
        stress = dict.fromkeys(LEVELS, 0.0)
        expected_utility = 0.0
        # There are 9 performance and stress pairs. Each one contributes probability times utility.
        for exam_result, stress_level in product(LEVELS, repeat=2):
            outcomes = {"Exam Performance": exam_result, "Student Stress": stress_level}
            probability = float(result.get_value(**outcomes))
            performance[exam_result] += probability
            stress[stress_level] += probability
            expected_utility += probability * get_utility(exam_result, stress_level)

        scores.append(ActionScore(action, performance, stress, expected_utility))
    return scores
