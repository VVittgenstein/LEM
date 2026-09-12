"""Exact probability checks for a proposed sequential partition selector.

This is a mathematical fixture, not a World Orogen map generator. It does not
generate any platform-mask examples or change the existing generators.
"""
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy.special import softmax

from common.io import utc_now, write_json
from common.runtime import configure_process_tree


def fixture():
    """Fourteen unequal artificial regions in a unit square with a 0.02 margin.

    A 3x5 rectangle grid is used and the first two cells are merged. Area and
    integrated squared distance include region interiors, not just centroids.
    The fixture geometry is only for arithmetic/probability verification.
    """
    labels = np.array([[0, 0, 1, 2, 3], [4, 5, 6, 7, 8], [9, 10, 11, 12, 13]])
    areas, moments = np.zeros(14), np.zeros(14)
    neighbors = [0]*14
    width, height = .96/5, .96/3
    for row in range(3):
        for col in range(5):
            region = int(labels[row, col])
            cx, cy = .02+(col+.5)*width, .02+(row+.5)*height
            area = width*height
            areas[region] += area
            moments[region] += area*((cx-.5)**2+(cy-.5)**2+(width**2+height**2)/12)
            for dr, dc in ((0, 1), (1, 0)):
                if row+dr < 3 and col+dc < 5:
                    other = int(labels[row+dr, col+dc])
                    if other != region:
                        neighbors[region] |= 1 << other
                        neighbors[other] |= 1 << region
    return labels, areas, moments, neighbors, 6


def all_features(areas, moments, neighbors):
    n = len(areas)
    count = 1 << n
    total_area, total_moment = np.zeros(count), np.zeros(count)
    radius2, fragmentation = np.zeros(count), np.zeros(count)
    components = np.zeros(count, dtype=np.int16)
    largest_fraction = np.zeros(count)
    for state in range(1, count):
        bit = state & -state
        index = bit.bit_length()-1
        previous = state ^ bit
        total_area[state] = total_area[previous]+areas[index]
        total_moment[state] = total_moment[previous]+moments[index]
        radius2[state] = total_moment[state]/total_area[state]
        remaining = state
        component_areas = []
        while remaining:
            pending = remaining & -remaining
            remaining ^= pending
            mass = 0.0
            while pending:
                current_bit = pending & -pending
                pending ^= current_bit
                current = current_bit.bit_length()-1
                mass += areas[current]
                new_bits = neighbors[current] & remaining
                remaining ^= new_bits
                pending |= new_bits
            component_areas.append(mass)
        fractions = np.asarray(component_areas)/total_area[state]
        components[state] = len(fractions)
        fragmentation[state] = max(0., 1.-float(fractions @ fractions))
        largest_fraction[state] = fractions.max()
    return {"area": total_area, "radius2": radius2, "fragmentation": fragmentation,
            "components": components, "largest_fraction": largest_fraction}


def exact_process(features, n, root, target, center_weight, connection_weight):
    """Forward dynamic programming sums probabilities of ALL growth paths.

    A transition adds exactly one whole region. The first crossing of target
    area is terminal. All not-yet-selected regions are eligible; no separate
    island-generation branch or component-count hard constraint is used.
    """
    count = 1 << n
    energy = center_weight*features["radius2"] + connection_weight*features["fragmentation"]
    visit = np.zeros(count)
    terminal = np.zeros(count)
    visit[1 << root] = 1.0
    transitions = {}
    maximum_normalization_error = 0.0
    minimum_transition_probability = 1.0
    for state in range(1, count):
        if not visit[state]:
            continue
        if features["area"][state] >= target-1e-12:
            terminal[state] = visit[state]
            continue
        indices = np.array([i for i in range(n) if not state & (1 << i)])
        if not len(indices):
            raise RuntimeError("target exceeds the available region area")
        destinations = state | (1 << indices)
        differences = energy[destinations]-energy[state]
        probabilities = softmax(-differences)
        maximum_normalization_error = max(maximum_normalization_error, abs(float(probabilities.sum())-1))
        minimum_transition_probability = min(minimum_transition_probability, float(probabilities.min()))
        visit[destinations] += visit[state]*probabilities
        cumulative = np.cumsum(probabilities)
        cumulative[-1] = 1.0
        transitions[state] = (destinations, cumulative)
    assert abs(terminal.sum()-1) < 1e-12
    assert minimum_transition_probability > 0
    return terminal, transitions, energy, maximum_normalization_error, minimum_transition_probability


def draw_paths(transitions, root, samples, seed):
    rng = np.random.default_rng(seed)
    final = np.empty(samples, dtype=np.int32)
    for index in range(samples):
        state = 1 << root
        while state in transitions:
            destinations, cumulative = transitions[state]
            state = int(destinations[np.searchsorted(cumulative, rng.random())])
        final[index] = state
    return final


def main():
    configure_process_tree(1)
    labels, areas, moments, neighbors, root = fixture()
    features = all_features(areas, moments, neighbors)
    # Independently check the geometrical and component definitions.
    assert abs(areas.sum()-.9216) < 1e-12
    assert features["fragmentation"][1 << root] == 0
    assert abs(features["fragmentation"][(1 << 6) | (1 << 8)]-.5) < 1e-12
    assert features["fragmentation"][(1 << 6) | (1 << 7) | (1 << 8)] < 1e-12
    assert features["radius2"][1 << 3] > features["radius2"][1 << root]
    target = .55
    configurations = [(0., 0.), (24., 0.), (24., 4.), (24., 8.)]
    results = []
    for index, (center_weight, connection_weight) in enumerate(configurations):
        terminal, transitions, energy, error, minimum = exact_process(
            features, len(areas), root, target, center_weight, connection_weight)
        selected = terminal > 0
        probability_connected = float(terminal[features["components"] == 1].sum())
        probability_fragmented = float(terminal[features["components"] >= 3].sum())
        samples = 20000
        drawn = draw_paths(transitions, root, samples, 20260911+index)
        observed_connected = float((features["components"][drawn] == 1).mean())
        tolerance = 6*np.sqrt(probability_connected*(1-probability_connected)/samples)+.002
        assert abs(observed_connected-probability_connected) < tolerance
        assert np.all(features["area"][drawn] >= target-1e-12)
        assert probability_fragmented > 0
        # A stepwise exponential choice generally does NOT sample exp(-E(final)).
        terminal_gibbs = np.zeros_like(terminal)
        terminal_gibbs[selected] = softmax(-energy[selected])
        tv = float(np.abs(terminal-terminal_gibbs).sum()/2)
        row = {"center_weight": center_weight, "connection_weight": connection_weight,
               "weights_status": "arithmetic fixture only, not project parameter selection",
               "reachable_terminal_combinations": int(selected.sum()),
               "total_terminal_probability": float(terminal.sum()),
               "minimum_terminal_probability": float(terminal[selected].min()),
               "maximum_terminal_probability": float(terminal[selected].max()),
               "entropy_effective_combinations": float(np.exp(-np.sum(terminal[selected]*np.log(terminal[selected])))),
               "component_count_distribution": {str(k): float(terminal[features["components"] == k].sum())
                                                for k in range(1, int(features["components"][selected].max())+1)},
               "maximum_step_probability_sum_error": error, "minimum_step_probability": minimum,
               "connected_probability_exact": probability_connected,
               "three_or_more_components_probability_exact": probability_fragmented,
               "expected_normalized_squared_radius": float(terminal @ features["radius2"]),
               "expected_largest_component_fraction": float(terminal @ features["largest_fraction"]),
               "expected_area_fraction": float(terminal @ features["area"]),
               "area_above_60_percent_probability": float(terminal[features["area"] > .6].sum()),
               "area_range": [float(features["area"][selected].min()), float(features["area"][selected].max())],
               "monte_carlo_samples": samples, "monte_carlo_connected_fraction": observed_connected,
               "monte_carlo_check_passed": True,
               "total_variation_from_terminal_gibbs_on_same_support": tv}
        results.append(row)
        print(f"weights=({center_weight:g},{connection_weight:g}) P(connected)={probability_connected:.6f} P(K>=3)={probability_fragmented:.8f}", flush=True)
    assert results[-1]["total_variation_from_terminal_gibbs_on_same_support"] > .01
    output = Path(__file__).resolve().parents[3] / "references/2026-09-11-partition-selection-model/math-check.json"
    report = {"created_utc": utc_now(), "status": "arithmetic_and_probability_checks_passed",
              "scope": "artificial partition graph; no World Orogen map, natural-appearance or geological validation",
              "fixture": {"labels": labels.tolist(), "region_count": len(areas), "areas": areas.tolist(),
                          "second_moments_about_center": moments.tolist(), "root": root,
                          "target_area_fraction": target, "total_available_fraction": float(areas.sum())},
              "model": {"radius2": "area-mean squared distance to chosen center, normalized by domain side squared",
                        "fragmentation": "1 - sum of squared connected-component area fractions",
                        "energy": "center_weight * radius2 + connection_weight * fragmentation",
                        "transition": "softmax of negative changes in energy over all unselected whole regions",
                        "stopping": "first whole-region step that reaches the target area"},
              "checks": {"area_and_moment_fixture": True, "component_merge": True,
                         "all_transition_probabilities_positive_and_normalized": True,
                         "terminal_probabilities_sum_to_one": True,
                         "direct_paths_match_exact_dynamic_programming": True,
                         "stepwise_process_distinguished_from_terminal_gibbs": True},
              "cases": results}
    write_json(output, report)
    print(f"saved {output}", flush=True)


if __name__ == "__main__":
    main()
