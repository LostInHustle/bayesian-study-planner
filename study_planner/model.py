from itertools import product

from pgmpy.factors.discrete import TabularCPD
from pgmpy.models import DiscreteBayesianNetwork

CONCEPTS = ("Concept 1 Difficulty", "Concept 2 Difficulty", "Concept 3 Difficulty")
DIFFICULTIES = ("easy", "hard")
LEVELS = ("low", "medium", "high")
DAYS = ("far", "near", "urgent")
ACTION_HOURS = {"rest": 0, "light": 1, "focused": 5}

STATES = {
    **{concept: DIFFICULTIES for concept in CONCEPTS},
    "Difficulty Load": (0, 1, 2, 3),
    "Mastery": LEVELS,
    "Days Until Exam": DAYS,
    "Action": tuple(ACTION_HOURS),
    "Exam Performance": LEVELS,
    "Student Stress": LEVELS,
}

MASTERY_BASE = {"low": 0.44, "medium": 0.65, "high": 0.87}
TIME_MARGIN = {"far": 0.09, "near": 0.05, "urgent": 0.00}
URGENT_GAIN_FRACTION = {"rest": 1.0, "light": 0.75, "focused": 0.45}

# The probabilities are for low, medium and high stress, in that order.
STRESS_PROBABILITIES = {
    "rest": {
        "far": (0.90, 0.09, 0.01),
        "near": (0.85, 0.13, 0.02),
        "urgent": (0.55, 0.35, 0.10),  # The exam can cause stress on a rest day.
    },
    "light": {
        "far": (0.60, 0.35, 0.05),
        "near": (0.45, 0.45, 0.10),
        "urgent": (0.35, 0.45, 0.20),
    },
    "focused": {
        "far": (0.25, 0.55, 0.20),
        "near": (0.15, 0.50, 0.35),
        "urgent": (0.04, 0.26, 0.70),  # Cramming for 5 hours is likely to be stressful.
    },
}


def get_days_state(days_left):
    """Return far, near or urgent for the number of days left."""
    if days_left <= 0:
        raise ValueError("Study days must be before the exam date.")
    if days_left <= 2:
        return "urgent"
    if days_left <= 6:
        return "near"
    return "far"


def get_performance_probabilities(mastery, hard_concepts, days, action):
    """Return probabilities for low, medium and high exam performance."""
    # With 5 hours, the student can spend more time on each hard concept.
    gains = {
        "rest": 0.00,
        "light": 0.08 + 0.02 * hard_concepts,
        "focused": 0.10 + 0.11 * hard_concepts,
    }
    gain = gains[action]
    if days == "urgent":
        # A student doing a long session right before the exam has less time to review it.
        gain *= URGENT_GAIN_FRACTION[action]

    readiness = MASTERY_BASE[mastery] - 0.10 * hard_concepts + TIME_MARGIN[days] + gain
    readiness = max(0.05, min(0.98, readiness))

    # Low means 0 parts right, medium means 1 and high means 2.
    missed = 1 - readiness
    return missed**2, 2 * readiness * missed, readiness**2


def make_cpt(variable, parents, get_column):
    """Build the CPT with one column for each combination of parent states."""
    names = {name: list(STATES[name]) for name in (variable, *parents)}
    columns = [
        get_column(*case) for case in product(*(names[name] for name in parents))
    ]
    return TabularCPD(
        variable=variable,
        variable_card=len(names[variable]),
        values=list(zip(*columns)),
        evidence=list(parents) or None,
        evidence_card=[len(names[name]) for name in parents] or None,
        state_names=names,
    )


def get_load_probabilities(*difficulties):
    """Give probability 1 to the number of hard concepts."""
    return tuple(
        int(load == difficulties.count("hard")) for load in STATES["Difficulty Load"]
    )


def build_model():
    """Create the graph, add the nine CPTs and check the model."""
    model = DiscreteBayesianNetwork()
    for concept in CONCEPTS:
        model.add_edge(concept, "Difficulty Load")

    performance_parents = ("Mastery", "Difficulty Load", "Days Until Exam", "Action")
    stress_parents = ("Days Until Exam", "Action")
    model.add_edges_from((parent, "Exam Performance") for parent in performance_parents)
    model.add_edges_from((parent, "Student Stress") for parent in stress_parents)

    # Use a uniform prior for the variables we give as evidence.
    for variable in (*CONCEPTS, "Mastery", "Days Until Exam", "Action"):
        count = len(STATES[variable])
        prior = (1 / count,) * count
        model.add_cpds(make_cpt(variable, (), lambda: prior))

    model.add_cpds(
        make_cpt("Difficulty Load", CONCEPTS, get_load_probabilities),
        make_cpt(
            "Exam Performance", performance_parents, get_performance_probabilities
        ),
        make_cpt(
            "Student Stress",
            stress_parents,
            lambda days, action: STRESS_PROBABILITIES[action][days],
        ),
    )
    model.check_model()
    return model
